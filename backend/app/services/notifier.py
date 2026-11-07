import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import AlertChannel, Monitor, Notification, utcnow

logger = logging.getLogger(__name__)


def _payload(
    monitor: Monitor, kind: str, title: str, message: str, incident_id: int | None
) -> dict[str, Any]:
    monitor_payload = {
        "id": monitor.id,
        "name": monitor.name,
        "url": monitor.url,
        "monitor_type": monitor.monitor_type,
        "method": monitor.method,
        "status": monitor.status,
        "last_status_code": monitor.last_status_code,
        "last_response_time_ms": monitor.last_response_time_ms,
    }
    event = {
        "down": "monitor.down",
        "recovery": "monitor.up",
        "degraded": "monitor.degraded",
        "test": "test",
    }.get(kind, "monitor.event")
    return {
        "event": event,
        "kind": kind,
        "text": message,
        "content": message,
        "title": title,
        "monitor": monitor_payload,
        "incident_id": incident_id,
        "dashboard_url": f"{settings.frontend_url}/monitors/{monitor.id}",
        "status_page_url": f"{settings.frontend_url}{settings.public_status_path}",
        "timestamp": utcnow().isoformat(),
    }


async def post_webhook(url: str, payload: dict[str, Any]) -> tuple[bool, str]:
    if not url:
        return False, "Webhook adresi yok"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"User-Agent": f"PulseWatch/{settings.version}"},
            )
        if 200 <= response.status_code < 300:
            return True, ""
        return False, f"Webhook HTTP {response.status_code}"
    except httpx.TimeoutException:
        return False, "Webhook zaman aşımına uğradı"
    except httpx.HTTPError as exc:
        return False, f"Webhook hatası: {exc.__class__.__name__}"
    except Exception as exc:
        logger.warning("Unexpected webhook error: %s", exc)
        return False, "Webhook gönderilemedi"


async def _send_slack(config: dict[str, Any], title: str, message: str) -> tuple[bool, str]:
    url = str(config.get("webhook_url") or "").strip()
    if not url:
        return False, "Slack webhook adresi tanımlı değil"
    return await post_webhook(
        url,
        {
            "text": f"*{title}*\n{message}",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title[:150]},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message[:2900]},
                },
            ],
        },
    )


async def _send_discord(config: dict[str, Any], title: str, message: str) -> tuple[bool, str]:
    url = str(config.get("webhook_url") or "").strip()
    if not url:
        return False, "Discord webhook adresi tanımlı değil"
    return await post_webhook(
        url,
        {
            "content": f"**{title}**\n{message}"[:1900],
            "username": "PulseWatch",
        },
    )


async def _send_telegram(config: dict[str, Any], title: str, message: str) -> tuple[bool, str]:
    token = str(config.get("bot_token") or "").strip()
    chat_id = str(config.get("chat_id") or "").strip()
    if not token or not chat_id:
        return False, "Telegram bot token veya chat id tanımlı değil"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{settings.telegram_api_base.rstrip('/')}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"{title}\n\n{message}"[:4000],
                    "link_preview_options": {"is_disabled": True},
                },
            )
        if 200 <= response.status_code < 300:
            return True, ""
        return False, f"Telegram HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        return False, f"Telegram hatası: {exc.__class__.__name__}"


async def _send_generic(config: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str]:
    url = str(config.get("url") or config.get("webhook_url") or "").strip()
    if not url:
        return False, "Webhook adresi tanımlı değil"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    secret = str(config.get("secret") or settings.webhook_signing_secret or "").strip()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"PulseWatch/{settings.version}",
    }
    if secret:
        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-PulseWatch-Signature"] = f"sha256={signature}"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.post(url, content=body, headers=headers)
        if 200 <= response.status_code < 300:
            return True, ""
        return False, f"Webhook HTTP {response.status_code}"
    except httpx.TimeoutException:
        return False, "Webhook zaman aşımına uğradı"
    except httpx.HTTPError as exc:
        return False, f"Webhook hatası: {exc.__class__.__name__}"


async def deliver_to_channel(
    channel: AlertChannel, notification: Notification, monitor: Monitor
) -> tuple[bool, str]:
    payload = _payload(
        monitor,
        notification.kind,
        notification.title,
        notification.message,
        notification.incident_id,
    )
    config = channel.config or {}
    if channel.kind == "slack":
        return await _send_slack(config, notification.title, notification.message)
    if channel.kind == "discord":
        return await _send_discord(config, notification.title, notification.message)
    if channel.kind == "telegram":
        return await _send_telegram(config, notification.title, notification.message)
    return await _send_generic(config, payload)


