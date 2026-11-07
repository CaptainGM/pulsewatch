import argparse
import asyncio
import math
import random
from datetime import timedelta

from sqlalchemy import delete, func, select

from app.database import SessionLocal, init_db
from app.models import (
    AlertChannel,
    ApiKey,
    Check,
    Incident,
    MaintenanceWindow,
    Monitor,
    Notification,
    Workspace,
    utcnow,
)

random.seed(42)

DEMO_MONITORS = [
    {
        "name": "GitHub API",
        "description": "Kod deposu, PR ve organizasyon metrikleri için genel API.",
        "url": "https://api.github.com",
        "method": "GET",
        "interval_seconds": 120,
        "timeout_seconds": 10,
        "expected_codes": [200],
        "json_path": "current_user_url",
        "tags": ["Kritik", "Geliştirici"],
        "base_latency": 110,
        "amplitude": 30,
        "noise": 14,
        "ssl_days": 47,
        "ssl_issuer": "DigiCert Inc",
    },
    {
        "name": "JSONPlaceholder",
        "description": "Demo veri kaynağı; içerik ve JSON alan doğrulaması örneği.",
        "url": "https://jsonplaceholder.typicode.com/posts/1",
        "method": "GET",
        "interval_seconds": 300,
        "timeout_seconds": 10,
        "expected_codes": [200],
        "expected_keyword": "userId",
        "json_path": "id",
        "expected_json_value": "1",
        "tags": ["Demo", "İçerik"],
        "base_latency": 72,
        "amplitude": 16,
        "noise": 8,
        "ssl_days": 89,
        "ssl_issuer": "Let's Encrypt",
    },
    {
        "name": "Open-Meteo Hava Durumu",
        "description": "İstanbul için saatlik hava durumu tahmini.",
        "url": "https://api.open-meteo.com/v1/forecast?latitude=41.01&longitude=28.98&current=temperature_2m",
        "method": "GET",
        "interval_seconds": 300,
        "timeout_seconds": 10,
        "expected_codes": [200],
        "slow_threshold_ms": 500,
        "tags": ["Harici", "Hava Durumu"],
        "base_latency": 175,
        "amplitude": 45,
        "noise": 20,
        "ssl_days": 23,
        "ssl_issuer": "Google Trust Services",
    },
    {
        "name": "Ödeme Servisi (Demo)",
        "description": "Kasıtlı olarak çevrimdışı bırakılan kritik ödeme servisi.",
        "url": "http://localhost:9999/health",
        "method": "GET",
        "interval_seconds": 60,
        "timeout_seconds": 5,
        "expected_codes": [200],
        "slow_threshold_ms": 500,
        "tags": ["Kritik", "Ödeme"],
        "base_latency": 240,
        "amplitude": 55,
        "noise": 22,
        "ssl_days": None,
        "ssl_issuer": None,
    },
    {
        "name": "Gece Yedekleme İşi",
        "description": "Her saat çalışan yedekleme cron'u için heartbeat (dead-man switch).",
        "url": None,
        "monitor_type": "heartbeat",
        "method": "GET",
        "interval_seconds": 3600,
        "timeout_seconds": 10,
        "expected_codes": [200],
        "heartbeat_grace_seconds": 300,
        "heartbeat_token": "demo-backup-heartbeat-token",
        "tags": ["İç Sistem", "Cron"],
        "base_latency": 0,
        "amplitude": 0,
        "noise": 0,
        "ssl_days": None,
        "ssl_issuer": None,
    },
]


def _latency(config: dict, index: int, spike: bool = False) -> float:
    if config.get("monitor_type") == "heartbeat":
        return 0.0
    value = (
        config["base_latency"]
        + config["amplitude"] * math.sin(index / 27)
        + random.uniform(-config["noise"], config["noise"])
    )
    if spike:
        value *= random.uniform(1.45, 1.9)
    return round(max(12.0, value), 1)


