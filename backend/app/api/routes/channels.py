from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import AlertChannel, utcnow
from app.schemas import ChannelCreate, ChannelOut, ChannelUpdate, WebhookTestOut
from app.services.notifier import send_test_channel

router = APIRouter(prefix="/channels", tags=["channels"])


def _validate_config(kind: str, config: dict) -> None:
    if kind in {"slack", "discord"}:
        if not str(config.get("webhook_url") or "").strip():
            raise HTTPException(status_code=422, detail="Webhook adresi zorunludur")
    elif kind == "telegram":
        if not str(config.get("bot_token") or "").strip():
            raise HTTPException(status_code=422, detail="Bot token zorunludur")
        if not str(config.get("chat_id") or "").strip():
            raise HTTPException(status_code=422, detail="Chat ID zorunludur")
    elif kind == "webhook":
        if not str(config.get("url") or "").strip():
            raise HTTPException(status_code=422, detail="Webhook adresi zorunludur")


async def _get_channel(session: AsyncSession, channel_id: int) -> AlertChannel:
    channel = await session.get(AlertChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Bildirim kanalı bulunamadı")
    return channel


@router.get("", response_model=list[ChannelOut])
async def list_channels(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(AlertChannel).order_by(AlertChannel.created_at.asc()))
    return result.scalars().all()


@router.post("", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(payload: ChannelCreate, session: AsyncSession = Depends(get_session)):
    _validate_config(payload.kind, payload.config)
    channel = AlertChannel(
        name=payload.name,
        kind=payload.kind,
        config=payload.config,
        enabled=payload.enabled,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: int,
    payload: ChannelUpdate,
    session: AsyncSession = Depends(get_session),
):
    channel = await _get_channel(session, channel_id)
    values = payload.model_dump(exclude_unset=True)
    kind = values.get("kind", channel.kind)
    config = values.get("config", channel.config or {})
    if "config" in values or "kind" in values:
        _validate_config(kind, config)
    for field, value in values.items():
        setattr(channel, field, value)
    channel.updated_at = utcnow()
    await session.commit()
    await session.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: int, session: AsyncSession = Depends(get_session)):
    channel = await _get_channel(session, channel_id)
    await session.delete(channel)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{channel_id}/test", response_model=WebhookTestOut)
async def test_channel(channel_id: int, session: AsyncSession = Depends(get_session)):
    channel = await _get_channel(session, channel_id)
    success, error = await send_test_channel(channel)
    await session.commit()
    return WebhookTestOut(
        success=success,
        message="Test bildirimi gönderildi" if success else (error or "Gönderilemedi"),
    )
