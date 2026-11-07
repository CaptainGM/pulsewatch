import asyncio
import ipaddress
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.models import Check, Incident, Monitor, Notification, utcnow
from app.services.cache import cache
from app.services.events import events
from app.services.maintenance import in_maintenance
from app.services.notifier import deliver_notification

logger = logging.getLogger(__name__)

CHECK_EVENTS = "pulsewatch:check"


class MonitorNotFoundError(Exception):
    pass


class CheckInProgressError(Exception):
    pass


class UnsupportedMonitorTypeError(Exception):
    pass


@dataclass
class ProbeResult:
    success: bool
    status_code: int | None
    response_time_ms: float
    error: str | None
    checked_at: datetime
    response_size_bytes: int | None = None
    ssl_expires_at: datetime | None = None
    ssl_issuer: str | None = None


@dataclass
class CheckOutcome:
    monitor_id: int
    monitor_name: str
    check_id: int
    success: bool
    status_code: int | None
    response_time_ms: float
    error: str | None
    checked_at: datetime
    status: str
    alert_kind: str | None
    incident_id: int | None
    notification_id: int | None


_check_locks: dict[int, asyncio.Lock] = {}
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(max(1, settings.check_concurrency))
    return _semaphore


def _get_lock(monitor_id: int) -> asyncio.Lock:
    lock = _check_locks.get(monitor_id)
    if lock is None:
        lock = asyncio.Lock()
        _check_locks[monitor_id] = lock
    return lock


def _truncate(value: str | None, limit: int = 500) -> str | None:
    if value is None:
        return None
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _is_private_target(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )


def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{max(1, seconds)} sn"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} dk"
    hours, remaining = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} sa {remaining} dk" if remaining else f"{hours} sa"
    days, remaining_hours = divmod(hours, 24)
    return f"{days} gün {remaining_hours} sa" if remaining_hours else f"{days} gün"


def _tls_details(response: httpx.Response) -> tuple[datetime | None, str | None]:
    try:
        stream = response.extensions.get("network_stream")
        if stream is None:
            return None, None
        ssl_object = stream.get_extra_info("ssl_object")
        if ssl_object is None:
            return None, None
        cert = ssl_object.getpeercert()
        if not cert:
            return None, None
        expires = datetime.strptime(cert.get("notAfter", ""), "%b %d %H:%M:%S %Y %Z").replace(
            tzinfo=UTC
        )
        issuer = ""
        for rdn in cert.get("issuer", ()):
            for key, value in rdn:
                if key in {"organizationName", "commonName"} and value:
                    issuer = value
                    break
            if issuer:
                break
        return expires, issuer or None
    except Exception:
        return None, None


def _json_path_value(data, path: str):
    cleaned = path.strip()
    if cleaned.startswith("$"):
        cleaned = cleaned[1:]
    tokens = [token.strip().strip("\"'") for token in re.split(r"[.\[\]]", cleaned)]
    current = data
    for token in tokens:
        if not token:
            continue
        if token.lstrip("-").isdigit():
            current = current[int(token)]
        else:
            current = current[token]
    return current


def _assert_response(monitor: Monitor, response: httpx.Response) -> str | None:
    text: str | None = None
    if monitor.expected_keyword:
        text = response.text
        if monitor.expected_keyword not in text:
            return f"İçerik doğrulaması başarısız: '{monitor.expected_keyword}' bulunamadı"
    if monitor.json_path:
        try:
            payload = response.json()
        except ValueError:
            return "JSON doğrulaması başarısız: yanıt geçerli JSON değil"
        try:
            value = _json_path_value(payload, monitor.json_path)
        except (KeyError, IndexError, TypeError):
            return f"JSON doğrulaması başarısız: '{monitor.json_path}' bulunamadı"
        if monitor.expected_json_value is not None:
            if isinstance(value, dict | list):
                actual = json.dumps(value, ensure_ascii=False, sort_keys=True)
            elif isinstance(value, bool):
                actual = "true" if value else "false"
            elif value is None:
                actual = "null"
            else:
                actual = str(value)
            if actual != monitor.expected_json_value:
                return (
                    f"JSON doğrulaması başarısız: '{monitor.json_path}' = '{actual}', "
                    f"beklenen '{monitor.expected_json_value}'"
                )
    return None


