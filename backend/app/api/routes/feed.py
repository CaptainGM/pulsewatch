from email.utils import format_datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import Incident, Monitor
from app.services.site import status_url

router = APIRouter(prefix="/status-page", tags=["status"])


@router.get("/feed.xml")
async def incident_feed(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(
        select(Incident, Monitor.name)
        .join(Monitor, Monitor.id == Incident.monitor_id)
        .order_by(Incident.started_at.desc())
        .limit(30)
    )
    items = []
    for incident, name in rows.all():
        state = "Çözüldü" if incident.status == "resolved" else "Açık"
        items.append(
            "<item>"
            f"<title>{escape(name)}: {state}</title>"
            f"<description>{escape(incident.cause)}</description>"
            f"<pubDate>{format_datetime(incident.started_at)}</pubDate>"
            f'<guid isPermaLink="false">pulsewatch-incident-{incident.id}</guid>'
            "</item>"
        )
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        f"<title>{escape(settings.workspace_name)} durum</title>"
        f"<link>{escape(status_url())}</link>"
        "<description>Kesinti kayıtları</description>" + "".join(items) + "</channel></rss>"
    )
    return Response(content=body, media_type="application/rss+xml; charset=utf-8")
