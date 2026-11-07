import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.schemas import SiteIn, SiteOut
from app.security import require_admin
from app.services.site import feed_url, get_site, status_url

router = APIRouter(prefix="/site", tags=["site"])

DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def _to_out(row) -> SiteOut:
    if row.custom_domain:
        base = f"https://{row.custom_domain}"
        page = f"{base}{settings.public_status_path}"
        feed = f"{base}/api/status-page/feed.xml"
    else:
        page, feed = status_url(), feed_url()
    return SiteOut(
        logo_url=row.logo_url,
        accent_color=row.accent_color,
        custom_domain=row.custom_domain,
        sla_target_percent=row.sla_target_percent,
        status_url=page,
        feed_url=feed,
    )


def _clean(payload: SiteIn) -> dict:
    logo = (payload.logo_url or "").strip() or None
    if logo and not logo.lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422, detail="Logo adresi http:// veya https:// ile başlamalı"
        )

    domain = (payload.custom_domain or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).rstrip("/") or None
    if domain and not DOMAIN_PATTERN.match(domain):
        raise HTTPException(
            status_code=422, detail="Alan adı geçerli değil, örnek: durum.sirketim.com"
        )

    return {
        "logo_url": logo,
        "accent_color": payload.accent_color.lower(),
        "custom_domain": domain,
        "sla_target_percent": payload.sla_target_percent,
    }


@router.get("", response_model=SiteOut)
async def read_site(session: AsyncSession = Depends(get_session)):
    return _to_out(await get_site(session))


@router.put("", response_model=SiteOut, dependencies=[Depends(require_admin)])
async def update_site(payload: SiteIn, session: AsyncSession = Depends(get_session)):
    row = await get_site(session)
    for field, value in _clean(payload).items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return _to_out(row)
