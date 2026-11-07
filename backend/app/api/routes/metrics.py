from datetime import timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Check, Incident, Monitor, RegionCheck, utcnow
from app.security import require_api_access

router = APIRouter(tags=["metrics"])


def _escape(value) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _sample(metric: str, value, **labels) -> str:
    inner = ",".join(f'{key}="{_escape(val)}"' for key, val in labels.items())
    return f"{metric}{{{inner}}} {value}" if labels else f"{metric} {value}"


def _block(lines: list[str], metric: str, kind: str, help_text: str, samples: list[str]) -> None:
    lines.append(f"# HELP {metric} {help_text}")
    lines.append(f"# TYPE {metric} {kind}")
    lines.extend(samples)


@router.get("/metrics", dependencies=[Depends(require_api_access)])
async def metrics(session: AsyncSession = Depends(get_session)):
    since = utcnow() - timedelta(hours=24)
    monitors = (await session.execute(select(Monitor).order_by(Monitor.id))).scalars().all()
    names = {monitor.id: monitor.name for monitor in monitors}

    http_rows = await session.execute(
        select(Check.monitor_id, Check.success, Check.status_code, func.count(Check.id))
        .where(Check.checked_at >= since, Check.kind == "http")
        .group_by(Check.monitor_id, Check.success, Check.status_code)
    )
    results: dict[tuple[int, str], int] = {}
    codes: dict[tuple[int, str], int] = {}
    for monitor_id, success, status_code, count in http_rows.all():
        key = "success" if success else "failure"
        results[(monitor_id, key)] = results.get((monitor_id, key), 0) + count
        if status_code is not None:
            codes[(monitor_id, str(status_code))] = (
                codes.get((monitor_id, str(status_code)), 0) + count
            )

    open_incidents = await session.scalar(
        select(func.count(Incident.id)).where(Incident.status == "open")
    )
    region_rows = await session.execute(
        select(RegionCheck.monitor_id, RegionCheck.region, RegionCheck.success)
        .order_by(RegionCheck.checked_at.desc())
        .limit(5000)
    )
    latest_region: dict[tuple[int, str], bool] = {}
    for monitor_id, region, success in region_rows.all():
        latest_region.setdefault((monitor_id, region), success)

    up, response_time, uptime, checks, statuses, regions = [], [], [], [], [], []
    for monitor in monitors:
        labels = {"monitor_id": monitor.id, "monitor": monitor.name}
        if monitor.status in ("up", "degraded"):
            up.append(_sample("pulsewatch_monitor_up", 1, **labels))
        elif monitor.status == "down":
            up.append(_sample("pulsewatch_monitor_up", 0, **labels))
        if monitor.last_response_time_ms is not None:
            response_time.append(
                _sample(
                    "pulsewatch_monitor_response_time_ms", monitor.last_response_time_ms, **labels
                )
            )
        ok = results.get((monitor.id, "success"), 0)
        failed = results.get((monitor.id, "failure"), 0)
        if ok + failed:
            percent = round(ok / (ok + failed) * 100, 2)
            uptime.append(_sample("pulsewatch_uptime_24h_percent", percent, **labels))
        for result in ("success", "failure"):
            count = results.get((monitor.id, result), 0)
            checks.append(_sample("pulsewatch_checks_24h", count, result=result, **labels))

    for (monitor_id, code), count in sorted(codes.items()):
        if monitor_id in names:
            labels = {"monitor_id": monitor_id, "monitor": names[monitor_id], "code": code}
            statuses.append(_sample("pulsewatch_http_status_24h", count, **labels))

    for (monitor_id, region), success in sorted(latest_region.items()):
        if monitor_id in names:
            labels = {"monitor_id": monitor_id, "monitor": names[monitor_id], "region": region}
            regions.append(_sample("pulsewatch_region_up", 1 if success else 0, **labels))

    lines: list[str] = []
    _block(
        lines,
        "pulsewatch_monitor_up",
        "gauge",
        "1 when the monitor is up or degraded, 0 when it is down.",
        up,
    )
    _block(
        lines,
        "pulsewatch_monitor_response_time_ms",
        "gauge",
        "Last response time of the monitor in milliseconds.",
        response_time,
    )
    _block(
        lines,
        "pulsewatch_uptime_24h_percent",
        "gauge",
        "Share of successful checks in the last 24 hours.",
        uptime,
    )
    _block(
        lines,
        "pulsewatch_checks_24h",
        "gauge",
        "HTTP checks in the last 24 hours by result.",
        checks,
    )
    _block(
        lines,
        "pulsewatch_http_status_24h",
        "gauge",
        "HTTP status codes seen in the last 24 hours.",
        statuses,
    )
    _block(
        lines,
        "pulsewatch_incidents_open",
        "gauge",
        "Incidents that are currently open.",
        [_sample("pulsewatch_incidents_open", open_incidents or 0)],
    )
    _block(
        lines,
        "pulsewatch_region_up",
        "gauge",
        "Latest result per region, 1 when the last check succeeded.",
        regions,
    )

    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
