"""
Amazon SP-API クライアント

v1.0で使用するAPI:
- Product Pricing API: getItemOffers（最安FBA価格）
- Product Fees API: getMyFeesEstimateForASIN（手数料計算）
- Catalog Items API: getCatalogItem（JAN/型番補完）
- Listings Restrictions API: getListingsRestrictions（出品制限）

レート制限: 1 rps / burst 2
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Any
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.cache import ApiCache

logger = logging.getLogger(__name__)
settings = get_settings()

# SP-API ライブラリ
try:
    from sp_api.api import Products, ProductFees, CatalogItems, ListingsRestrictions
    from sp_api.base import Marketplaces, SellingApiException
    SP_API_AVAILABLE = True
except ImportError:
    SP_API_AVAILABLE = False
    logger.warning("python-amazon-sp-api not available")


class SpApiClient:
    """SP-API クライアント（レート制限対応）"""

    def __init__(
        self,
        refresh_token: str,
        lwa_app_id: str,
        lwa_client_secret: str,
        marketplace: str = "A1VC38T7YXB528",  # Japan
        rate_limit: float = 1.0,
    ):
        self.credentials = {
            "refresh_token": refresh_token,
            "lwa_app_id": lwa_app_id,
            "lwa_client_secret": lwa_client_secret,
        }
        self.marketplace = getattr(Marketplaces, "JP", None)
        self.rate_limit = rate_limit
        self._last_request_time = 0.0

    def _wait_for_rate_limit(self):
        """レート制限を遵守"""
        if self.rate_limit <= 0:
            return
        min_interval = 1.0 / self.rate_limit
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _get_products_api(self):
        """Product Pricing APIクライアント"""
        return Products(credentials=self.credentials, marketplace=self.marketplace)

    def _get_fees_api(self):
        """Product Fees APIクライアント"""
        return ProductFees(credentials=self.credentials, marketplace=self.marketplace)

    def _get_catalog_api(self):
        """Catalog Items APIクライアント"""
        return CatalogItems(credentials=self.credentials, marketplace=self.marketplace)

    def _get_restrictions_api(self):
        """Listings Restrictions APIクライアント"""
        return ListingsRestrictions(credentials=self.credentials, marketplace=self.marketplace)


class SpApiService:
    """SP-APIデータ取得サービス"""

    def __init__(self, db: Session):
        self.db = db
        if not SP_API_AVAILABLE:
            self.client = None
            return

        self.client = SpApiClient(
            refresh_token=settings.sp_api_refresh_token,
            lwa_app_id=settings.sp_api_client_id,
            lwa_client_secret=settings.sp_api_client_secret,
            marketplace=settings.sp_api_marketplace_id,
            rate_limit=settings.rate_limit_sp_api,
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

    def get_item_offers(self, asin: str, use_cache: bool = True) -> Optional[dict]:
        """
        商品のオファー情報を取得（最安FBA価格など）

        Returns:
            {
                'fba_lowest_price': int,  # 最安FBA価格（円）
                'fba_seller_count': int,  # FBAセラー数
                'new_lowest_price': int,  # 新品最安価格（円）
                'seller_count': int,      # 総セラー数
            }
        """
        cache_key = f"sp_api_offers_{asin}"

        if use_cache:
            cached = self._get_cache(cache_key, "SP_API_PRICING")
            if cached:
                return cached

        if not self.client:
            logger.warning("SP-API client not configured")
            return None

        try:
            self.client._wait_for_rate_limit()
            products_api = self.client._get_products_api()
            response = products_api.get_item_offers(asin=asin, item_condition="New")

            result = self._parse_offers(response.payload)
            self._set_cache(cache_key, "SP_API_PRICING", result, {"asin": asin})
            return result

        except Exception as e:
            logger.error(f"SP-API get_item_offers error for {asin}: {e}")
            return None

    def _parse_offers(self, payload: dict) -> dict:
        """オファー情報を解析"""
        result = {
            'fba_lowest_price': None,
            'fba_seller_count': 0,
            'new_lowest_price': None,
            'seller_count': 0,
        }

        if not payload:
            return result

        # Summary
        summary = payload.get('Summary', {})
        if summary:
            # 総セラー数
            total_count = summary.get('TotalOfferCount', 0)
            result['seller_count'] = total_count

            # 最安価格（新品）
            lowest_prices = summary.get('LowestPrices', [])
            for lp in lowest_prices:
                if lp.get('condition') == 'New':
                    if lp.get('fulfillmentChannel') == 'Amazon':
                        # FBA
                        price = lp.get('LandedPrice', {}).get('Amount')
                        if price:
                            result['fba_lowest_price'] = int(float(price))
                    elif lp.get('fulfillmentChannel') == 'Merchant':
                        # 自己発送
                        price = lp.get('LandedPrice', {}).get('Amount')
                        if price and result['new_lowest_price'] is None:
                            result['new_lowest_price'] = int(float(price))

            # FBAセラー数
            buy_box_prices = summary.get('BuyBoxPrices', [])
            for bbp in buy_box_prices:
                if bbp.get('condition') == 'New':
                    result['fba_seller_count'] = summary.get('NumberOfOffers', [{}])[0].get('OfferCount', 0)

        # Offers から詳細取得
        offers = payload.get('Offers', [])
        fba_count = 0
        for offer in offers:
            if offer.get('IsFulfilledByAmazon'):
                fba_count += 1
                # 最安FBA価格（まだ未設定なら）
                if result['fba_lowest_price'] is None:
                    listing_price = offer.get('ListingPrice', {}).get('Amount')
                    shipping = offer.get('Shipping', {}).get('Amount', 0)
                    if listing_price:
                        result['fba_lowest_price'] = int(float(listing_price) + float(shipping))

        if fba_count > 0:
            result['fba_seller_count'] = fba_count

        return result

    def get_fees_estimate(self, asin: str, price: int, use_cache: bool = True) -> Optional[dict]:
        """
        手数料見積もりを取得

        Args:
            asin: ASIN
            price: 販売価格（円）

        Returns:
            {
                'referral_fee': int,    # 販売手数料（円）
                'fba_fee': int,         # FBA手数料（円）
                'other_fee': int,       # その他手数料（円）
                'total_fee': int,       # 合計手数料（円）
            }
        """
        cache_key = f"sp_api_fees_{asin}_{price}"

        if use_cache:
            cached = self._get_cache(cache_key, "SP_API_FEES")
            if cached:
                return cached

        if not self.client:
            logger.warning("SP-API client not configured")
            return None

        try:
            self.client._wait_for_rate_limit()
            fees_api = self.client._get_fees_api()

            # リクエストボディ
            body = {
                "FeesEstimateRequest": {
                    "MarketplaceId": settings.sp_api_marketplace_id,
                    "IsAmazonFulfilled": True,  # FBA
                    "PriceToEstimateFees": {
                        "ListingPrice": {
                            "CurrencyCode": "JPY",
                            "Amount": price,
                        }
                    },
                    "Identifier": asin,
                }
            }

            response = fees_api.get_my_fees_estimate_for_asin(asin=asin, body=body)
            result = self._parse_fees(response.payload)
            self._set_cache(cache_key, "SP_API_FEES", result, {"asin": asin, "price": price})
            return result

        except Exception as e:
            logger.error(f"SP-API get_fees_estimate error for {asin}: {e}")
            return None

    def _parse_fees(self, payload: dict) -> dict:
        """手数料情報を解析"""
        result = {
            'referral_fee': 0,
            'fba_fee': 0,
            'other_fee': 0,
            'total_fee': 0,
        }

        if not payload:
            return result

        fees_estimate = payload.get('FeesEstimateResult', {}).get('FeesEstimate', {})
        if not fees_estimate:
            return result

        # 合計
        total = fees_estimate.get('TotalFeesEstimate', {}).get('Amount')
        if total:
            result['total_fee'] = int(float(total))

        # 詳細
        fee_details = fees_estimate.get('FeeDetailList', [])
        for fee in fee_details:
            fee_type = fee.get('FeeType', '')
            amount = fee.get('FinalFee', {}).get('Amount', 0)
            amount_int = int(float(amount)) if amount else 0

            if 'ReferralFee' in fee_type:
                result['referral_fee'] += amount_int
            elif 'FBA' in fee_type or 'Fulfillment' in fee_type:
                result['fba_fee'] += amount_int
            else:
                result['other_fee'] += amount_int

        return result

    def get_catalog_item(self, asin: str, use_cache: bool = True) -> Optional[dict]:
        """
        カタログ情報を取得（JAN/型番補完用）

        Returns:
            {
                'title': str,
                'brand': str,
                'model_number': str,
                'part_number': str,
                'ean': str,
                'upc': str,
            }
        """
        cache_key = f"sp_api_catalog_{asin}"

        if use_cache:
            cached = self._get_cache(cache_key, "SP_API_CATALOG")
            if cached:
                return cached

        if not self.client:
            logger.warning("SP-API client not configured")
            return None

        try:
            self.client._wait_for_rate_limit()
            catalog_api = self.client._get_catalog_api()
            response = catalog_api.get_catalog_item(
                asin=asin,
                includedData=["attributes", "identifiers", "summaries"],
            )

            result = self._parse_catalog(response.payload)
            self._set_cache(cache_key, "SP_API_CATALOG", result, {"asin": asin})
            return result

        except Exception as e:
            logger.error(f"SP-API get_catalog_item error for {asin}: {e}")
            return None

    def _parse_catalog(self, payload: dict) -> dict:
        """カタログ情報を解析"""
        result = {
            'title': None,
            'brand': None,
            'model_number': None,
            'part_number': None,
            'ean': None,
            'upc': None,
        }

        if not payload:
            return result

        # Summaries
        summaries = payload.get('summaries', [])
        for summary in summaries:
            if not result['title']:
                result['title'] = summary.get('itemName')
            if not result['brand']:
                result['brand'] = summary.get('brand')

        # Attributes
        attributes = payload.get('attributes', {})
        if attributes:
            # 型番
            model = attributes.get('model_number', [])
            if model:
                result['model_number'] = model[0].get('value')

            part = attributes.get('part_number', [])
            if part:
                result['part_number'] = part[0].get('value')

        # Identifiers
        identifiers = payload.get('identifiers', [])
        for id_group in identifiers:
            for identifier in id_group.get('identifiers', []):
                id_type = identifier.get('identifierType', '')
                id_value = identifier.get('identifier')
                if id_type == 'EAN':
                    result['ean'] = id_value
                elif id_type == 'UPC':
                    result['upc'] = id_value

        return result

    def get_listing_restrictions(self, asin: str, use_cache: bool = True) -> Optional[dict]:
        """
        出品制限を確認

        Returns:
            {
                'has_restriction': bool,  # 制限あり
                'restriction_type': str,  # 制限タイプ
                'reason': str,            # 理由
            }
        """
        cache_key = f"sp_api_restrictions_{asin}"

        if use_cache:
            cached = self._get_cache(cache_key, "SP_API_RESTRICTIONS")
            if cached:
                return cached

        if not self.client:
            logger.warning("SP-API client not configured")
            return None

        try:
            self.client._wait_for_rate_limit()
            restrictions_api = self.client._get_restrictions_api()
            response = restrictions_api.get_listings_restrictions(
                asin=asin,
                sellerId="",  # 自分のセラーID（設定から取得が必要）
                marketplaceIds=[settings.sp_api_marketplace_id],
            )

            result = self._parse_restrictions(response.payload)
            self._set_cache(cache_key, "SP_API_RESTRICTIONS", result, {"asin": asin})
            return result

        except Exception as e:
            logger.error(f"SP-API get_listing_restrictions error for {asin}: {e}")
            # 制限確認失敗はUNKNOWNとして返す
            return {
                'has_restriction': None,
                'restriction_type': 'UNKNOWN',
                'reason': str(e),
            }

    def _parse_restrictions(self, payload: dict) -> dict:
        """出品制限情報を解析"""
        result = {
            'has_restriction': False,
            'restriction_type': None,
            'reason': None,
        }

        if not payload:
            return result

        restrictions = payload.get('restrictions', [])
        if restrictions:
            result['has_restriction'] = True
            first = restrictions[0]
            result['restriction_type'] = first.get('conditionType', 'UNKNOWN')

            reasons = first.get('reasons', [])
            if reasons:
                result['reason'] = reasons[0].get('message')

        return result


def get_sp_api_service(db: Session) -> SpApiService:
    """SpApiServiceのファクトリ関数"""
    return SpApiService(db)