def _historical_error(
    monitor_name: str, day_offset: int, slot: int
) -> tuple[int | None, bool, str | None]:
    seed = day_offset * 31 + slot
    if monitor_name == "Ödeme Servisi (Demo)" and day_offset in {12, 23} and slot in {11, 12}:
        return None, False, "Bağlantı kurulamadı"
    if monitor_name == "GitHub API" and day_offset == 6 and slot == 37:
        return 500, False, "Beklenmeyen HTTP 500 (beklenen: 200)"
    if monitor_name == "JSONPlaceholder" and day_offset == 17 and slot in {8, 9}:
        return 404, False, "Beklenmeyen HTTP 404 (beklenen: 200)"
    if monitor_name == "Open-Meteo Hava Durumu" and day_offset == 20 and slot == 22:
        return 503, False, "Beklenmeyen HTTP 503 (beklenen: 200)"
    if seed % 97 == 0:
        return 503, False, "Beklenmeyen HTTP 503 (beklenen: 200)"
    return 200, True, None


def _build_check(
    monitor: Monitor,
    config: dict,
    index: int,
    checked_at,
    *,
    historical_day: int | None = None,
    slot: int = 0,
) -> Check:
    if monitor.monitor_type == "heartbeat":
        return Check(
            monitor_id=monitor.id,
            kind="heartbeat",
            status_code=None,
            response_time_ms=0.0,
            success=True,
            error=None,
            checked_at=checked_at,
        )
    if historical_day is not None:
        status_code, success, error = _historical_error(monitor.name, historical_day, slot)
        return Check(
            monitor_id=monitor.id,
            kind="http",
            status_code=status_code,
            response_time_ms=_latency(config, index, index % 53 == 0),
            success=success,
            error=error,
            checked_at=checked_at,
        )
    status_code: int | None = 200
    success = True
    error: str | None = None
    spike = index % 47 == 0 or index % 83 == 0
    if monitor.name == "GitHub API" and index in {100, 400}:
        status_code = 404 if index == 100 else 500
        success = False
        error = f"Beklenmeyen HTTP {status_code} (beklenen: 200)"
    elif monitor.name == "JSONPlaceholder" and 204 <= index <= 206:
        status_code = 500
        success = False
        error = "Beklenmeyen HTTP 500 (beklenen: 200)"
    elif monitor.name == "Open-Meteo Hava Durumu" and (index == 90 or 132 <= index <= 133):
        status_code = 404 if index == 90 else 503
        success = False
        error = f"Beklenmeyen HTTP {status_code} (beklenen: 200)"
    elif (
        monitor.name == "Ödeme Servisi (Demo)"
        and index >= int(24 * 3600 / monitor.interval_seconds) - 4
    ):
        status_code = None
        success = False
        error = "Bağlantı kurulamadı"
    return Check(
        monitor_id=monitor.id,
        kind="http",
        status_code=status_code,
        response_time_ms=_latency(config, index, spike),
        success=success,
        error=error,
        checked_at=checked_at,
    )


