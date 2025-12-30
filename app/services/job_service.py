from datetime import datetime
from typing import List, Optional
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.job import ResearchJob
from app.models.item import ResearchItem
from app.schemas.job import JobCreate


class JobService:

    @staticmethod
    def create_job(db: Session, job_data: JobCreate) -> ResearchJob:
        """ジョブを作成し、ASINを登録する"""
        # 重複排除
        unique_asins = list(dict.fromkeys(job_data.asins))

        # ジョブ作成
        job = ResearchJob(
            job_id=str(uuid.uuid4()),
            status="PENDING",
            point_rate_normal=job_data.point_rate_normal,
            point_rate_spu=job_data.point_rate_spu,
            point_rate_total=job_data.point_rate_normal + job_data.point_rate_spu,
            threshold_profit_amount=job_data.threshold_profit_amount,
            threshold_profit_rate=job_data.threshold_profit_rate,
            threshold_rank=job_data.threshold_rank,
            threshold_sales_30=job_data.threshold_sales_30,
            total_count=len(unique_asins),
        )
        db.add(job)
        db.flush()

        # ASIN登録
        for asin in unique_asins:
            item = ResearchItem(
                job_id=job.job_id,
                asin=asin.strip().upper(),
                process_status="PENDING",
            )
            db.add(item)

        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_job(db: Session, job_id: str) -> Optional[ResearchJob]:
        """ジョブを取得"""
        return db.query(ResearchJob).filter(ResearchJob.job_id == job_id).first()

    @staticmethod
    def get_jobs(db: Session, skip: int = 0, limit: int = 50) -> List[ResearchJob]:
        """ジョブ一覧を取得"""
        return (
            db.query(ResearchJob)
            .order_by(ResearchJob.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_jobs_count(db: Session) -> int:
        """ジョブ総数を取得"""
        return db.query(func.count(ResearchJob.job_id)).scalar()

    @staticmethod
    def update_job_status(db: Session, job_id: str, status: str) -> Optional[ResearchJob]:
        """ジョブステータスを更新"""
        job = db.query(ResearchJob).filter(ResearchJob.job_id == job_id).first()
        if job:
            job.status = status
            if status == "RUNNING":
                job.started_at = datetime.utcnow()
            elif status in ("DONE", "FAILED"):
                job.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
        return job

    @staticmethod
    def update_job_counts(db: Session, job_id: str) -> Optional[ResearchJob]:
        """ジョブの集計を更新"""
        job = db.query(ResearchJob).filter(ResearchJob.job_id == job_id).first()
        if not job:
            return None

        # 各ステータスの件数を集計
        counts = (
            db.query(
                ResearchItem.process_status,
                ResearchItem.pass_status,
                func.count(ResearchItem.id)
            )
            .filter(ResearchItem.job_id == job_id)
            .group_by(ResearchItem.process_status, ResearchItem.pass_status)
            .all()
        )

        success_count = 0
        fail_count = 0
        pass_count = 0
        review_count = 0

        for process_status, pass_status, count in counts:
            if process_status == "SUCCESS":
                success_count += count
                if pass_status == "PASS":
                    pass_count += count
                elif pass_status == "REVIEW":
                    review_count += count
            elif process_status == "FAILED":
                fail_count += count

        job.success_count = success_count
        job.fail_count = fail_count
        job.pass_count = pass_count
        job.review_count = review_count

        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_pending_items(db: Session, job_id: str, limit: int = 100) -> List[ResearchItem]:
        """処理待ちのアイテムを取得"""
        return (
            db.query(ResearchItem)
            .filter(
                ResearchItem.job_id == job_id,
                ResearchItem.process_status == "PENDING"
            )
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_failed_items(db: Session, job_id: str) -> List[ResearchItem]:
        """失敗したアイテムを取得"""
        return (
            db.query(ResearchItem)
            .filter(
                ResearchItem.job_id == job_id,
                ResearchItem.process_status == "FAILED"
            )
            .all()
        )

    @staticmethod
    def retry_failed_items(db: Session, job_id: str) -> int:
        """失敗したアイテムを再試行対象にする"""
        count = (
            db.query(ResearchItem)
            .filter(
                ResearchItem.job_id == job_id,
                ResearchItem.process_status == "FAILED"
            )
            .update({"process_status": "PENDING", "fail_reason": None})
        )
        db.commit()
        return count