async def probe(monitor: Monitor) -> ProbeResult:
    started = time.perf_counter()

    if not monitor.url:
        return ProbeResult(False, None, 0.0, "HTTP monitörü için URL tanımlı değil", utcnow())

    if not settings.allow_private_networks and _is_private_target(monitor.url):
        return ProbeResult(
            False,
            None,
            0.0,
            "Özel ağ adreslerine izin verilmiyor (ALLOW_PRIVATE_NETWORKS=false)",
            utcnow(),
        )

    headers = {str(key): str(value) for key, value in (monitor.headers or {}).items()}
    content = None
    if monitor.body and monitor.method not in {"GET", "HEAD"}:
        content = monitor.body.encode("utf-8")
    expected = monitor.expected_code_list()

    try:
        async with httpx.AsyncClient(
            timeout=monitor.timeout_seconds,
            follow_redirects=True,
            verify=True,
            headers={"User-Agent": f"PulseWatch/{settings.version}"},
        ) as client:
            response = await client.request(
                monitor.method,
                monitor.url,
                headers=headers,
                content=content,
            )
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        size = len(response.content or b"")
        ssl_expires_at, ssl_issuer = _tls_details(response)

        success = response.status_code in expected
        error: str | None = None
        if not success:
            expected_text = ", ".join(str(code) for code in expected)
            error = f"Beklenmeyen HTTP {response.status_code} (beklenen: {expected_text})"
        else:
            error = _assert_response(monitor, response)
            success = error is None

        return ProbeResult(
            success,
            response.status_code,
            elapsed,
            error,
            utcnow(),
            size,
            ssl_expires_at,
            ssl_issuer,
        )
    except httpx.TimeoutException:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return ProbeResult(
            False,
            None,
            elapsed,
            f"Zaman aşımı ({monitor.timeout_seconds} sn)",
            utcnow(),
        )
    except httpx.ConnectError:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return ProbeResult(False, None, elapsed, "Bağlantı kurulamadı", utcnow())
    except httpx.TooManyRedirects:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return ProbeResult(False, None, elapsed, "Çok fazla yönlendirme", utcnow())
    except httpx.HTTPError as exc:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        return ProbeResult(
            False,
            None,
            elapsed,
            _truncate(f"İstek hatası: {exc.__class__.__name__}"),
            utcnow(),
        )
    except Exception as exc:
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        logger.exception("Unexpected probe failure for monitor %s", monitor.id)
        return ProbeResult(False, None, elapsed, _truncate(f"Beklenmeyen hata: {exc}"), utcnow())


def _result_status(monitor: Monitor, result: ProbeResult, maintenance: bool) -> str:
    if not monitor.active:
        return "paused"
    if maintenance:
        return "maintenance"
    if not result.success:
        return "down"
    if monitor.slow_threshold_ms and result.response_time_ms >= monitor.slow_threshold_ms:
        return "degraded"
    return "up"


async def _open_incident(session: AsyncSession, monitor_id: int) -> Incident | None:
    return await session.scalar(
        select(Incident)
        .where(Incident.monitor_id == monitor_id, Incident.status == "open")
        .order_by(Incident.started_at.desc())
        .limit(1)
    )


