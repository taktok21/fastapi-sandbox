from datetime import datetime
from typing import Optional, List
import uuid

from sqlalchemy import String, Integer, Enum, DECIMAL, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResearchJob(Base):
    __tablename__ = "research_job"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(
        Enum("PENDING", "RUNNING", "DONE", "FAILED", name="job_status"),
        nullable=False,
        default="PENDING"
    )

    # ジョブ設定
    point_rate_normal: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False, default=0.01)
    point_rate_spu: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False, default=0.07)
    point_rate_total: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False, default=0.08)

    # 判定基準
    threshold_profit_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    threshold_profit_rate: Mapped[float] = mapped_column(DECIMAL(5, 4), nullable=False, default=0.15)
    threshold_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=50000)
    threshold_sales_30: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # 集計
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # タイムスタンプ
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    items: Mapped[List["ResearchItem"]] = relationship("ResearchItem", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_job_status", "status"),
        Index("idx_job_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ResearchJob(job_id={self.job_id}, status={self.status})>"
