from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.item import ResearchItem


class ItemService:

    @staticmethod
    def get_item(db: Session, item_id: int) -> Optional[ResearchItem]:
        """アイテムを取得"""
        return db.query(ResearchItem).filter(ResearchItem.id == item_id).first()

    @staticmethod
    def get_item_by_asin(db: Session, job_id: str, asin: str) -> Optional[ResearchItem]:
        """job_id + ASINでアイテムを取得"""
        return (
            db.query(ResearchItem)
            .filter(ResearchItem.job_id == job_id, ResearchItem.asin == asin)
            .first()
        )

    @staticmethod
    def get_items_by_job(
        db: Session,
        job_id: str,
        pass_status: Optional[str] = None,
        is_candidate: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "profit_amount",
        sort_order: str = "desc",
    ) -> List[ResearchItem]:
        """ジョブのアイテム一覧を取得"""
        query = db.query(ResearchItem).filter(ResearchItem.job_id == job_id)

        if pass_status:
            query = query.filter(ResearchItem.pass_status == pass_status)
        if is_candidate is not None:
            query = query.filter(ResearchItem.is_candidate == is_candidate)

        # ソート（MySQLはNULLS LAST非対応のため、CASE文で代替）
        sort_column = getattr(ResearchItem, sort_by, ResearchItem.profit_amount)
        from sqlalchemy import case
        null_order = case((sort_column.is_(None), 1), else_=0)

        if sort_order == "desc":
            query = query.order_by(null_order, sort_column.desc())
        else:
            query = query.order_by(null_order, sort_column.asc())

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_items_count(
        db: Session,
        job_id: str,
        pass_status: Optional[str] = None,
        is_candidate: Optional[bool] = None,
    ) -> int:
        """アイテム総数を取得"""
        query = db.query(func.count(ResearchItem.id)).filter(ResearchItem.job_id == job_id)

        if pass_status:
            query = query.filter(ResearchItem.pass_status == pass_status)
        if is_candidate is not None:
            query = query.filter(ResearchItem.is_candidate == is_candidate)

        return query.scalar()

    @staticmethod
    def get_pass_status_counts(db: Session, job_id: str) -> dict:
        """pass_statusごとの件数を取得"""
        counts = (
            db.query(ResearchItem.pass_status, func.count(ResearchItem.id))
            .filter(ResearchItem.job_id == job_id)
            .group_by(ResearchItem.pass_status)
            .all()
        )
        return {status: count for status, count in counts}

    @staticmethod
    def update_candidate(
        db: Session,
        item_id: int,
        is_candidate: bool,
        user_memo: Optional[str] = None
    ) -> Optional[ResearchItem]:
        """仕入れ候補フラグを更新"""
        item = db.query(ResearchItem).filter(ResearchItem.id == item_id).first()
        if item:
            item.is_candidate = is_candidate
            if user_memo is not None:
                item.user_memo = user_memo
            db.commit()
            db.refresh(item)
        return item

    @staticmethod
    def get_candidates(db: Session, job_id: Optional[str] = None) -> List[ResearchItem]:
        """仕入れ候補を取得"""
        query = db.query(ResearchItem).filter(ResearchItem.is_candidate == True)
        if job_id:
            query = query.filter(ResearchItem.job_id == job_id)
        return query.order_by(ResearchItem.profit_amount.desc()).all()
