from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Incident, MaintenanceWindow, Monitor, utcnow


def _merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _clip(start, end, since, until):
    start, end = max(start, since), min(end, until)
    return (start, end) if end > start else None


def _subtract(intervals, cuts):
    result = []
    for start, end in intervals:
        pieces = [(start, end)]
        for cut_start, cut_end in cuts:
            remaining = []
            for piece_start, piece_end in pieces:
                if cut_end <= piece_start or cut_start >= piece_end:
                    remaining.append((piece_start, piece_end))
                    continue
                if piece_start < cut_start:
                    remaining.append((piece_start, cut_start))
                if cut_end < piece_end:
                    remaining.append((cut_end, piece_end))
            pieces = remaining
        result.extend(pieces)
    return result


def downtime_seconds(incidents, maintenance, since, until) -> float:
    down = [
        span
        for span in (_clip(start, resolved or until, since, until) for start, resolved in incidents)
        if span
    ]
    cuts = _merge(
        [span for span in (_clip(start, end, since, until) for start, end in maintenance) if span]
    )
    pieces = _subtract(_merge(down), cuts)
    return sum((end - start).total_seconds() for start, end in pieces)


def build_sla_rows(
    monitors: list[tuple[int, str]],
    incidents: list[tuple[int, datetime, datetime | None]],
    maintenance: list[tuple[int | None, datetime, datetime]],
    since: datetime,
    until: datetime,
    target_percent: float,
) -> dict[str, Any]:
    period = (until - since).total_seconds()
    allowed = period * (1 - target_percent / 100)
    rows = []
    for monitor_id, name in monitors:
        own_incidents = [
            (start, resolved) for mid, start, resolved in incidents if mid == monitor_id
        ]
        own_maintenance = [
            (start, end) for mid, start, end in maintenance if mid in (None, monitor_id)
        ]
        down = downtime_seconds(own_incidents, own_maintenance, since, until)
        availability = 100 * (1 - down / period) if period else 100.0
        rows.append(
            {
                "monitor_id": monitor_id,
                "name": name,
                "availability_percent": round(availability, 3),
                "downtime_minutes": round(down / 60, 1),
                "incidents": len(own_incidents),
                "error_budget_minutes": round((allowed - down) / 60, 1),
                "meets_target": availability >= target_percent,
            }
        )
    overall = (
        round(sum(row["availability_percent"] for row in rows) / len(rows), 3) if rows else None
    )
    return {
        "period_start": since,
        "period_end": until,
        "target_percent": target_percent,
        "overall_percent": overall,
        "monitors": rows,
    }


async def load_sla(session: AsyncSession, since: datetime, until: datetime, target: float):
    monitors = (
        await session.execute(select(Monitor.id, Monitor.name).order_by(Monitor.name))
    ).all()
    incidents = (
        await session.execute(
            select(Incident.monitor_id, Incident.started_at, Incident.resolved_at).where(
                Incident.started_at < until,
                or_(Incident.resolved_at.is_(None), Incident.resolved_at > since),
            )
        )
    ).all()
    maintenance = (
        await session.execute(
            select(
                MaintenanceWindow.monitor_id,
                MaintenanceWindow.starts_at,
                MaintenanceWindow.ends_at,
            ).where(
                MaintenanceWindow.starts_at < until,
                MaintenanceWindow.ends_at > since,
            )
        )
    ).all()
    return build_sla_rows(
        [(row.id, row.name) for row in monitors],
        [(row.monitor_id, row.started_at, row.resolved_at) for row in incidents],
        [(row.monitor_id, row.starts_at, row.ends_at) for row in maintenance],
        since,
        until,
        target,
    )


def period_bounds(days: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    until = now or utcnow()
    return until - timedelta(days=days), until
