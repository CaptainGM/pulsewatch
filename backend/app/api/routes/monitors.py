import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import AlertChannel, Check, Monitor, utcnow
from app.schemas import (
    CheckOut,
    CheckRunOut,
    MonitorCreate,
    MonitorImportIn,
    MonitorOut,
    MonitorStats,
    MonitorUpdate,
)
from app.security import require_admin
from app.services.cache import cache
from app.services.metrics import get_monitor_stats as compute_monitor_stats
from app.services.monitoring import (
    CheckInProgressError,
    MonitorNotFoundError,
    UnsupportedMonitorTypeError,
    evaluate_heartbeat_now,
    perform_check,
)
from app.services.status_page import STATUS_CACHE_KEY

router = APIRouter(prefix="/monitors", tags=["monitors"])


async def _get_monitor(session: AsyncSession, monitor_id: int) -> Monitor:
    monitor = await session.get(Monitor, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="Monitör bulunamadı")
    return monitor


async def _invalidate(monitor_id: int | None = None) -> None:
    await cache.delete("dashboard:summary")
    await cache.delete(STATUS_CACHE_KEY)
    if monitor_id is not None:
        await cache.delete_prefix(f"monitor:{monitor_id}:stats:")


async def _validate_channels(session: AsyncSession, channel_ids: list[int]) -> None:
    if not channel_ids:
        return
    existing = set(
        (await session.execute(select(AlertChannel.id).where(AlertChannel.id.in_(channel_ids))))
        .scalars()
        .all()
    )
    missing = sorted(set(channel_ids) - existing)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Bildirim kanalı bulunamadı: {', '.join(map(str, missing))}",
        )


@router.get("", response_model=list[MonitorOut])
async def list_monitors(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Monitor).order_by(Monitor.created_at.asc()))
    return result.scalars().all()


@router.post("", response_model=MonitorOut, status_code=status.HTTP_201_CREATED)
async def create_monitor(payload: MonitorCreate, session: AsyncSession = Depends(get_session)):
    await _validate_channels(session, payload.alert_channel_ids)
    data = payload.model_dump()
    if data["monitor_type"] == "heartbeat":
        data["heartbeat_token"] = secrets.token_urlsafe(32)
        data["next_check_at"] = None
        data["method"] = "GET"
    else:
        data["next_check_at"] = utcnow()
    monitor = Monitor(
        **data,
        status="unknown",
    )
    session.add(monitor)
    await session.commit()
    await session.refresh(monitor)
    await _invalidate(monitor.id)
    return monitor


TRANSFER_FIELDS = (
    "name",
    "description",
    "url",
    "monitor_type",
    "method",
    "body",
    "expected_codes",
    "expected_keyword",
    "json_path",
    "expected_json_value",
    "slow_threshold_ms",
    "heartbeat_grace_seconds",
    "interval_seconds",
    "timeout_seconds",
    "active",
    "alert_after_failures",
    "tags",
)


def _new_monitor(payload: MonitorCreate) -> Monitor:
    data = payload.model_dump()
    data["alert_channel_ids"] = []
    if data["monitor_type"] == "heartbeat":
        data["heartbeat_token"] = secrets.token_urlsafe(32)
        data["next_check_at"] = None
        data["method"] = "GET"
    else:
        data["next_check_at"] = utcnow()
    return Monitor(**data, status="unknown")


@router.get("/export", dependencies=[Depends(require_admin)])
async def export_monitors(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Monitor).order_by(Monitor.id))).scalars().all()
    return {
        "version": 1,
        "exported_at": utcnow().isoformat(),
        "monitors": [
            {field: getattr(monitor, field) for field in TRANSFER_FIELDS} for monitor in rows
        ],
    }


@router.post("/import", dependencies=[Depends(require_admin)], status_code=status.HTTP_201_CREATED)
async def import_monitors(payload: MonitorImportIn, session: AsyncSession = Depends(get_session)):
    known = {
        (name, url)
        for name, url in (await session.execute(select(Monitor.name, Monitor.url))).all()
    }
    created, skipped, errors = 0, 0, []
    for index, item in enumerate(payload.monitors):
        clean = {key: value for key, value in item.items() if key in TRANSFER_FIELDS}
        try:
            data = MonitorCreate.model_validate(clean)
        except ValidationError as exc:
            errors.append(
                {"index": index, "name": str(item.get("name", "")), "error": exc.errors()[0]["msg"]}
            )
            continue
        key = (data.name, data.url)
        if key in known:
            skipped += 1
            continue
        session.add(_new_monitor(data))
        known.add(key)
        created += 1
    await session.commit()
    await _invalidate()
    return {"created": created, "skipped": skipped, "errors": errors}


