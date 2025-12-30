from fastapi import APIRouter

from app.api.jobs import router as jobs_router
from app.api.items import router as items_router

api_router = APIRouter()
api_router.include_router(jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(items_router, prefix="/items", tags=["items"])
