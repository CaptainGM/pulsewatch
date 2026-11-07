from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Check, Incident, Monitor, Notification, utcnow

LATENCY_EDGES = [
    (0, 50, "0-50 ms"),
    (50, 100, "50-100 ms"),
    (100, 200, "100-200 ms"),
    (200, 300, "200-300 ms"),
    (300, 500, "300-500 ms"),
    (500, 750, "500-750 ms"),
    (750, 1000, "750 ms-1 sn"),
    (1000, 2000, "1-2 sn"),
    (2000, 5000, "2-5 sn"),
    (5000, None, "5 sn+"),
]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _round(value: float | None, digits: int = 1) -> float | None:
    return round(value, digits) if value is not None else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percentile / 100)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def status_class(status_code: int | None) -> str:
    if status_code is None:
        return "net"
    return f"{status_code // 100}xx"


def _is_http(row: Any) -> bool:
    return getattr(row, "kind", "http") != "heartbeat"


def _histogram(values: list[float]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for lower, upper, label in LATENCY_EDGES:
        if upper is None:
            count = sum(1 for value in values if value >= lower)
        else:
            count = sum(1 for value in values if lower <= value < upper)
        result.append({"label": label, "count": count})
    return result


def serialize_check(check) -> dict[str, Any]:
    return {
        "id": check.id,
        "monitor_id": check.monitor_id,
        "kind": getattr(check, "kind", "http"),
        "status_code": check.status_code,
        "response_time_ms": check.response_time_ms,
        "response_size_bytes": getattr(check, "response_size_bytes", None),
        "success": check.success,
        "error": check.error,
        "checked_at": check.checked_at,
    }


def serialize_incident(incident: Incident, monitor_name: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    end = incident.resolved_at or now
    duration = max(0, int((_aware(end) - _aware(incident.started_at)).total_seconds()))
    return {
        "id": incident.id,
        "monitor_id": incident.monitor_id,
        "monitor_name": monitor_name,
        "status": incident.status,
        "cause": incident.cause,
        "last_error": incident.last_error,
        "failure_count": incident.failure_count,
        "acknowledged": incident.acknowledged,
        "started_at": incident.started_at,
        "resolved_at": incident.resolved_at,
        "duration_seconds": duration,
    }


def build_series(
    rows: Iterable[Any], since: datetime, until: datetime, bucket_count: int
) -> list[dict]:
    bucket_count = max(1, bucket_count)
    total_seconds = max(1.0, (_aware(until) - _aware(since)).total_seconds())
    width = total_seconds / bucket_count
    buckets: list[dict[str, Any]] = []
    for index in range(bucket_count):
        buckets.append(
            {
                "start": _aware(since) + timedelta(seconds=width * index),
                "times": [],
                "checks": 0,
                "errors": 0,
                "classes": Counter(),
            }
        )

    for row in rows:
        checked_at = _aware(row.checked_at)
        index = int((checked_at - _aware(since)).total_seconds() / width)
        index = max(0, min(bucket_count - 1, index))
        bucket = buckets[index]
        bucket["checks"] += 1
        if not row.success:
            bucket["errors"] += 1
        if _is_http(row):
            if row.success and row.response_time_ms is not None:
                bucket["times"].append(float(row.response_time_ms))
            bucket["classes"][status_class(row.status_code)] += 1

    series: list[dict] = []
    for bucket in buckets:
        checks = bucket["checks"]
        errors = bucket["errors"]
        times: list[float] = bucket["times"]
        uptime = ((checks - errors) / checks * 100) if checks else None
        classes = {
            key: int(bucket["classes"].get(key, 0)) for key in ("2xx", "3xx", "4xx", "5xx", "net")
        }
        series.append(
            {
                "start": bucket["start"],
                "avg_ms": _round(sum(times) / len(times)) if times else None,
                "p95_ms": _round(_percentile(times, 95)),
                "checks": checks,
                "errors": errors,
                "uptime_percent": _round(uptime, 2),
                "classes": classes,
            }
        )
    return series


def compute_stats(
    rows: Iterable[Any],
    *,
    window_hours: int,
    buckets: int,
    since: datetime,
    until: datetime,
) -> dict:
    rows = list(rows)
    total_checks = len(rows)
    success_count = sum(1 for row in rows if row.success)
    error_count = total_checks - success_count
    response_times = [
        float(row.response_time_ms)
        for row in rows
        if row.success and row.response_time_ms is not None and _is_http(row)
    ]
    status_counter = Counter(
        row.status_code for row in rows if row.status_code is not None and _is_http(row)
    )
    class_counter = Counter(status_class(row.status_code) for row in rows if _is_http(row))

    uptime = (success_count / total_checks * 100) if total_checks else None
    error_rate = (error_count / total_checks * 100) if total_checks else None
    avg_response = sum(response_times) / len(response_times) if response_times else None

    status_counts = [
        {
            "code": code,
            "count": count,
            "percent": round(count / total_checks * 100, 2) if total_checks else 0.0,
        }
        for code, count in sorted(status_counter.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]

    last_check = None
    if rows:
        latest = max(rows, key=lambda row: _aware(row.checked_at))
        last_check = serialize_check(latest)

    return {
        "window_hours": window_hours,
        "buckets": buckets,
        "total_checks": total_checks,
        "success_count": success_count,
        "error_count": error_count,
        "uptime_percent": _round(uptime, 2),
        "avg_response_ms": _round(avg_response),
        "p50_response_ms": _round(_percentile(response_times, 50)),
        "p95_response_ms": _round(_percentile(response_times, 95)),
        "p99_response_ms": _round(_percentile(response_times, 99)),
        "min_response_ms": _round(min(response_times)) if response_times else None,
        "max_response_ms": _round(max(response_times)) if response_times else None,
        "error_rate_percent": _round(error_rate, 2),
        "status_counts": status_counts,
        "class_counts": {
            key: int(class_counter.get(key, 0)) for key in ("2xx", "3xx", "4xx", "5xx", "net")
        },
        "series": build_series(rows, since, until, buckets),
        "latency_histogram": _histogram(response_times),
        "last_check": last_check,
    }


def build_monitor_card(
    monitor: Monitor,
    rows: list[Any],
    since: datetime,
    until: datetime,
) -> dict:
    ordered = sorted(rows, key=lambda row: _aware(row.checked_at))
    total = len(ordered)
    errors = sum(1 for row in ordered if not row.success)
    success = total - errors
    response_times = [
        float(row.response_time_ms)
        for row in ordered
        if row.success and row.response_time_ms is not None and _is_http(row)
    ]
    uptime = (success / total * 100) if total else None
    avg_response = sum(response_times) / len(response_times) if response_times else None
    sparkline = [round(value, 1) for value in response_times[-24:]]
    recent = [serialize_check(check) for check in ordered[-12:]]

    return {
        "id": monitor.id,
        "name": monitor.name,
        "description": monitor.description,
        "url": monitor.url,
        "monitor_type": monitor.monitor_type,
        "method": monitor.method,
        "status": monitor.status,
        "active": monitor.active,
        "interval_seconds": monitor.interval_seconds,
        "tags": monitor.tags or [],
        "last_checked_at": monitor.last_checked_at,
        "last_heartbeat_at": monitor.last_heartbeat_at,
        "last_response_time_ms": monitor.last_response_time_ms,
        "last_status_code": monitor.last_status_code,
        "last_error": monitor.last_error,
        "ssl_days_left": monitor.ssl_days_left,
        "uptime_percent": _round(uptime, 2),
        "avg_response_ms": _round(avg_response),
        "error_count": errors,
        "total_checks": total,
        "error_rate_percent": _round((errors / total * 100) if total else None, 2),
        "sparkline": sparkline,
        "recent_checks": recent,
    }


async def build_dashboard(session: AsyncSession) -> dict:
    now = utcnow()
    since = now - timedelta(hours=24)

    monitors = (
        (await session.execute(select(Monitor).order_by(Monitor.created_at.asc()))).scalars().all()
    )
    rows = (
        await session.execute(
            select(
                Check.id,
                Check.monitor_id,
                Check.kind,
                Check.checked_at,
                Check.success,
                Check.response_time_ms,
                Check.status_code,
                Check.error,
                Check.response_size_bytes,
            )
            .where(Check.checked_at >= since)
            .order_by(Check.checked_at.asc())
        )
    ).all()

    by_monitor: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        by_monitor[row.monitor_id].append(row)

    overall = compute_stats(
        rows,
        window_hours=24,
        buckets=24,
        since=since,
        until=now,
    )

    cards = [
        build_monitor_card(monitor, by_monitor.get(monitor.id, []), since, now)
        for monitor in monitors
    ]

    incident_rows = (
        await session.execute(
            select(Incident, Monitor.name)
            .join(Monitor, Monitor.id == Incident.monitor_id)
            .order_by(Incident.started_at.desc())
            .limit(5)
        )
    ).all()
    recent_incidents = [
        serialize_incident(incident, monitor_name, now) for incident, monitor_name in incident_rows
    ]

    unread = await session.scalar(
        select(func.count(Notification.id)).where(Notification.read.is_(False))
    )

    up = sum(1 for monitor in monitors if monitor.active and monitor.status == "up")
    degraded = sum(1 for monitor in monitors if monitor.active and monitor.status == "degraded")
    down = sum(1 for monitor in monitors if monitor.active and monitor.status == "down")
    maintenance = sum(
        1 for monitor in monitors if monitor.active and monitor.status == "maintenance"
    )
    paused = sum(1 for monitor in monitors if not monitor.active)
    unknown = sum(
        1
        for monitor in monitors
        if monitor.active and monitor.status not in {"up", "down", "degraded", "maintenance"}
    )

    return {
        "generated_at": now,
        "window_hours": 24,
        "totals": {
            "monitors": len(monitors),
            "up": up,
            "down": down,
            "degraded": degraded,
            "maintenance": maintenance,
            "paused": paused,
            "unknown": unknown,
            "checks": overall["total_checks"],
            "errors": overall["error_count"],
        },
        "uptime_percent": overall["uptime_percent"],
        "avg_response_ms": overall["avg_response_ms"],
        "p95_response_ms": overall["p95_response_ms"],
        "error_rate_percent": overall["error_rate_percent"],
        "class_counts": overall["class_counts"],
        "status_counts": overall["status_counts"],
        "series": overall["series"],
        "monitors": cards,
        "recent_incidents": recent_incidents,
        "unread_notifications": int(unread or 0),
    }


async def get_monitor_stats(
    session: AsyncSession, monitor_id: int, hours: int, buckets: int
) -> dict:
    until = utcnow()
    since = until - timedelta(hours=hours)
    rows = (
        (
            await session.execute(
                select(Check)
                .where(Check.monitor_id == monitor_id, Check.checked_at >= since)
                .order_by(Check.checked_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return compute_stats(
        rows,
        window_hours=hours,
        buckets=buckets,
        since=since,
        until=until,
    )
