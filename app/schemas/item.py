from datetime import datetime
from typing import Optional, List, Any
from enum import Enum

from pydantic import BaseModel, Field


class ProcessStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PassStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class RakutenMatchType(str, Enum):
    JAN = "JAN"
    MODEL = "MODEL"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class ItemResponse(BaseModel):
    id: int
    job_id: str
    asin: str
    process_status: ProcessStatus
    fail_reason: Optional[str]

    # 商品基本情報
    title: Optional[str]
    jan_code: Optional[str]
    model_number: Optional[str]
    brand: Optional[str]
    category: Optional[str]

    # Amazon
    amazon_price_fba_lowest: Optional[int]
    amazon_fee_total: Optional[int]
    amazon_payout: Optional[int]

    # 楽天
    rakuten_match_type: Optional[RakutenMatchType]
    rakuten_item_name: Optional[str]
    rakuten_shop_name: Optional[str]
    rakuten_price: Optional[int]
    rakuten_shipping: Optional[int]
    rakuten_cost_net: Optional[int]

    # 利益
    profit_amount: Optional[int]
    profit_rate: Optional[float]

    # ランキング・販売数
    rank_current: Optional[int]
    sales_est_30: Optional[int]
    sales_est_90: Optional[int]
    sales_est_180: Optional[int]

    # セラー
    seller_count: Optional[int]
    fba_seller_count: Optional[int]

    # 判定
    pass_status: Optional[PassStatus]
    pass_fail_reasons: Optional[Any]

    # 候補
    is_candidate: bool
    user_memo: Optional[str]

    fetched_at: Optional[datetime]

    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    items: List[ItemResponse]
    total: int
    pass_count: int
    fail_count: int
    review_count: int


class ItemUpdateCandidate(BaseModel):
    is_candidate: bool = Field(..., description="仕入れ候補フラグ")
    user_memo: Optional[str] = Field(None, description="ユーザーメモ")
