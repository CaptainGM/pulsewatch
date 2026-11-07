from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.security import hash_password


async def ensure_bootstrap_admin() -> None:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count(User.id)))
        if count:
            return
        session.add(
            User(
                email=settings.admin_email.strip().lower(),
                name="Yönetici",
                password_hash=hash_password(settings.admin_password),
                role="admin",
                auth_provider="local",
                active=True,
            )
        )
        await session.commit()


async def other_active_admins(session: AsyncSession, user_id: int) -> int:
    query = select(func.count(User.id)).where(
        User.role == "admin",
        User.active.is_(True),
        User.id != user_id,
    )
    return int(await session.scalar(query) or 0)
