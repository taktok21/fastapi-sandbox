from datetime import datetime, date

from sqlalchemy import String, Integer, Date, Enum, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResearchTimeseries(Base):
    __tablename__ = "research_timeseries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_job.job_id", ondelete="CASCADE"), nullable=False)
    asin: Mapped[str] = mapped_column(String(20), nullable=False)

    metric: Mapped[str] = mapped_column(
        Enum("PRICE", "RANK", "SELLER_COUNT", "FBA_SELLER_COUNT", name="timeseries_metric"),
        nullable=False
    )
    recorded_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(
        Enum("KEEPA", "SP_API", "MANUAL", name="timeseries_source"),
        nullable=False,
        default="KEEPA"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("uk_timeseries", "job_id", "asin", "metric", "recorded_date", unique=True),
        Index("idx_ts_job_asin", "job_id", "asin"),
        Index("idx_ts_metric", "metric"),
        Index("idx_ts_date", "recorded_date"),
    )

    def __repr__(self) -> str:
        return f"<ResearchTimeseries(asin={self.asin}, metric={self.metric}, date={self.recorded_date})>"