async def perform_check(monitor_id: int) -> CheckOutcome:
    local_lock = _get_lock(monitor_id)
    if local_lock.locked():
        raise CheckInProgressError("Bu monitör şu anda kontrol ediliyor")

    async with local_lock:
        lock_key = f"pulsewatch:lock:check:{monitor_id}"
        lock_token = await cache.acquire_lock(lock_key, ttl=120)
        if lock_token is None:
            raise CheckInProgressError("Bu monitör başka bir çalışan tarafından kontrol ediliyor")

        pending_delivery = False
        try:
            async with _get_semaphore():
                async with SessionLocal() as session:
                    monitor = await session.get(Monitor, monitor_id)
                    if monitor is None:
                        raise MonitorNotFoundError("Monitör bulunamadı")
                    if monitor.monitor_type == "heartbeat":
                        raise UnsupportedMonitorTypeError(
                            "Heartbeat monitörleri ping adresiyle beslenir; HTTP kontrolü yapılamaz"
                        )

                    maintenance = await in_maintenance(session, monitor.id)
                    result = await probe(monitor)
                    checked_at = result.checked_at
                    previous_status = monitor.status
                    check = Check(
                        monitor_id=monitor.id,
                        kind="http",
                        status_code=result.status_code,
                        response_time_ms=result.response_time_ms,
                        response_size_bytes=result.response_size_bytes,
                        success=result.success,
                        error=_truncate(result.error),
                        checked_at=checked_at,
                    )
                    session.add(check)

                    monitor.last_checked_at = checked_at
                    monitor.last_status_code = result.status_code
                    monitor.last_response_time_ms = result.response_time_ms
                    monitor.last_error = _truncate(result.error)
                    monitor.next_check_at = checked_at + timedelta(seconds=monitor.interval_seconds)
                    monitor.updated_at = checked_at

                    if monitor.url and monitor.url.startswith("https://"):
                        if result.ssl_expires_at is not None:
                            monitor.ssl_expires_at = result.ssl_expires_at
                        monitor.ssl_issuer = result.ssl_issuer or monitor.ssl_issuer
                    else:
                        monitor.ssl_expires_at = None
                        monitor.ssl_issuer = None

                    open_incident = await _open_incident(session, monitor.id)
                    status = _result_status(monitor, result, maintenance)
                    monitor.status = status

                    alert_kind: str | None = None
                    incident_id: int | None = None
                    notification_id: int | None = None

                    if result.success:
                        monitor.consecutive_failures = 0
                        if open_incident is not None:
                            resolved_at = checked_at
                            open_incident.status = "resolved"
                            open_incident.resolved_at = resolved_at
                            duration = max(
                                0,
                                int((resolved_at - open_incident.started_at).total_seconds()),
                            )
                            if not maintenance:
                                notification = Notification(
                                    monitor_id=monitor.id,
                                    incident_id=open_incident.id,
                                    kind="recovery",
                                    title=f"{monitor.name} tekrar çevrimiçi",
                                    message=(
                                        f"{monitor.name} ({monitor.url}) yeniden yanıt veriyor. "
                                        f"Kesinti süresi: {_format_duration(duration)}. "
                                        f"HTTP {result.status_code} · {result.response_time_ms} ms"
                                    ),
                                )
                                session.add(notification)
                                await session.flush()
                                alert_kind = "recovery"
                                incident_id = open_incident.id
                                notification_id = notification.id
                        elif status == "degraded" and previous_status != "degraded":
                            if not maintenance:
                                notification = Notification(
                                    monitor_id=monitor.id,
                                    incident_id=None,
                                    kind="degraded",
                                    title=f"{monitor.name} yavaş yanıt veriyor",
                                    message=(
                                        f"{monitor.name} ({monitor.url}) yanıt süresi "
                                        f"{result.response_time_ms} ms; tanımlı eşik "
                                        f"{monitor.slow_threshold_ms} ms. Servis ayakta "
                                        "ancak performans düşük."
                                    ),
                                )
                                session.add(notification)
                                await session.flush()
                                alert_kind = "degraded"
                                notification_id = notification.id
                    else:
                        monitor.consecutive_failures += 1
                        cause = (
                            f"HTTP {result.status_code}"
                            if result.status_code is not None
                            else (result.error or "Bilinmeyen hata")
                        )
                        cause = _truncate(cause, 500) or "Bilinmeyen hata"

                        if open_incident is not None:
                            open_incident.last_error = _truncate(result.error)
                            open_incident.failure_count = monitor.consecutive_failures
                        elif (
                            monitor.active
                            and not maintenance
                            and monitor.consecutive_failures >= monitor.alert_after_failures
                        ):
                            incident = Incident(
                                monitor_id=monitor.id,
                                status="open",
                                cause=cause,
                                last_error=_truncate(result.error),
                                failure_count=monitor.consecutive_failures,
                                started_at=checked_at,
                            )
                            session.add(incident)
                            await session.flush()
                            notification = Notification(
                                monitor_id=monitor.id,
                                incident_id=incident.id,
                                kind="down",
                                title=f"{monitor.name} yanıt vermiyor",
                                message=(
                                    f"{monitor.name} ({monitor.url}) kontrolü başarısız: {cause}. "
                                    f"Üst üste {monitor.consecutive_failures}. hata. "
                                    f"Son yanıt süresi: {result.response_time_ms} ms"
                                ),
                            )
                            session.add(notification)
                            await session.flush()
                            alert_kind = "down"
                            incident_id = incident.id
                            notification_id = notification.id

                    await session.commit()

                    outcome = CheckOutcome(
                        monitor_id=monitor.id,
                        monitor_name=monitor.name,
                        check_id=check.id,
                        success=result.success,
                        status_code=result.status_code,
                        response_time_ms=result.response_time_ms,
                        error=result.error,
                        checked_at=checked_at,
                        status=status,
                        alert_kind=alert_kind,
                        incident_id=incident_id,
                        notification_id=notification_id,
                    )
                    pending_delivery = notification_id is not None

                    logger.info(
                        "Checked monitor %s (%s): %s in %sms",
                        monitor.id,
                        monitor.name,
                        result.status_code or result.error,
                        result.response_time_ms,
                    )

            if pending_delivery and outcome.notification_id is not None:
                await deliver_notification(outcome.notification_id)

            await cache.delete("dashboard:summary")
            await events.publish(
                {
                    "type": "check.completed",
                    "monitor_id": outcome.monitor_id,
                    "monitor_name": outcome.monitor_name,
                    "success": outcome.success,
                    "status": outcome.status,
                    "status_code": outcome.status_code,
                    "response_time_ms": outcome.response_time_ms,
                    "error": outcome.error,
                    "checked_at": outcome.checked_at,
                    "alert": (
                        {
                            "kind": outcome.alert_kind,
                            "incident_id": outcome.incident_id,
                            "notification_id": outcome.notification_id,
                        }
                        if outcome.alert_kind
                        else None
                    ),
                }
            )
            return outcome
        finally:
            await cache.release_lock(lock_key, lock_token)


