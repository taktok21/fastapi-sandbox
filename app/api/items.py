from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.item import ItemResponse, ItemListResponse, ItemUpdateCandidate
from app.services.item_service import ItemService

router = APIRouter()


@router.get("/job/{job_id}", response_model=ItemListResponse)
def list_items_by_job(
    job_id: str,
    pass_status: Optional[str] = Query(None, description="PASS/FAIL/REVIEW"),
    is_candidate: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    sort_by: str = Query("profit_amount", description="ソート列"),
    sort_order: str = Query("desc", description="asc/desc"),
    db: Session = Depends(get_db)
):
    """ジョブのアイテム一覧を取得"""
    items = ItemService.get_items_by_job(
        db,
        job_id=job_id,
        pass_status=pass_status,
        is_candidate=is_candidate,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    total = ItemService.get_items_count(db, job_id, pass_status, is_candidate)
    counts = ItemService.get_pass_status_counts(db, job_id)

    return ItemListResponse(
        items=items,
        total=total,
        pass_count=counts.get("PASS", 0),
        fail_count=counts.get("FAIL", 0),
        review_count=counts.get("REVIEW", 0),
    )


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)):
    """アイテム詳細を取得"""
    item = ItemService.get_item(db, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.patch("/{item_id}/candidate", response_model=ItemResponse)
def update_candidate(
    item_id: int,
    data: ItemUpdateCandidate,
    db: Session = Depends(get_db)
):
    """仕入れ候補フラグを更新"""
    item = ItemService.update_candidate(
        db,
        item_id=item_id,
        is_candidate=data.is_candidate,
        user_memo=data.user_memo,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.get("/candidates/", response_model=ItemListResponse)
def list_candidates(
    job_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """仕入れ候補一覧を取得"""
    items = ItemService.get_candidates(db, job_id)
    return ItemListResponse(
        items=items,
        total=len(items),
        pass_count=len([i for i in items if i.pass_status == "PASS"]),
        fail_count=len([i for i in items if i.pass_status == "FAIL"]),
        review_count=len([i for i in items if i.pass_status == "REVIEW"]),
    )
