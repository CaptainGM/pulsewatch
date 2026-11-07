from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Incident, Monitor
from app.schemas import MonitorCard, MonitorStats, StatusPageOut
from app.security import require_api_access
from app.services.metrics import build_dashboard, get_monitor_stats, serialize_incident
from app.services.status_page import cached_status_page

router = APIRouter(prefix="/v1", tags=["public-api"])


@router.get("/status", response_model=StatusPageOut)
async def status(session: AsyncSession = Depends(get_session)):
    return await cached_status_page(session)


@router.get("/monitors", response_model=list[MonitorCard])
async def monitors(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_api_access),
):
    data = await build_dashboard(session)
    return data["monitors"]


@router.get("/monitors/{monitor_id}/stats", response_model=MonitorStats)
async def monitor_stats(
    monitor_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    buckets: int = Query(default=48, ge=6, le=168),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_api_access),
):
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitör bulunamadı")
    return await get_monitor_stats(session, monitor_id, hours, buckets)


@router.get("/incidents")
async def incidents(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_api_access),
):
    rows = (
        await session.execute(
            select(Incident, Monitor.name)
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .order_by(Incident.started_at.desc())
            .limit(limit)
        )
    ).all()
    return [serialize_incident(incident, name) for incident, name in rows]
