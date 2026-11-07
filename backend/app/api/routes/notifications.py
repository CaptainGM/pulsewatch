from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Monitor, Notification
from app.schemas import NotificationOut, WebhookTestIn, WebhookTestOut
from app.services.notifier import deliver_notification, send_test_webhook

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(notification: Notification, monitor_name: str | None) -> dict:
    return {
        "id": notification.id,
        "monitor_id": notification.monitor_id,
        "monitor_name": monitor_name,
        "incident_id": notification.incident_id,
        "kind": notification.kind,
        "title": notification.title,
        "message": notification.message,
        "read": notification.read,
        "webhook_status": notification.webhook_status,
        "webhook_error": notification.webhook_error,
        "deliveries": notification.deliveries or [],
        "created_at": notification.created_at,
    }


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    statement = (
        select(Notification, Monitor.name)
        .outerjoin(Monitor, Monitor.id == Notification.monitor_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    if unread_only:
        statement = statement.where(Notification.read.is_(False))
    rows = (await session.execute(statement)).all()
    return [_serialize(notification, monitor_name) for notification, monitor_name in rows]


@router.patch("/{notification_id}/read", response_model=NotificationOut)
async def mark_notification_read(
    notification_id: int,
    session: AsyncSession = Depends(get_session),
):
    notification = await session.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı")
    notification.read = True
    await session.commit()
    await session.refresh(notification)
    monitor = (
        await session.get(Monitor, notification.monitor_id) if notification.monitor_id else None
    )
    return _serialize(notification, monitor.name if monitor else None)


@router.post("/read-all")
async def mark_all_read(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        update(Notification).where(Notification.read.is_(False)).values(read=True)
    )
    await session.commit()
    return {"updated": result.rowcount or 0}


@router.get("/unread-count")
async def unread_count(session: AsyncSession = Depends(get_session)):
    count = await session.scalar(
        select(func.count(Notification.id)).where(Notification.read.is_(False))
    )
    return {"count": int(count or 0)}


@router.post("/{notification_id}/retry", response_model=NotificationOut)
async def retry_notification(notification_id: int, session: AsyncSession = Depends(get_session)):
    notification = await session.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı")
    await deliver_notification(notification_id)
    await session.refresh(notification)
    monitor = (
        await session.get(Monitor, notification.monitor_id) if notification.monitor_id else None
    )
    return _serialize(notification, monitor.name if monitor else None)


@router.post("/test-webhook", response_model=WebhookTestOut)
async def test_webhook(payload: WebhookTestIn):
    success, message = await send_test_webhook(payload.url)
    return {
        "success": success,
        "message": "Test bildirimi gönderildi" if success else message,
    }
