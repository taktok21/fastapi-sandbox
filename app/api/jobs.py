from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.job import JobCreate, JobResponse, JobListResponse
from app.services.job_service import JobService
from app.workers.tasks import enqueue_research_job

router = APIRouter()


@router.post("/", response_model=JobResponse)
def create_job(job_data: JobCreate, db: Session = Depends(get_db)):
    """ジョブを作成してキューに追加"""
    job = JobService.create_job(db, job_data)

    # RQにジョブを追加
    enqueue_research_job(job.job_id)

    return job


@router.get("/", response_model=JobListResponse)
def list_jobs(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """ジョブ一覧を取得"""
    jobs = JobService.get_jobs(db, skip=skip, limit=limit)
    total = JobService.get_jobs_count(db)
    return JobListResponse(jobs=jobs, total=total)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """ジョブ詳細を取得"""
    job = JobService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/retry")
def retry_failed_items(job_id: str, db: Session = Depends(get_db)):
    """失敗したアイテムを再試行"""
    job = JobService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    count = JobService.retry_failed_items(db, job_id)

    if count > 0:
        # ジョブを再実行
        JobService.update_job_status(db, job_id, "PENDING")
        enqueue_research_job(job_id)

    return {"retried": count}
