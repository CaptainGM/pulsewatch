from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Incident, Monitor, utcnow
from app.schemas import IncidentOut
from app.services.metrics import serialize_incident

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentOut])
async def list_incidents(
    status_filter: Literal["open", "resolved"] | None = Query(default=None, alias="status"),
    monitor_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    statement = (
        select(Incident, Monitor.name)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .order_by(Incident.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        statement = statement.where(Incident.status == status_filter)
    if monitor_id is not None:
        statement = statement.where(Incident.monitor_id == monitor_id)

    rows = (await session.execute(statement)).all()
    now = utcnow()
    return [serialize_incident(incident, name, now) for incident, name in rows]


@router.post("/{incident_id}/ack", response_model=IncidentOut)
async def acknowledge_incident(
    incident_id: int,
    session: AsyncSession = Depends(get_session),
):
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Olay bulunamadı")
    incident.acknowledged = True
    await session.commit()
    await session.refresh(incident)
    monitor = await session.get(Monitor, incident.monitor_id)
    name = monitor.name if monitor else "Bilinmeyen monitör"
    return serialize_incident(incident, name)
