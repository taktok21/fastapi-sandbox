from datetime import datetime
from typing import Optional, List
from enum import Enum

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class JobCreate(BaseModel):
    asins: List[str] = Field(..., description="ASINリスト", min_length=1, max_length=1000)
    point_rate_normal: float = Field(default=0.01, ge=0, le=1, description="通常ポイント率")
    point_rate_spu: float = Field(default=0.07, ge=0, le=1, description="SPUポイント率")
    threshold_profit_amount: int = Field(default=1000, ge=0, description="利益額閾値（円）")
    threshold_profit_rate: float = Field(default=0.15, ge=0, le=1, description="利益率閾値")
    threshold_rank: int = Field(default=50000, ge=1, description="ランキング閾値")
    threshold_sales_30: int = Field(default=10, ge=0, description="30日販売数閾値")


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    point_rate_normal: float
    point_rate_spu: float
    point_rate_total: float
    threshold_profit_amount: int
    threshold_profit_rate: float
    threshold_rank: int
    threshold_sales_30: int
    total_count: int
    success_count: int
    fail_count: int
    review_count: int
    pass_count: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
