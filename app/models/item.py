from datetime import datetime
from typing import Optional, Any

from sqlalchemy import String, Integer, Text, Enum, DECIMAL, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResearchItem(Base):
    __tablename__ = "research_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_job.job_id", ondelete="CASCADE"), nullable=False)
    asin: Mapped[str] = mapped_column(String(20), nullable=False)

    # 処理ステータス
    process_status: Mapped[str] = mapped_column(
        Enum("PENDING", "PROCESSING", "SUCCESS", "FAILED", "SKIPPED", name="process_status"),
        nullable=False,
        default="PENDING"
    )
    fail_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 商品基本情報
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    jan_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    model_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Amazon価格・手数料
    amazon_price_fba_lowest: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amazon_fee_referral: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amazon_fee_fba: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amazon_fee_other: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amazon_fee_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amazon_payout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 楽天仕入れ
    rakuten_match_type: Mapped[Optional[str]] = mapped_column(
        Enum("JAN", "MODEL", "NONE", "UNKNOWN", name="rakuten_match_type"),
        nullable=True
    )
    rakuten_item_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    rakuten_shop_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    rakuten_item_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    rakuten_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rakuten_shipping: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rakuten_shipping_status: Mapped[Optional[str]] = mapped_column(
        Enum("FREE", "PAID", "UNKNOWN", name="shipping_status"),
        nullable=True,
        default="UNKNOWN"
    )
    rakuten_point: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rakuten_cost_gross: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rakuten_cost_net: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 利益計算
    profit_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    profit_rate: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)

    # ランキング・販売数
    rank_current: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rank_avg_30: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rank_avg_90: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sales_est_30: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sales_est_90: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sales_est_180: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # セラー情報
    seller_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fba_seller_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fba_lowest_seller_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 季節性
    seasonality_flag: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    seasonality_score: Mapped[Optional[float]] = mapped_column(DECIMAL(3, 2), nullable=True)
    seasonality_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # リスクフラグ
    flag_hazardous: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_hazardous_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_oversized: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_oversized_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status_oversized"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_fragile: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_fragile_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status_fragile"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_high_return: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_high_return_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status_return"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_maker_restriction: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_maker_restriction_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status_maker"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_authenticity_risk: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_authenticity_risk_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status_auth"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_listing_restriction: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    flag_listing_restriction_status: Mapped[Optional[str]] = mapped_column(
        Enum("AUTO", "MANUAL", "UNKNOWN", name="flag_status_listing"),
        nullable=True,
        default="UNKNOWN"
    )
    flag_memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 判定結果
    pass_status: Mapped[Optional[str]] = mapped_column(
        Enum("PASS", "FAIL", "REVIEW", name="pass_status"),
        nullable=True
    )
    pass_fail_reasons: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    # 仕入れ候補
    is_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # タイムスタンプ
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    job: Mapped["ResearchJob"] = relationship("ResearchJob", back_populates="items")

    __table_args__ = (
        Index("uk_job_asin", "job_id", "asin", unique=True),
        Index("idx_item_job", "job_id"),
        Index("idx_item_asin", "asin"),
        Index("idx_item_process_status", "process_status"),
        Index("idx_item_pass_status", "pass_status"),
        Index("idx_item_profit", "profit_amount"),
        Index("idx_item_rank", "rank_current"),
        Index("idx_item_candidate", "is_candidate"),
        Index("idx_item_fetched", "fetched_at"),
    )

    def __repr__(self) -> str:
        return f"<ResearchItem(asin={self.asin}, status={self.process_status})>"