async def _fallback_channels(session, monitor: Monitor) -> list[AlertChannel]:
    if monitor.alert_channel_ids:
        result = await session.execute(
            select(AlertChannel).where(
                AlertChannel.id.in_(monitor.alert_channel_ids),
                AlertChannel.enabled.is_(True),
            )
        )
        return list(result.scalars())
    result = await session.execute(
        select(AlertChannel).where(AlertChannel.enabled.is_(True)).order_by(AlertChannel.id)
    )
    return list(result.scalars())


async def deliver_notification(notification_id: int) -> None:
    async with SessionLocal() as session:
        notification = await session.get(Notification, notification_id)
        if notification is None:
            return
        monitor = (
            await session.get(Monitor, notification.monitor_id) if notification.monitor_id else None
        )
        if monitor is None:
            notification.webhook_status = "failed"
            notification.webhook_error = "Monitör bulunamadı"
            await session.commit()
            return

        channels = await _fallback_channels(session, monitor)
        results: list[dict[str, Any]] = []
        if channels:
            for channel in channels:
                success, error = await deliver_to_channel(channel, notification, monitor)
                results.append(
                    {
                        "channel_id": channel.id,
                        "channel_name": channel.name,
                        "kind": channel.kind,
                        "status": "sent" if success else "failed",
                        "error": error or None,
                        "at": utcnow().isoformat(),
                    }
                )
                channel.last_status = "sent" if success else "failed"
                channel.last_error = error or None
                channel.last_tested_at = utcnow()
                if not success:
                    logger.warning(
                        "Channel %s delivery failed for notification %s: %s",
                        channel.id,
                        notification_id,
                        error,
                    )
        elif monitor.webhook_url or settings.alert_webhook_url:
            url = monitor.webhook_url or settings.alert_webhook_url
            payload = _payload(
                monitor,
                notification.kind,
                notification.title,
                notification.message,
                notification.incident_id,
            )
            success, error = await _send_generic(
                {"url": url, "secret": settings.webhook_signing_secret}, payload
            )
            results.append(
                {
                    "channel_id": None,
                    "channel_name": "Varsayılan webhook",
                    "kind": "webhook",
                    "status": "sent" if success else "failed",
                    "error": error or None,
                    "at": utcnow().isoformat(),
                }
            )

        notification.deliveries = results
        if not results:
            notification.webhook_status = "none"
            notification.webhook_error = None
        else:
            failed = [item for item in results if item["status"] == "failed"]
            notification.webhook_status = "failed" if failed else "sent"
            notification.webhook_error = (
                "; ".join(str(item["error"]) for item in failed if item.get("error"))[:500] or None
            )
        await session.commit()


async def send_test_channel(channel: AlertChannel) -> tuple[bool, str]:
    if channel.kind == "slack":
        success, error = await _send_slack(
            channel.config or {},
            "PulseWatch test bildirimi",
            "Slack kanalınız PulseWatch alarmlarına hazır.",
        )
    elif channel.kind == "discord":
        success, error = await _send_discord(
            channel.config or {},
            "PulseWatch test bildirimi",
            "Discord kanalınız PulseWatch alarmlarına hazır.",
        )
    elif channel.kind == "telegram":
        success, error = await _send_telegram(
            channel.config or {},
            "PulseWatch test bildirimi",
            "Telegram kanalınız PulseWatch alarmlarına hazır.",
        )
    else:
        success, error = await _send_generic(
            channel.config or {},
            {
                "event": "test",
                "title": "PulseWatch test bildirimi",
                "text": "Webhook entegrasyonunuz çalışıyor.",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    channel.last_status = "sent" if success else "failed"
    channel.last_error = error or None
    channel.last_tested_at = utcnow()
    return success, error


async def send_test_webhook(url: str) -> tuple[bool, str]:
    payload = {
        "event": "test",
        "text": "PulseWatch test bildirimi — webhook bağlantısı çalışıyor.",
        "content": "PulseWatch test bildirimi — webhook bağlantısı çalışıyor.",
        "title": "PulseWatch test bildirimi",
        "monitor": None,
        "timestamp": utcnow().isoformat(),
    }
    return await post_webhook(url, payload)
