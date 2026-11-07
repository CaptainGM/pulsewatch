from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Monitor
from app.schemas import StatusPageOut
from app.services.badges import badge_svg
from app.services.monitoring import MonitorNotFoundError, record_heartbeat
from app.services.status_page import cached_status_page

router = APIRouter(tags=["public"])


@router.get("/status-page", response_model=StatusPageOut)
async def public_status_page(session: AsyncSession = Depends(get_session)):
    return await cached_status_page(session)


@router.get("/badge/overall.svg")
async def overall_badge(
    theme: str = Query(default="dark", pattern="^(dark|light)$"),
    session: AsyncSession = Depends(get_session),
):
    data = await cached_status_page(session)
    svg = badge_svg(data["overall_status"], theme=theme)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/badge/monitors/{monitor_id}.svg")
async def monitor_badge(
    monitor_id: int,
    theme: str = Query(default="dark", pattern="^(dark|light)$"),
    session: AsyncSession = Depends(get_session),
):
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitör bulunamadı")
    status = "paused" if not monitor.active else monitor.status
    svg = badge_svg(status, label=monitor.name, theme=theme)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/ping/{token}")
@router.post("/ping/{token}")
async def heartbeat_ping(token: str):
    try:
        monitor, check = await record_heartbeat(token)
    except MonitorNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Heartbeat adresi geçersiz") from exc
    return {
        "ok": True,
        "monitor": {"id": monitor.id, "name": monitor.name, "status": monitor.status},
        "check": {"id": check.id, "received_at": check.checked_at},
    }
