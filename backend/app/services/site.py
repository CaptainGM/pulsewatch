from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import SiteSettings


async def get_site(session: AsyncSession) -> SiteSettings:
    row = await session.get(SiteSettings, 1)
    if row is None:
        row = SiteSettings(id=1)
        session.add(row)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            row = await session.get(SiteSettings, 1)
        else:
            await session.refresh(row)
    return row


def status_url() -> str:
    return f"{settings.public_url.rstrip('/')}{settings.public_status_path}"


def feed_url() -> str:
    return f"{settings.public_url.rstrip('/')}/api/status-page/feed.xml"
