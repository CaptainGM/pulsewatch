from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import DashboardOut
from app.services.cache import cache
from app.services.metrics import build_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

CACHE_KEY = "dashboard:summary"


@router.get("", response_model=DashboardOut)
async def get_dashboard(session: AsyncSession = Depends(get_session)):
    cached = await cache.get_json(CACHE_KEY)
    if cached is not None:
        return cached
    data = await build_dashboard(session)
    await cache.set_json(CACHE_KEY, data, ttl=5)
    return data
