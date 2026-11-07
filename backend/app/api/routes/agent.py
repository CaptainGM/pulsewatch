import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Monitor, RegionCheck, utcnow
from app.schemas import RegionReportIn
from app.security import require_api_access, require_user

router = APIRouter(tags=["regions"])

REGION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$")


@router.get("/agent/monitors", dependencies=[Depends(require_api_access)])
async def agent_monitors(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(Monitor).where(
            Monitor.active.is_(True),
            Monitor.monitor_type == "http",
            Monitor.url.is_not(None),
        )
    )
    return [
        {
            "id": monitor.id,
            "name": monitor.name,
            "url": monitor.url,
            "method": monitor.method,
            "expected_codes": monitor.expected_code_list(),
            "timeout_seconds": monitor.timeout_seconds,
            "interval_seconds": monitor.interval_seconds,
        }
        for monitor in rows.scalars().all()
    ]


@router.post(
    "/agent/results",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_api_access)],
)
async def agent_results(payload: RegionReportIn, session: AsyncSession = Depends(get_session)):
    region = payload.region.strip().lower()
    if not REGION_PATTERN.match(region):
        raise HTTPException(
            status_code=422,
            detail="Bölge adı yalnızca küçük harf, rakam ve tire içerebilir",
        )
    wanted = {item.monitor_id for item in payload.results}
    known = set(
        (await session.execute(select(Monitor.id).where(Monitor.id.in_(wanted)))).scalars().all()
    )
    checked_at = utcnow()
    stored = 0
    for item in payload.results:
        if item.monitor_id not in known:
            continue
        session.add(
            RegionCheck(
                monitor_id=item.monitor_id,
                region=region,
                success=item.success,
                status_code=item.status_code,
                response_time_ms=item.response_time_ms,
                error=item.error,
                checked_at=checked_at,
            )
        )
        stored += 1
    await session.commit()
    return {"region": region, "stored": stored, "skipped": len(payload.results) - stored}


@router.get("/monitors/{monitor_id}/regions", dependencies=[Depends(require_user)])
async def monitor_regions(monitor_id: int, session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(RegionCheck)
        .where(RegionCheck.monitor_id == monitor_id)
        .order_by(RegionCheck.checked_at.desc())
        .limit(2000)
    )
    latest = {}
    for row in rows.scalars().all():
        latest.setdefault(row.region, row)
    return [
        {
            "region": region,
            "success": row.success,
            "status_code": row.status_code,
            "response_time_ms": row.response_time_ms,
            "error": row.error,
            "checked_at": row.checked_at,
        }
        for region, row in sorted(latest.items())
    ]
