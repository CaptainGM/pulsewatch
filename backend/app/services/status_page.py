from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Check, Incident, MaintenanceWindow, Monitor, Workspace, utcnow
from app.services.cache import cache
from app.services.metrics import serialize_incident

STATUS_CACHE_KEY = "status-page:data"


async def get_workspace(session: AsyncSession) -> Workspace:
    workspace = await session.get(Workspace, 1)
    if workspace is None:
        workspace = Workspace(
            id=1,
            name=settings.workspace_name,
            status_page_title=settings.status_page_title,
            status_page_description=settings.status_page_description,
        )
        session.add(workspace)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            workspace = await session.get(Workspace, 1)
        else:
            await session.refresh(workspace)
    return workspace


def _day_key(value: datetime) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def _uptime(rows: list[Any]) -> float | None:
    if not rows:
        return None
    success = sum(1 for row in rows if row.success)
    return round(success / len(rows) * 100, 2)


def _avg_response(rows: list[Any]) -> float | None:
    values = [
        float(row.response_time_ms)
        for row in rows
        if row.success and row.kind != "heartbeat" and row.response_time_ms is not None
    ]
    return round(sum(values) / len(values), 1) if values else None


def _overall_status(components: list[dict], maintenance: list[dict]) -> str:
    active_statuses = [item["status"] for item in components if item["status"] != "paused"]
    if not active_statuses:
        return "empty"
    if any(status == "down" for status in active_statuses):
        return "outage"
    if any(status == "degraded" for status in active_statuses):
        return "degraded"
    if any(item["active"] for item in maintenance):
        return "maintenance"
    return "operational"


async def build_status_page(session: AsyncSession) -> dict:
    now = utcnow()
    workspace = await get_workspace(session)
    window_start = now - timedelta(days=30)
    day_start = now - timedelta(hours=24)

    monitors = list(
        (await session.execute(select(Monitor).order_by(Monitor.created_at.asc()))).scalars()
    )
    rows = list(
        (
            await session.execute(
                select(
                    Check.monitor_id,
                    Check.kind,
                    Check.checked_at,
                    Check.success,
                    Check.response_time_ms,
                )
                .where(Check.checked_at >= window_start)
                .order_by(Check.checked_at.asc())
            )
        ).all()
    )
    by_monitor: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        by_monitor[row.monitor_id].append(row)

    windows = list(
        (
            await session.execute(
                select(MaintenanceWindow, Monitor.name)
                .outerjoin(Monitor, Monitor.id == MaintenanceWindow.monitor_id)
                .where(MaintenanceWindow.ends_at > now)
                .order_by(MaintenanceWindow.starts_at.asc())
            )
        ).all()
    )
    maintenance = [
        {
            "id": window.id,
            "title": window.title,
            "description": window.description,
            "monitor_id": window.monitor_id,
            "monitor_name": monitor_name,
            "starts_at": window.starts_at,
            "ends_at": window.ends_at,
            "active": window.starts_at <= now < window.ends_at,
        }
        for window, monitor_name in windows
    ]
    maintenance_by_monitor: dict[int, list[dict]] = defaultdict(list)
    global_maintenance = False
    for item in maintenance:
        if not item["active"]:
            continue
        if item["monitor_id"] is None:
            global_maintenance = True
        else:
            maintenance_by_monitor[item["monitor_id"]].append(item)

    today = now.date()
    days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
    components: list[dict] = []
    for monitor in monitors:
        monitor_rows = by_monitor.get(monitor.id, [])
        rows_24h = [row for row in monitor_rows if row.checked_at >= day_start]
        rows_7d = [row for row in monitor_rows if row.checked_at >= now - timedelta(days=7)]
        daily_counts: dict[date, list[Any]] = defaultdict(list)
        for row in monitor_rows:
            daily_counts[_day_key(row.checked_at)].append(row)
        daily = [
            {
                "day": day,
                "uptime_percent": _uptime(daily_counts.get(day, [])),
                "checks": len(daily_counts.get(day, [])),
            }
            for day in days
        ]
        in_maintenance = monitor.active and (
            global_maintenance or bool(maintenance_by_monitor.get(monitor.id))
        )
        status = "maintenance" if in_maintenance else monitor.status
        if not monitor.active:
            status = "paused"
        components.append(
            {
                "id": monitor.id,
                "name": monitor.name,
                "description": monitor.description,
                "url": monitor.url,
                "monitor_type": monitor.monitor_type,
                "status": status,
                "tags": monitor.tags or [],
                "uptime_24h": _uptime(rows_24h),
                "uptime_7d": _uptime(rows_7d),
                "uptime_30d": _uptime(monitor_rows),
                "avg_response_ms": _avg_response(rows_24h),
                "last_checked_at": monitor.last_checked_at,
                "last_heartbeat_at": monitor.last_heartbeat_at,
                "ssl_days_left": monitor.ssl_days_left,
                "daily": daily,
            }
        )

    incident_rows = (
        await session.execute(
            select(Incident, Monitor.name)
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .where(Incident.started_at >= window_start)
            .order_by(Incident.started_at.desc())
            .limit(14)
        )
    ).all()
    incidents = [
        serialize_incident(incident, monitor_name, now) for incident, monitor_name in incident_rows
    ]

    operational = sum(1 for item in components if item["status"] == "up")
    degraded = sum(1 for item in components if item["status"] == "degraded")
    down = sum(1 for item in components if item["status"] == "down")
    maintenance_count = sum(1 for item in components if item["status"] == "maintenance")

    rows_24h = [row for row in rows if row.checked_at >= day_start]
    rows_7d = [row for row in rows if row.checked_at >= now - timedelta(days=7)]
    return {
        "workspace_name": workspace.name,
        "title": workspace.status_page_title,
        "description": workspace.status_page_description,
        "support_url": workspace.support_url,
        "overall_status": _overall_status(components, maintenance),
        "generated_at": now,
        "uptime_24h": _uptime(rows_24h),
        "uptime_7d": _uptime(rows_7d),
        "uptime_30d": _uptime(rows),
        "avg_response_ms": _avg_response(rows_24h),
        "totals": {
            "monitors": len(monitors),
            "operational": operational,
            "degraded": degraded,
            "down": down,
            "maintenance": maintenance_count,
        },
        "components": components,
        "incidents": incidents,
        "maintenance": maintenance,
        "public": workspace.status_page_public,
    }


async def cached_status_page(session: AsyncSession) -> dict:
    cached = await cache.get_json(STATUS_CACHE_KEY)
    if cached is not None:
        return cached
    data = await build_status_page(session)
    await cache.set_json(STATUS_CACHE_KEY, data, ttl=20)
    return data
