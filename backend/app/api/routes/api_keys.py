from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ApiKey, utcnow
from app.schemas import ApiKeyCreate, ApiKeyCreatedOut, ApiKeyOut
from app.security import generate_api_key

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_api_key(payload: ApiKeyCreate, session: AsyncSession = Depends(get_session)):
    full_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(name=payload.name, prefix=prefix, key_hash=key_hash)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return ApiKeyCreatedOut(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        last_used_at=api_key.last_used_at,
        revoked_at=api_key.revoked_at,
        created_at=api_key.created_at,
        key=full_key,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: int, session: AsyncSession = Depends(get_session)):
    api_key = await session.get(ApiKey, key_id)
    if api_key is None:
        raise HTTPException(status_code=404, detail="API anahtarı bulunamadı")
    if api_key.revoked_at is None:
        api_key.revoked_at = utcnow()
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