async def record_heartbeat(token: str) -> tuple[Monitor, Check]:
    async with SessionLocal() as session:
        monitor = await session.scalar(select(Monitor).where(Monitor.heartbeat_token == token))
        if monitor is None or monitor.monitor_type != "heartbeat":
            raise MonitorNotFoundError("Heartbeat adresi bulunamadı")
        if not monitor.active:
            raise MonitorNotFoundError("Heartbeat monitörü duraklatılmış")

        now = utcnow()
        maintenance = await in_maintenance(session, monitor.id)
        check = Check(
            monitor_id=monitor.id,
            kind="heartbeat",
            status_code=None,
            response_time_ms=0.0,
            success=True,
            error=None,
            checked_at=now,
        )
        session.add(check)
        monitor.last_heartbeat_at = now
        monitor.last_checked_at = now
        monitor.last_status_code = None
        monitor.last_response_time_ms = 0.0
        monitor.last_error = None
        monitor.consecutive_failures = 0
        monitor.status = "maintenance" if maintenance else "up"
        monitor.updated_at = now

        open_incident = await _open_incident(session, monitor.id)
        notification = None
        if open_incident is not None:
            open_incident.status = "resolved"
            open_incident.resolved_at = now
            duration = max(0, int((now - open_incident.started_at).total_seconds()))
            if not maintenance:
                notification = Notification(
                    monitor_id=monitor.id,
                    incident_id=open_incident.id,
                    kind="recovery",
                    title=f"{monitor.name} tekrar çevrimiçi",
                    message=(
                        f"{monitor.name} yeniden heartbeat gönderiyor. "
                        f"Kesinti süresi: {_format_duration(duration)}."
                    ),
                )
                session.add(notification)

        await session.commit()
        if notification is not None:
            await deliver_notification(notification.id)

        await cache.delete("dashboard:summary")
        await events.publish(
            {
                "type": "heartbeat.received",
                "monitor_id": monitor.id,
                "monitor_name": monitor.name,
                "status": monitor.status,
                "received_at": now,
                "recovered": open_incident is not None,
            }
        )
        return monitor, check


