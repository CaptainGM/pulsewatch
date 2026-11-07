from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import utcnow
from app.services.cache import cache
from app.services.events import events
from app.services.scheduler import scheduler

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)):
    database = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database = "error"

    redis_status = await cache.ping()
    healthy = database == "ok"
    return {
        "service": "pulsewatch",
        "status": "ok" if healthy else "degraded",
        "version": settings.version,
        "environment": settings.environment,
        "database": database,
        "redis": redis_status,
        "scheduler_running": scheduler.running,
        "websocket_clients": events.connection_count,
        "time": utcnow(),
    }
