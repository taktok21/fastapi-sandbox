from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Enum, DateTime, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApiCache(Base):
    __tablename__ = "api_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    api_type: Mapped[str] = mapped_column(
        Enum(
            "KEEPA",
            "SP_API_FEES",
            "SP_API_PRICING",
            "SP_API_CATALOG",
            "SP_API_RESTRICTIONS",
            "RAKUTEN_PRODUCT",
            "RAKUTEN_SEARCH",
            name="api_cache_type"
        ),
        nullable=False
    )
    request_params: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    response_data: Mapped[Any] = mapped_column(JSON, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_cache_type", "api_type"),
        Index("idx_cache_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<ApiCache(key={self.cache_key}, type={self.api_type})>"
