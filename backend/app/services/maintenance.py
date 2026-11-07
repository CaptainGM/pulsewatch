from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MaintenanceWindow, Monitor, utcnow


def window_is_active(window: MaintenanceWindow, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return window.starts_at <= now < window.ends_at


async def active_windows(
    session: AsyncSession, monitor_id: int | None = None, now: datetime | None = None
) -> list[MaintenanceWindow]:
    now = now or utcnow()
    query = select(MaintenanceWindow).where(
        MaintenanceWindow.starts_at <= now,
        MaintenanceWindow.ends_at > now,
        or_(
            MaintenanceWindow.monitor_id.is_(None),
            MaintenanceWindow.monitor_id == monitor_id if monitor_id is not None else False,
        ),
    )
    return list((await session.execute(query.order_by(MaintenanceWindow.ends_at.asc()))).scalars())


async def in_maintenance(
    session: AsyncSession, monitor_id: int | None = None, now: datetime | None = None
) -> bool:
    now = now or utcnow()
    query = select(MaintenanceWindow.id).where(
        MaintenanceWindow.starts_at <= now,
        MaintenanceWindow.ends_at > now,
        or_(
            MaintenanceWindow.monitor_id.is_(None),
            MaintenanceWindow.monitor_id == monitor_id if monitor_id is not None else False,
        ),
    )
    return (await session.scalar(query.limit(1))) is not None


async def sweep_maintenance(session: AsyncSession) -> None:
    now = utcnow()
    windows = list(
        (
            await session.execute(
                select(MaintenanceWindow).where(
                    MaintenanceWindow.starts_at <= now,
                    MaintenanceWindow.ends_at > now,
                )
            )
        ).scalars()
    )
    covered_ids = {window.monitor_id for window in windows if window.monitor_id is not None}
    global_window = any(window.monitor_id is None for window in windows)

    monitors = list((await session.execute(select(Monitor))).scalars())
    for monitor in monitors:
        active = monitor.active and (global_window or monitor.id in covered_ids)
        if active and monitor.status != "maintenance":
            monitor.status = "maintenance"
            monitor.updated_at = now
        elif not active and monitor.status == "maintenance":
            monitor.status = "unknown" if monitor.active else "paused"
            monitor.next_check_at = now if monitor.active else None
            monitor.updated_at = now
    await session.commit()
