from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Enum, DECIMAL, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RakutenCandidate(Base):
    __tablename__ = "rakuten_candidate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_job.job_id", ondelete="CASCADE"), nullable=False)
    asin: Mapped[str] = mapped_column(String(20), nullable=False)

    match_type: Mapped[str] = mapped_column(
        Enum("JAN", "MODEL", "KEYWORD", name="rakuten_candidate_match_type"),
        nullable=False
    )
    match_value: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # 楽天商品情報
    rakuten_item_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    item_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    item_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    shop_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    shop_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # 価格情報
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shipping_status: Mapped[str] = mapped_column(
        Enum("FREE", "PAID", "UNKNOWN", name="rakuten_shipping_status"),
        nullable=False,
        default="UNKNOWN"
    )
    total_cost: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ポイント
    point_rate: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)
    point_rate_used: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 4), nullable=True)
    point_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 採用フラグ
    is_chosen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_rc_job_asin", "job_id", "asin"),
        Index("idx_rc_match_type", "match_type"),
        Index("idx_rc_chosen", "is_chosen"),
        Index("idx_rc_price", "price"),
    )

    def __repr__(self) -> str:
        return f"<RakutenCandidate(asin={self.asin}, shop={self.shop_name}, price={self.price})>"
