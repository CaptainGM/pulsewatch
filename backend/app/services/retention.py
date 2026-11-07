from datetime import timedelta

from sqlalchemy import delete

from app.config import settings
from app.database import SessionLocal
from app.models import Check, utcnow


async def prune_old_checks() -> int:
    if settings.retention_days <= 0:
        return 0
    cutoff = utcnow() - timedelta(days=settings.retention_days)
    async with SessionLocal() as session:
        result = await session.execute(delete(Check).where(Check.checked_at < cutoff))
        await session.commit()
        return result.rowcount or 0
