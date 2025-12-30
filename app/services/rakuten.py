"""
楽天API クライアント

v1.0で使用するAPI:
- 楽天製品検索API (Product Search): JAN/型番で製品を特定
- 楽天市場商品検索API (Ichiba Item Search): 最安候補を抽出

同一商品判定:
1. JANコードで製品検索API → 製品を特定
2. 特定した製品のJAN/型番でIchiba商品検索 → 候補取得
3. 最安（商品+送料-ポイント）を採用

レート制限: 1 rps
"""
import logging
import time
import re
from datetime import datetime, timedelta
from typing import Optional, List
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.cache import ApiCache
from app.models.rakuten_candidate import RakutenCandidate

logger = logging.getLogger(__name__)
settings = get_settings()


def normalize_model_number(model: str) -> str:
    """型番を正規化（大文字化、空白/ハイフン除去）"""
    if not model:
        return ""
    return re.sub(r'[\s\-_]', '', model.upper())


class RakutenClient:
    """楽天API クライアント"""

    PRODUCT_SEARCH_URL = "https://app.rakuten.co.jp/services/api/Product/Search/20170426"
    ICHIBA_SEARCH_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

    def __init__(self, app_id: str, rate_limit: float = 1.0):
        self.app_id = app_id
        self.rate_limit = rate_limit
        self._last_request_time = 0.0
        self._client = httpx.Client(timeout=30.0)

    def _wait_for_rate_limit(self):
        """レート制限を遵守"""
        if self.rate_limit <= 0:
            return
        min_interval = 1.0 / self.rate_limit
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _request(self, url: str, params: dict) -> dict:
        """APIリクエストを実行"""
        self._wait_for_rate_limit()

        params["applicationId"] = self.app_id
        params["format"] = "json"

        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Rakuten API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Rakuten API request failed: {e}")
            raise

    def search_product(self, product_code: str) -> Optional[dict]:
        """
        製品検索API: JANコードで製品を検索

        Args:
            product_code: JANコード（13桁）

        Returns:
            製品情報
        """
        params = {
            "productCode": product_code,
            "hits": 1,
        }

        try:
            data = self._request(self.PRODUCT_SEARCH_URL, params)
            products = data.get("Products", [])
            if products:
                return products[0].get("Product", {})
            return None
        except Exception as e:
            logger.warning(f"Product search failed for {product_code}: {e}")
            return None

    def search_items(
        self,
        keyword: str,
        hits: int = 30,
        sort: str = "+itemPrice",  # 価格昇順
        min_price: int = None,
        max_price: int = None,
    ) -> List[dict]:
        """
        市場商品検索API: キーワードで商品を検索

        Args:
            keyword: 検索キーワード（JAN/型番/商品名）
            hits: 取得件数（最大30）
            sort: ソート順（+itemPrice=価格昇順）

        Returns:
            商品リスト
        """
        params = {
            "keyword": keyword,
            "hits": min(hits, 30),
            "sort": sort,
        }

        if min_price:
            params["minPrice"] = min_price
        if max_price:
            params["maxPrice"] = max_price

        try:
            data = self._request(self.ICHIBA_SEARCH_URL, params)
            items = data.get("Items", [])
            return [item.get("Item", {}) for item in items]
        except Exception as e:
            logger.warning(f"Item search failed for {keyword}: {e}")
            return []

    def close(self):
        """クライアントを閉じる"""
        self._client.close()


