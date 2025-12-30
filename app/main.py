from fastapi import FastAPI, Request, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api import api_router
from app.database import get_db
from app.services.job_service import JobService
from app.services.item_service import ItemService
from app.schemas.job import JobCreate
from app.workers.tasks import enqueue_research_job

app = FastAPI(
    title="物販リサーチアプリ",
    description="Amazon-楽天間の利益判定ツール",
    version="1.0.0",
)

# 静的ファイル
app.mount("/static", StaticFiles(directory="static"), name="static")

# テンプレート
templates = Jinja2Templates(directory="app/templates")

# API Router
app.include_router(api_router, prefix="/api")


# ==================== Web Pages ====================

@app.get("/")
def index():
    """トップページ→ジョブ一覧へリダイレクト"""
    return RedirectResponse(url="/jobs", status_code=302)


@app.get("/jobs")
def jobs_list_page(request: Request, db: Session = Depends(get_db)):
    """ジョブ一覧ページ"""
    jobs = JobService.get_jobs(db, skip=0, limit=50)
    return templates.TemplateResponse(
        "jobs/list.html",
        {"request": request, "jobs": jobs}
    )


@app.get("/jobs/create")
def jobs_create_page(request: Request):
    """ジョブ作成ページ"""
    return templates.TemplateResponse(
        "jobs/create.html",
        {"request": request}
    )


@app.post("/jobs/create")
def jobs_create_submit(
    request: Request,
    asins: str = Form(...),
    threshold_profit_amount: int = Form(1000),
    threshold_profit_rate: float = Form(15),
    threshold_rank: int = Form(50000),
    threshold_sales_30: int = Form(10),
    point_rate_normal: float = Form(1),
    point_rate_spu: float = Form(7),
    db: Session = Depends(get_db)
):
    """ジョブ作成処理"""
    # ASINをパース
    asin_list = []
    for line in asins.split('\n'):
        for part in line.split(','):
            cleaned = part.strip().upper()
            if cleaned and len(cleaned) == 10 and cleaned.startswith('B0'):
                asin_list.append(cleaned)

    if not asin_list:
        return templates.TemplateResponse(
            "jobs/create.html",
            {"request": request, "error": "有効なASINが見つかりません"}
        )

    # ジョブ作成
    job_data = JobCreate(
        asins=asin_list,
        point_rate_normal=point_rate_normal / 100,
        point_rate_spu=point_rate_spu / 100,
        threshold_profit_amount=threshold_profit_amount,
        threshold_profit_rate=threshold_profit_rate / 100,
        threshold_rank=threshold_rank,
        threshold_sales_30=threshold_sales_30,
    )
    job = JobService.create_job(db, job_data)

    # キューに追加
    enqueue_research_job(job.job_id)

    return RedirectResponse(url=f"/jobs/{job.job_id}", status_code=302)


@app.get("/jobs/{job_id}")
def jobs_detail_page(request: Request, job_id: str, db: Session = Depends(get_db)):
    """ジョブ詳細ページ"""
    job = JobService.get_job(db, job_id)
    if not job:
        return RedirectResponse(url="/jobs", status_code=302)
    return templates.TemplateResponse(
        "jobs/detail.html",
        {"request": request, "job": job}
    )


@app.post("/jobs/{job_id}/retry")
def jobs_retry_submit(job_id: str, db: Session = Depends(get_db)):
    """失敗分リトライ"""
    job = JobService.get_job(db, job_id)
    if job:
        count = JobService.retry_failed_items(db, job_id)
        if count > 0:
            JobService.update_job_status(db, job_id, "PENDING")
            enqueue_research_job(job_id)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=302)


@app.get("/jobs/{job_id}/items")
def items_list_page(
    request: Request,
    job_id: str,
    pass_status: str = None,
    db: Session = Depends(get_db)
):
    """結果一覧ページ"""
    job = JobService.get_job(db, job_id)
    if not job:
        return RedirectResponse(url="/jobs", status_code=302)

    items = ItemService.get_items_by_job(
        db,
        job_id=job_id,
        pass_status=pass_status if pass_status else None,
        skip=0,
        limit=100,
    )
    total = ItemService.get_items_count(db, job_id, pass_status if pass_status else None)
    counts = ItemService.get_pass_status_counts(db, job_id)

    return templates.TemplateResponse(
        "items/list.html",
        {
            "request": request,
            "job": job,
            "items": items,
            "total": total,
            "pass_count": counts.get("PASS", 0),
            "fail_count": counts.get("FAIL", 0),
            "review_count": counts.get("REVIEW", 0),
            "current_filter": pass_status,
        }
    )


@app.get("/items/{item_id}")
def items_detail_page(request: Request, item_id: int, db: Session = Depends(get_db)):
    """商品詳細ページ"""
    item = ItemService.get_item(db, item_id)
    if not item:
        return RedirectResponse(url="/jobs", status_code=302)
    return templates.TemplateResponse(
        "items/detail.html",
        {"request": request, "item": item}
    )


# ==================== Health Check ====================

@app.get("/health")
def health_check():
    return {"status": "ok"}