@router.get("/{monitor_id}", response_model=MonitorOut)
async def get_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)):
    return await _get_monitor(session, monitor_id)


@router.patch("/{monitor_id}", response_model=MonitorOut)
async def update_monitor(
    monitor_id: int,
    payload: MonitorUpdate,
    session: AsyncSession = Depends(get_session),
):
    monitor = await _get_monitor(session, monitor_id)
    values = payload.model_dump(exclude_unset=True)
    if "alert_channel_ids" in values:
        await _validate_channels(session, values["alert_channel_ids"] or [])

    previous_active = monitor.active
    previous_type = monitor.monitor_type
    for field, value in values.items():
        setattr(monitor, field, value)

    if monitor.monitor_type == "heartbeat":
        if not monitor.heartbeat_token:
            monitor.heartbeat_token = secrets.token_urlsafe(32)
        monitor.next_check_at = None
        if previous_type != "heartbeat":
            monitor.status = "unknown" if monitor.active else "paused"
    elif previous_type == "heartbeat":
        monitor.next_check_at = utcnow()
        monitor.status = "unknown" if monitor.active else "paused"

    if "active" in values:
        if monitor.active:
            monitor.next_check_at = utcnow() if monitor.monitor_type == "http" else None
            if not previous_active:
                monitor.status = "unknown"
        else:
            monitor.status = "paused"
            monitor.next_check_at = None
    elif "interval_seconds" in values and monitor.active:
        if monitor.monitor_type == "http":
            monitor.next_check_at = utcnow()

    monitor.updated_at = utcnow()
    await session.commit()
    await session.refresh(monitor)
    await _invalidate(monitor.id)
    return monitor


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monitor(monitor_id: int, session: AsyncSession = Depends(get_session)):
    monitor = await _get_monitor(session, monitor_id)
    await session.delete(monitor)
    await session.commit()
    await _invalidate(monitor_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{monitor_id}/check", response_model=CheckRunOut)
async def check_monitor_now(monitor_id: int, session: AsyncSession = Depends(get_session)):
    monitor = await _get_monitor(session, monitor_id)
    if monitor.monitor_type == "heartbeat":
        fresh = await evaluate_heartbeat_now(monitor_id)
        raise HTTPException(
            status_code=400,
            detail=(
                "Heartbeat monitörleri ping adresiyle beslenir. "
                f"Son 24 saat penceresi: {'aktif' if fresh else 'sinyal yok'}."
            ),
        )
    try:
        outcome = await perform_check(monitor_id)
    except MonitorNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedMonitorTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CheckInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    check = await session.get(Check, outcome.check_id)
    monitor = await session.get(Monitor, monitor_id)
    if check is None or monitor is None:
        raise HTTPException(status_code=500, detail="Kontrol sonucu kaydedilemedi")
    await session.refresh(check)
    await session.refresh(monitor)
    await _invalidate(monitor_id)
    return {"check": check, "monitor": monitor}


@router.post("/{monitor_id}/heartbeat/rotate", response_model=MonitorOut)
async def rotate_heartbeat_token(monitor_id: int, session: AsyncSession = Depends(get_session)):
    monitor = await _get_monitor(session, monitor_id)
    if monitor.monitor_type != "heartbeat":
        raise HTTPException(status_code=400, detail="Bu monitör heartbeat türünde değil")
    monitor.heartbeat_token = secrets.token_urlsafe(32)
    monitor.updated_at = utcnow()
    await session.commit()
    await session.refresh(monitor)
    await _invalidate(monitor_id)
    return monitor


@router.get("/{monitor_id}/checks", response_model=list[CheckOut])
async def list_checks(
    monitor_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    await _get_monitor(session, monitor_id)
    result = await session.execute(
        select(Check)
        .where(Check.monitor_id == monitor_id)
        .order_by(Check.checked_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/{monitor_id}/stats", response_model=MonitorStats)
async def monitor_stats(
    monitor_id: int,
    hours: int = Query(default=24, ge=1, le=720),
    buckets: int = Query(default=48, ge=6, le=168),
    session: AsyncSession = Depends(get_session),
):
    await _get_monitor(session, monitor_id)
    return await compute_monitor_stats(session, monitor_id, hours, buckets)
