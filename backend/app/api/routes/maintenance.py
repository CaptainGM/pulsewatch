from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import MaintenanceWindow, Monitor, utcnow
from app.schemas import MaintenanceCreate, MaintenanceOut
from app.services.cache import cache
from app.services.maintenance import sweep_maintenance
from app.services.status_page import STATUS_CACHE_KEY

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


def _serialize(window: MaintenanceWindow, monitor_name: str | None, now=None) -> dict:
    now = now or utcnow()
    return {
        "id": window.id,
        "title": window.title,
        "description": window.description,
        "monitor_id": window.monitor_id,
        "monitor_name": monitor_name,
        "starts_at": window.starts_at,
        "ends_at": window.ends_at,
        "active": window.starts_at <= now < window.ends_at,
        "created_at": window.created_at,
    }


@router.get("", response_model=list[MaintenanceOut])
async def list_maintenance(session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(MaintenanceWindow, Monitor.name)
            .outerjoin(Monitor, Monitor.id == MaintenanceWindow.monitor_id)
            .order_by(MaintenanceWindow.starts_at.desc())
        )
    ).all()
    now = utcnow()
    return [_serialize(window, name, now) for window, name in rows]


@router.post("", response_model=MaintenanceOut, status_code=status.HTTP_201_CREATED)
async def create_maintenance(
    payload: MaintenanceCreate, session: AsyncSession = Depends(get_session)
):
    monitor_name = None
    if payload.monitor_id is not None:
        monitor = await session.get(Monitor, payload.monitor_id)
        if monitor is None:
            raise HTTPException(status_code=404, detail="Monitör bulunamadı")
        monitor_name = monitor.name
    window = MaintenanceWindow(**payload.model_dump())
    session.add(window)
    await session.commit()
    await session.refresh(window)
    await sweep_maintenance(session)
    await cache.delete("dashboard:summary")
    await cache.delete(STATUS_CACHE_KEY)
    return _serialize(window, monitor_name)


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance(window_id: int, session: AsyncSession = Depends(get_session)):
    window = await session.get(MaintenanceWindow, window_id)
    if window is None:
        raise HTTPException(status_code=404, detail="Bakım penceresi bulunamadı")
    await session.delete(window)
    await session.commit()
    await sweep_maintenance(session)
    await cache.delete("dashboard:summary")
    await cache.delete(STATUS_CACHE_KEY)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
