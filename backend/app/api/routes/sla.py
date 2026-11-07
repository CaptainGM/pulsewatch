from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.security import require_user
from app.services.site import get_site
from app.services.sla import load_sla, period_bounds

router = APIRouter(prefix="/sla", tags=["sla"])

CSV_HEADER = (
    "monitor,availability_percent,downtime_minutes,incidents,error_budget_minutes,meets_target"
)


async def _report(session: AsyncSession, days: int) -> dict:
    since, until = period_bounds(days)
    site = await get_site(session)
    return await load_sla(session, since, until, site.sla_target_percent)


@router.get("")
async def sla_report(
    days: int = Query(default=30, ge=1, le=366),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_user),
):
    return await _report(session, days)


@router.get("/export.csv")
async def sla_csv(
    days: int = Query(default=30, ge=1, le=366),
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_user),
):
    report = await _report(session, days)
    lines = [CSV_HEADER]
    for row in report["monitors"]:
        name = '"' + row["name"].replace('"', '""') + '"'
        met = "evet" if row["meets_target"] else "hayir"
        lines.append(
            f"{name},{row['availability_percent']},{row['downtime_minutes']},"
            f"{row['incidents']},{row['error_budget_minutes']},{met}"
        )
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=sla.csv"},
    )