async def sweep_heartbeats() -> None:
    async with SessionLocal() as session:
        now = utcnow()
        monitors = list(
            (
                await session.execute(
                    select(Monitor).where(
                        Monitor.monitor_type == "heartbeat",
                        Monitor.active.is_(True),
                    )
                )
            ).scalars()
        )
        notifications: list[int] = []
        for monitor in monitors:
            if monitor.status in {"maintenance", "down"}:
                continue
            reference = monitor.last_heartbeat_at or monitor.created_at
            deadline = reference + timedelta(
                seconds=monitor.interval_seconds + monitor.heartbeat_grace_seconds
            )
            if now < deadline:
                continue
            maintenance = await in_maintenance(session, monitor.id)
            if maintenance:
                continue

            last_seen = (
                monitor.last_heartbeat_at.strftime("%d.%m.%Y %H:%M:%S")
                if monitor.last_heartbeat_at
                else "hiç"
            )
            error = (
                f"Beklenen ping alınamadı. Son ping: {last_seen}. "
                f"Beklenen aralık: {_format_duration(monitor.interval_seconds)}"
            )
            session.add(
                Check(
                    monitor_id=monitor.id,
                    kind="heartbeat",
                    status_code=None,
                    response_time_ms=0.0,
                    success=False,
                    error=_truncate(error),
                    checked_at=now,
                )
            )
            monitor.status = "down"
            monitor.last_checked_at = now
            monitor.last_response_time_ms = 0.0
            monitor.last_error = _truncate(error)
            monitor.consecutive_failures += 1
            monitor.next_check_at = None
            monitor.updated_at = now

            incident = await _open_incident(session, monitor.id)
            if incident is None:
                incident = Incident(
                    monitor_id=monitor.id,
                    status="open",
                    cause="Heartbeat alınamadı",
                    last_error=_truncate(error),
                    failure_count=monitor.consecutive_failures,
                    started_at=now,
                )
                session.add(incident)
                await session.flush()
                notification = Notification(
                    monitor_id=monitor.id,
                    incident_id=incident.id,
                    kind="down",
                    title=f"{monitor.name} heartbeat göndermiyor",
                    message=(f"{monitor.name} için beklenen ping alınamadı. {error}"),
                )
                session.add(notification)
                await session.flush()
                notifications.append(notification.id)

            await session.commit()
            await cache.delete("dashboard:summary")
            await events.publish(
                {
                    "type": "heartbeat.missed",
                    "monitor_id": monitor.id,
                    "monitor_name": monitor.name,
                    "status": "down",
                    "checked_at": now,
                    "error": error,
                }
            )

        for notification_id in notifications:
            await deliver_notification(notification_id)


async def evaluate_heartbeat_now(monitor_id: int) -> bool:
    async with SessionLocal() as session:
        monitor = await session.get(Monitor, monitor_id)
        if monitor is None or monitor.monitor_type != "heartbeat":
            return False
        reference = monitor.last_heartbeat_at or monitor.created_at
        deadline = reference + timedelta(
            seconds=monitor.interval_seconds + monitor.heartbeat_grace_seconds
        )
        return utcnow() < deadline
