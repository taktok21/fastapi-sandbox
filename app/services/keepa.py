"""
Keepa API クライアント

v1.0では Request Products（基本情報/統計のみ）を使用
offersは使わない（コスト抑制：1ASIN=1トークン想定）

参考: https://keepa.com/#!discuss/t/product-request/110
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.cache import ApiCache

logger = logging.getLogger(__name__)
settings = get_settings()

# Keepa domain codes
KEEPA_DOMAIN_JP = 5  # Japan

# Keepa時間はMinutes since 01.01.2011
KEEPA_EPOCH = datetime(2011, 1, 1)


def keepa_time_to_datetime(keepa_time: int) -> datetime:
    """Keepa時間をdatetimeに変換"""
    return KEEPA_EPOCH + timedelta(minutes=keepa_time)


def datetime_to_keepa_time(dt: datetime) -> int:
    """datetimeをKeepa時間に変換"""
    return int((dt - KEEPA_EPOCH).total_seconds() / 60)


class KeepaClient:
    """Keepa APIクライアント"""

    BASE_URL = "https://api.keepa.com"

    def __init__(self, api_key: str, rate_limit: float = 0.5):
        """
        Args:
            api_key: Keepa API Key
            rate_limit: requests per second (default: 0.5 = 2秒に1回)
        """
        self.api_key = api_key
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

    def _request(self, endpoint: str, params: dict) -> dict:
        """APIリクエストを実行"""
        self._wait_for_rate_limit()

        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # トークン残量をログ
            tokens_left = data.get("tokensLeft", "?")
            logger.info(f"Keepa API: tokens_left={tokens_left}")

            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"Keepa API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Keepa API request failed: {e}")
            raise

    def get_products(
        self,
        asins: list[str],
        domain: int = KEEPA_DOMAIN_JP,
        stats: int = 180,
        offers: int = 0,  # v1.0では使わない
    ) -> list[dict]:
        """
        複数ASINの商品情報を取得

        Args:
            asins: ASINリスト（最大100件）
            domain: Keepaドメイン（5=Japan）
            stats: 統計期間（日数）
            offers: オファー取得数（0=取得しない）

        Returns:
            商品情報リスト
        """
        if not asins:
            return []

        if len(asins) > 100:
            raise ValueError("Max 100 ASINs per request")

        params = {
            "domain": domain,
            "asin": ",".join(asins),
            "stats": stats,
        }

        if offers > 0:
            params["offers"] = offers

        data = self._request("product", params)
        return data.get("products", [])

    def get_product(
        self,
        asin: str,
        domain: int = KEEPA_DOMAIN_JP,
        stats: int = 180,
    ) -> Optional[dict]:
        """単一ASINの商品情報を取得"""
        products = self.get_products([asin], domain, stats)
        return products[0] if products else None

    def close(self):
        """クライアントを閉じる"""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class KeepaService:
    """Keepaデータ取得・解析サービス"""

    # CSV index definitions (Keepa Product csv array indices)
    CSV_AMAZON = 0       # Amazon price
    CSV_NEW = 1          # New price (lowest)
    CSV_USED = 2         # Used price (lowest)
    CSV_SALES_RANK = 3   # Sales rank
    CSV_LIST_PRICE = 4   # List price
    CSV_NEW_FBA = 10     # New FBA price
    CSV_COUNT_NEW = 11   # Count of new offers
    CSV_COUNT_USED = 12  # Count of used offers
    CSV_COUNT_NEW_FBA = 18  # Count of new FBA offers

    def __init__(self, db: Session):
        self.db = db
        self.client = KeepaClient(
            api_key=settings.keepa_api_key,
            rate_limit=settings.rate_limit_keepa,
        )

    def _get_cache(self, asin: str) -> Optional[dict]:
        """キャッシュからデータを取得"""
        cache_key = f"keepa_product_{asin}"
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

    def _set_cache(self, asin: str, data: dict):
        """キャッシュにデータを保存"""
        cache_key = f"keepa_product_{asin}"
        expires_at = datetime.utcnow() + timedelta(seconds=settings.cache_ttl_seconds)

        # 既存キャッシュを削除
        self.db.query(ApiCache).filter(ApiCache.cache_key == cache_key).delete()

        cache = ApiCache(
            cache_key=cache_key,
            api_type="KEEPA",
            request_params={"asin": asin},
            response_data=data,
            fetched_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        self.db.add(cache)
        self.db.commit()

    def fetch_product(self, asin: str, use_cache: bool = True) -> Optional[dict]:
        """
        商品情報を取得（キャッシュ対応）

        Returns:
            Keepa product data or None
        """
        if use_cache:
            cached = self._get_cache(asin)
            if cached:
                return cached

        if not settings.keepa_api_key:
            logger.warning("Keepa API key not configured")
            return None

        product = self.client.get_product(asin)
        if product:
            self._set_cache(asin, product)

        return product

    def parse_product(self, product: dict) -> dict:
        """
        Keepa商品データを解析してアプリ用データに変換

        Returns:
            {
                'title': str,
                'brand': str,
                'category': str,
                'jan_code': str,
                'model_number': str,
                'rank_current': int,
                'rank_avg_30': int,
                'rank_avg_90': int,
                'sales_est_30': int,
                'sales_est_90': int,
                'sales_est_180': int,
                'seller_count': int,
                'fba_seller_count': int,
                'price_history': list,
                'rank_history': list,
            }
        """
        result = {
            'title': None,
            'brand': None,
            'category': None,
            'jan_code': None,
            'model_number': None,
            'rank_current': None,
            'rank_avg_30': None,
            'rank_avg_90': None,
            'sales_est_30': None,
            'sales_est_90': None,
            'sales_est_180': None,
            'seller_count': None,
            'fba_seller_count': None,
            'price_history': [],
            'rank_history': [],
        }

        if not product:
            return result

        # 基本情報
        result['title'] = product.get('title')
        result['brand'] = product.get('brand')

        # カテゴリ
        categories = product.get('categoryTree', [])
        if categories:
            result['category'] = categories[-1].get('name') if categories else None

        # EAN/JAN
        ean_list = product.get('eanList', [])
        if ean_list:
            result['jan_code'] = ean_list[0]

        # 型番
        result['model_number'] = product.get('model') or product.get('partNumber')

        # 統計情報
        stats = product.get('stats', {})
        if stats:
            result.update(self._parse_stats(stats))

        # CSV時系列データ
        csv_data = product.get('csv', [])
        if csv_data:
            result.update(self._parse_csv(csv_data))

        return result

    def _parse_stats(self, stats: dict) -> dict:
        """統計情報を解析"""
        result = {}

        # 現在のランキング
        current = stats.get('current', [])
        if current and len(current) > self.CSV_SALES_RANK:
            rank = current[self.CSV_SALES_RANK]
            if rank and rank > 0:
                result['rank_current'] = rank

        # 平均ランキング
        avg = stats.get('avg', [])
        if avg:
            # avg[0] = 30日, avg[1] = 90日, avg[2] = 180日
            for period, key in [(0, 'rank_avg_30'), (1, 'rank_avg_90')]:
                if len(avg) > period:
                    period_avg = avg[period]
                    if period_avg and len(period_avg) > self.CSV_SALES_RANK:
                        rank = period_avg[self.CSV_SALES_RANK]
                        if rank and rank > 0:
                            result[key] = rank

        # 販売数推定（salesRankDrops）
        # Keepaでは30/90/180日のランク下落回数から販売数を推定
        sales_drops = stats.get('salesRankDrops30', 0)
        if sales_drops and sales_drops > 0:
            result['sales_est_30'] = sales_drops

        sales_drops_90 = stats.get('salesRankDrops90', 0)
        if sales_drops_90 and sales_drops_90 > 0:
            result['sales_est_90'] = sales_drops_90

        sales_drops_180 = stats.get('salesRankDrops180', 0)
        if sales_drops_180 and sales_drops_180 > 0:
            result['sales_est_180'] = sales_drops_180

        # セラー数
        if current:
            if len(current) > self.CSV_COUNT_NEW:
                count = current[self.CSV_COUNT_NEW]
                if count and count > 0:
                    result['seller_count'] = count

            if len(current) > self.CSV_COUNT_NEW_FBA:
                count = current[self.CSV_COUNT_NEW_FBA]
                if count and count > 0:
                    result['fba_seller_count'] = count

        return result

    def _parse_csv(self, csv_data: list) -> dict:
        """CSV時系列データを解析"""
        result = {
            'price_history': [],
            'rank_history': [],
        }

        # New FBA価格の推移
        if len(csv_data) > self.CSV_NEW_FBA:
            fba_prices = csv_data[self.CSV_NEW_FBA]
            if fba_prices:
                result['price_history'] = self._parse_time_series(fba_prices)

        # ランキングの推移
        if len(csv_data) > self.CSV_SALES_RANK:
            ranks = csv_data[self.CSV_SALES_RANK]
            if ranks:
                result['rank_history'] = self._parse_time_series(ranks)

        return result

    def _parse_time_series(self, data: list) -> list[dict]:
        """
        Keepa時系列データを解析

        Keepa CSVは [time1, value1, time2, value2, ...] 形式
        """
        if not data or len(data) < 2:
            return []

        result = []
        for i in range(0, len(data) - 1, 2):
            keepa_time = data[i]
            value = data[i + 1]

            if keepa_time is None or value is None:
                continue

            # -1 は値なし
            if value == -1:
                continue

            dt = keepa_time_to_datetime(keepa_time)
            result.append({
                'date': dt.date().isoformat(),
                'value': value,
            })

        return result

    def close(self):
        """リソースを解放"""
        self.client.close()


def get_keepa_service(db: Session) -> KeepaService:
    """KeepaServiceのファクトリ関数"""
    return KeepaService(db)