class RakutenService:
    """楽天データ取得・マッチングサービス"""

    def __init__(self, db: Session):
        self.db = db
        self.client = RakutenClient(
            app_id=settings.rakuten_app_id,
            rate_limit=settings.rate_limit_rakuten,
        )
        self.point_rate_total = (
            settings.default_point_rate_normal + settings.default_point_rate_spu
        )

    def _get_cache(self, cache_key: str, api_type: str) -> Optional[dict]:
        """キャッシュからデータを取得"""
        cache = (
            self.db.query(ApiCache)
            .filter(
                ApiCache.cache_key == cache_key,
                ApiCache.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if cache:
            logger.debug(f"Cache hit: {cache_key}")
            return cache.response_data
        return None

    def _set_cache(self, cache_key: str, api_type: str, data: dict, params: dict = None):
        """キャッシュにデータを保存"""
        expires_at = datetime.utcnow() + timedelta(seconds=settings.cache_ttl_seconds)

        self.db.query(ApiCache).filter(ApiCache.cache_key == cache_key).delete()

        cache = ApiCache(
            cache_key=cache_key,
            api_type=api_type,
            request_params=params,
            response_data=data,
            fetched_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        self.db.add(cache)
        self.db.commit()

    def find_matching_items(
        self,
        jan_code: Optional[str],
        model_number: Optional[str],
        job_id: str,
        asin: str,
        point_rate: float = None,
    ) -> dict:
        """
        JAN/型番で楽天商品を検索し、最安を特定

        Args:
            jan_code: JANコード
            model_number: 型番
            job_id: ジョブID
            asin: ASIN
            point_rate: ポイント率（指定しない場合はデフォルト）

        Returns:
            {
                'match_type': 'JAN' | 'MODEL' | 'NONE',
                'chosen_item': {...},
                'candidates': [...],
            }
        """
        point_rate = point_rate or self.point_rate_total
        result = {
            'match_type': 'NONE',
            'chosen_item': None,
            'candidates': [],
        }

        candidates = []

        # 1. JAN検索
        if jan_code and len(jan_code) >= 8:
            jan_items = self._search_by_jan(jan_code)
            for item in jan_items:
                item['_match_type'] = 'JAN'
                item['_match_value'] = jan_code
            candidates.extend(jan_items)
            if jan_items:
                result['match_type'] = 'JAN'

        # 2. 型番検索（JANで見つからない場合のみ）
        if not candidates and model_number:
            normalized = normalize_model_number(model_number)
            if normalized and len(normalized) >= 3:
                model_items = self._search_by_model(normalized, model_number)
                for item in model_items:
                    item['_match_type'] = 'MODEL'
                    item['_match_value'] = model_number
                candidates.extend(model_items)
                if model_items:
                    result['match_type'] = 'MODEL'

        if not candidates:
            result['match_type'] = 'NONE'
            return result

        # 候補を処理して最安を決定
        processed = []
        for item in candidates:
            processed_item = self._process_item(item, point_rate)
            processed.append(processed_item)

        # 最安（実質仕入れ価格）でソート
        processed.sort(key=lambda x: x.get('net_cost', float('inf')))

        result['candidates'] = processed
        result['chosen_item'] = processed[0] if processed else None

        # 候補をDBに保存
        self._save_candidates(job_id, asin, processed, result['match_type'])

        return result

    def _search_by_jan(self, jan_code: str) -> List[dict]:
        """JANコードで商品を検索"""
        cache_key = f"rakuten_jan_{jan_code}"
        cached = self._get_cache(cache_key, "RAKUTEN_SEARCH")
        if cached:
            return cached

        items = self.client.search_items(jan_code, hits=30)
        self._set_cache(cache_key, "RAKUTEN_SEARCH", items, {"jan": jan_code})
        return items

    def _search_by_model(self, normalized_model: str, original_model: str) -> List[dict]:
        """型番で商品を検索（正規化後の完全一致のみ）"""
        cache_key = f"rakuten_model_{normalized_model}"
        cached = self._get_cache(cache_key, "RAKUTEN_SEARCH")
        if cached:
            return cached

        # 元の型番で検索
        items = self.client.search_items(original_model, hits=30)

        # 正規化後の完全一致でフィルタ（商品名に型番が含まれるか）
        matched = []
        for item in items:
            item_name = item.get('itemName', '')
            # 商品名を正規化して型番が含まれるかチェック
            normalized_name = normalize_model_number(item_name)
            if normalized_model in normalized_name:
                matched.append(item)

        self._set_cache(cache_key, "RAKUTEN_SEARCH", matched, {"model": original_model})
        return matched

    def _process_item(self, item: dict, point_rate: float) -> dict:
        """商品情報を処理して必要な値を計算"""
        price = item.get('itemPrice', 0)

        # 送料判定
        shipping = 0
        shipping_status = 'UNKNOWN'
        postage_flag = item.get('postageFlag', 1)  # 0=送料込み, 1=送料別
        if postage_flag == 0:
            shipping_status = 'FREE'
        else:
            # 送料別の場合はUNKNOWN（手動確認）
            shipping_status = 'UNKNOWN'
            # 楽天APIでは送料を取得できないため、概算値を使用しないとUNKNOWNのまま
            # v1.0では送料UNKNOWNは手動確認

        # 総コスト
        if shipping_status == 'FREE':
            gross_cost = price
        else:
            gross_cost = price  # 送料不明の場合は商品価格のみ（最低額）

        # ポイント計算
        point_amount = int(gross_cost * point_rate)

        # 実質コスト
        net_cost = gross_cost - point_amount

        return {
            'item_code': item.get('itemCode'),
            'item_name': item.get('itemName'),
            'item_url': item.get('itemUrl'),
            'shop_code': item.get('shopCode'),
            'shop_name': item.get('shopName'),
            'price': price,
            'shipping': shipping if shipping > 0 else None,
            'shipping_status': shipping_status,
            'gross_cost': gross_cost,
            'point_rate': point_rate,
            'point_amount': point_amount,
            'net_cost': net_cost,
            '_match_type': item.get('_match_type'),
            '_match_value': item.get('_match_value'),
        }

    def _save_candidates(
        self,
        job_id: str,
        asin: str,
        candidates: List[dict],
        match_type: str,
    ):
        """候補をDBに保存"""
        # 既存候補を削除
        self.db.query(RakutenCandidate).filter(
            RakutenCandidate.job_id == job_id,
            RakutenCandidate.asin == asin,
        ).delete()

        for i, cand in enumerate(candidates[:20]):  # 上位20件を保存
            rc = RakutenCandidate(
                job_id=job_id,
                asin=asin,
                match_type=cand.get('_match_type', match_type),
                match_value=cand.get('_match_value'),
                rakuten_item_code=cand.get('item_code'),
                item_name=cand.get('item_name'),
                item_url=cand.get('item_url'),
                shop_code=cand.get('shop_code'),
                shop_name=cand.get('shop_name'),
                price=cand.get('price', 0),
                shipping=cand.get('shipping'),
                shipping_status=cand.get('shipping_status', 'UNKNOWN'),
                total_cost=cand.get('gross_cost'),
                point_rate=cand.get('point_rate'),
                point_rate_used=cand.get('point_rate'),
                point_amount=cand.get('point_amount'),
                is_chosen=(i == 0),  # 最安が選択
            )
            self.db.add(rc)

        self.db.commit()

    def close(self):
        """リソースを解放"""
        self.client.close()


def get_rakuten_service(db: Session) -> RakutenService:
    """RakutenServiceのファクトリ関数"""
    return RakutenService(db)
