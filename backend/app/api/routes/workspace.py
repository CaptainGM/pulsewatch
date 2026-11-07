from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import utcnow
from app.schemas import StatusPageSettingsOut, WorkspaceOut, WorkspaceUpdate
from app.services.cache import cache
from app.services.status_page import STATUS_CACHE_KEY, get_workspace

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceOut)
async def get_workspace_settings(session: AsyncSession = Depends(get_session)):
    return await get_workspace(session)


@router.patch("", response_model=WorkspaceOut)
async def update_workspace(payload: WorkspaceUpdate, session: AsyncSession = Depends(get_session)):
    workspace = await get_workspace(session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workspace, field, value)
    workspace.updated_at = utcnow()
    await session.commit()
    await session.refresh(workspace)
    await cache.delete(STATUS_CACHE_KEY)
    return workspace


@router.get("/status-page", response_model=StatusPageSettingsOut)
async def status_page_settings(session: AsyncSession = Depends(get_session)):
    workspace = await get_workspace(session)
    base = settings.frontend_url.rstrip("/")
    return StatusPageSettingsOut(
        title=workspace.status_page_title,
        description=workspace.status_page_description,
        public=workspace.status_page_public,
        support_url=workspace.support_url,
        status_page_url=f"{base}{settings.public_status_path}",
        badge_url=f"{base}/api/badge/overall.svg",
    )