async def seed_demo_data(force: bool = False) -> bool:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count(Monitor.id)))
        if count and not force:
            return False

        if force:
            await session.execute(delete(Notification))
            await session.execute(delete(Incident))
            await session.execute(delete(Check))
            await session.execute(delete(MaintenanceWindow))
            await session.execute(delete(Monitor))
            await session.execute(delete(AlertChannel))
            await session.execute(delete(ApiKey))
            await session.execute(delete(Workspace))
            await session.commit()

        workspace = Workspace(
            id=1,
            name="PulseWatch",
            status_page_title="PulseWatch · Servis Durumu",
            status_page_description="Servislerin canlı durumu ve son dönemdeki kesintiler.",
            support_url="https://example.com/destek",
            timezone="Europe/Istanbul",
        )
        session.add(workspace)

        now = utcnow().replace(microsecond=0)
        monitors: list[Monitor] = []
        all_checks: list[Check] = []

        for config in DEMO_MONITORS:
            interval = config["interval_seconds"]
            is_heartbeat = config.get("monitor_type") == "heartbeat"
            steps = 24 if is_heartbeat else int(24 * 3600 / interval)
            start = now - timedelta(seconds=steps * interval)
            monitor = Monitor(
                name=config["name"],
                description=config.get("description"),
                url=config.get("url"),
                monitor_type=config.get("monitor_type", "http"),
                method=config["method"],
                headers={},
                expected_codes=config["expected_codes"],
                expected_keyword=config.get("expected_keyword"),
                json_path=config.get("json_path"),
                expected_json_value=config.get("expected_json_value"),
                slow_threshold_ms=config.get("slow_threshold_ms"),
                heartbeat_token=config.get("heartbeat_token"),
                heartbeat_grace_seconds=config.get("heartbeat_grace_seconds", 60),
                last_heartbeat_at=now - timedelta(minutes=12)
                if config.get("monitor_type") == "heartbeat"
                else None,
                tags=config["tags"],
                interval_seconds=interval,
                timeout_seconds=config["timeout_seconds"],
                active=True,
                alert_after_failures=2,
                alert_channel_ids=[],
                status="unknown",
                ssl_expires_at=now + timedelta(days=config["ssl_days"])
                if config.get("ssl_days")
                else None,
                ssl_issuer=config.get("ssl_issuer"),
                created_at=now - timedelta(days=62),
                updated_at=now,
            )
            session.add(monitor)
            await session.flush()
            monitors.append(monitor)

            checks: list[Check] = []
            for index in range(steps + 1):
                checked_at = start + timedelta(seconds=interval * index)
                checks.append(_build_check(monitor, config, index, checked_at))
            all_checks.extend(checks)

            if monitor.monitor_type != "heartbeat":
                for day_offset in range(29, 0, -1):
                    base = (now - timedelta(days=day_offset)).replace(
                        minute=0, second=0, microsecond=0
                    )
                    for slot in range(0, 24, 1):
                        checked_at = base + timedelta(hours=slot)
                        all_checks.append(
                            _build_check(
                                monitor,
                                config,
                                day_offset * 100 + slot,
                                checked_at,
                                historical_day=day_offset,
                                slot=slot,
                            )
                        )
            else:
                for hour_offset in range(25, 24 * 30):
                    checked_at = now - timedelta(hours=hour_offset)
                    all_checks.append(
                        Check(
                            monitor_id=monitor.id,
                            kind="heartbeat",
                            status_code=None,
                            response_time_ms=0.0,
                            success=True,
                            error=None,
                            checked_at=checked_at,
                        )
                    )

            last = checks[-1]
            monitor.last_checked_at = last.checked_at
            monitor.last_status_code = last.status_code
            monitor.last_response_time_ms = last.response_time_ms
            monitor.last_error = last.error
            monitor.next_check_at = (
                now + timedelta(seconds=interval) if monitor.monitor_type == "http" else None
            )
            if monitor.name == "Ödeme Servisi (Demo)":
                monitor.status = "down"
                monitor.consecutive_failures = 5
            else:
                monitor.status = "up"
                monitor.consecutive_failures = 0

        session.add_all(all_checks)
        await session.commit()

        payment = next(m for m in monitors if m.name == "Ödeme Servisi (Demo)")
        json_monitor = next(m for m in monitors if m.name == "JSONPlaceholder")
        weather = next(m for m in monitors if m.name == "Open-Meteo Hava Durumu")
        github = next(m for m in monitors if m.name == "GitHub API")

        payment_incident = Incident(
            monitor_id=payment.id,
            status="open",
            cause="Bağlantı kurulamadı",
            last_error="Bağlantı kurulamadı",
            failure_count=5,
            acknowledged=False,
            started_at=now - timedelta(minutes=4),
        )
        json_incident = Incident(
            monitor_id=json_monitor.id,
            status="resolved",
            cause="HTTP 500",
            last_error="Beklenmeyen HTTP 500 (beklenen: 200)",
            failure_count=3,
            acknowledged=True,
            started_at=now - timedelta(hours=7),
            resolved_at=now - timedelta(hours=6, minutes=50),
        )
        weather_incident = Incident(
            monitor_id=weather.id,
            status="resolved",
            cause="HTTP 503",
            last_error="Beklenmeyen HTTP 503 (beklenen: 200)",
            failure_count=2,
            acknowledged=True,
            started_at=now - timedelta(hours=13),
            resolved_at=now - timedelta(hours=12, minutes=50),
        )
        github_incident = Incident(
            monitor_id=github.id,
            status="resolved",
            cause="HTTP 500",
            last_error="Beklenmeyen HTTP 500 (beklenen: 200)",
            failure_count=4,
            acknowledged=True,
            started_at=now - timedelta(days=6, hours=3),
            resolved_at=now - timedelta(days=6, hours=2, minutes=37),
        )
        session.add_all([payment_incident, json_incident, weather_incident, github_incident])
        await session.flush()

        session.add_all(
            [
                Notification(
                    monitor_id=payment.id,
                    incident_id=payment_incident.id,
                    kind="down",
                    title=f"{payment.name} yanıt vermiyor",
                    message=(
                        f"{payment.name} ({payment.url}) kontrolü başarısız: Bağlantı kurulamadı. "
                        "Üst üste 5. hata. Son yanıt süresi: 12.4 ms"
                    ),
                    read=False,
                    webhook_status="none",
                    created_at=now - timedelta(minutes=3),
                ),
                Notification(
                    monitor_id=json_monitor.id,
                    incident_id=json_incident.id,
                    kind="recovery",
                    title=f"{json_monitor.name} tekrar çevrimiçi",
                    message=(
                        f"{json_monitor.name} ({json_monitor.url}) yeniden yanıt veriyor. "
                        "Kesinti süresi: 10 dk. HTTP 200 · 81.3 ms"
                    ),
                    read=True,
                    webhook_status="none",
                    created_at=now - timedelta(hours=6, minutes=50),
                ),
                Notification(
                    monitor_id=weather.id,
                    incident_id=weather_incident.id,
                    kind="recovery",
                    title=f"{weather.name} tekrar çevrimiçi",
                    message=(
                        f"{weather.name} ({weather.url}) yeniden yanıt veriyor. "
                        "Kesinti süresi: 10 dk. HTTP 200 · 168.2 ms"
                    ),
                    read=True,
                    webhook_status="none",
                    created_at=now - timedelta(hours=12, minutes=50),
                ),
            ]
        )

        maintenance = MaintenanceWindow(
            monitor_id=weather.id,
            title="Hava durumu API'si planlı bakım",
            description=(
                "Sağlayıcı tarafındaki altyapı güncellemesi nedeniyle kısa süreli "
                "yanıt gecikmeleri bekleniyor."
            ),
            starts_at=now + timedelta(days=2, hours=1),
            ends_at=now + timedelta(days=2, hours=2),
        )
        session.add(maintenance)
        await session.commit()

    print(
        f"Demo verisi hazır: {len(monitors)} monitör, {len(all_checks)} kontrol kaydı, "
        "1 açık olay ve planlı bakım."
    )
    return True


async def seed_if_empty() -> bool:
    return await seed_demo_data(force=False)


async def _main(reset: bool) -> None:
    await init_db()
    seeded = await seed_demo_data(force=reset)
    if not seeded:
        print("Veritabanında zaten veri var. Sıfırlamak için --reset kullanın.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PulseWatch demo verisi oluşturur")
    parser.add_argument(
        "--reset", action="store_true", help="Mevcut monitörleri silip yeniden oluştur"
    )
    args = parser.parse_args()
    asyncio.run(_main(reset=args.reset))
