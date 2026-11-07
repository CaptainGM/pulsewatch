from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.models import Incident, MaintenanceWindow, Monitor
from app.services.sla import build_sla_rows, downtime_seconds

SINCE = datetime(2026, 1, 1, tzinfo=UTC)
UNTIL = datetime(2026, 1, 31, tzinfo=UTC)


def at(day, hour=0, minute=0):
    return datetime(2026, 1, day, hour, minute, tzinfo=UTC)


def test_single_incident_counts_its_duration():
    assert downtime_seconds([(at(10), at(10, 1))], [], SINCE, UNTIL) == 3600


def test_maintenance_window_is_excluded_from_downtime():
    seconds = downtime_seconds(
        [(at(10), at(10, 1))], [(at(10, 0, 30), at(10, 1, 30))], SINCE, UNTIL
    )
    assert seconds == 1800


def test_open_incident_runs_until_period_end_and_is_clipped():
    seconds = downtime_seconds([(at(30), None)], [], SINCE, UNTIL)
    assert seconds == 86400


def test_incident_before_period_only_counts_inside_it():
    before = (datetime(2025, 12, 31, 23, tzinfo=UTC), at(1, 1))
    assert downtime_seconds([before], [], SINCE, UNTIL) == 3600


def test_overlapping_incidents_are_not_double_counted():
    overlapping = [(at(5), at(5, 2)), (at(5, 1), at(5, 3))]
    assert downtime_seconds(overlapping, [], SINCE, UNTIL) == 3 * 3600


def test_report_rows_with_error_budget():
    report = build_sla_rows(
        monitors=[(1, "API A"), (2, "API B")],
        incidents=[(1, at(10), at(10, 1))],
        maintenance=[(None, at(20), at(20, 0, 10))],
        since=SINCE,
        until=UNTIL,
        target_percent=99.9,
    )
    first, second = report["monitors"]
    assert first["downtime_minutes"] == 60.0
    assert first["incidents"] == 1
    assert first["availability_percent"] == 99.861
    assert first["meets_target"] is False
    assert first["error_budget_minutes"] == -16.8
    assert second["availability_percent"] == 100.0
    assert second["meets_target"] is True
    assert report["overall_percent"] == 99.93


async def test_sla_endpoint_and_csv(client):
    async with SessionLocal() as session:
        monitor = Monitor(name="Ödeme", url="https://example.com/pay")
        session.add(monitor)
        await session.flush()
        now = datetime.now(UTC)
        session.add(
            Incident(
                monitor_id=monitor.id,
                status="resolved",
                cause="HTTP 503",
                started_at=now - timedelta(hours=2),
                resolved_at=now - timedelta(hours=1),
            )
        )
        session.add(
            MaintenanceWindow(
                monitor_id=monitor.id,
                title="Planlı",
                starts_at=now - timedelta(hours=2),
                ends_at=now - timedelta(hours=1, minutes=30),
            )
        )
        await session.commit()

    report = (await client.get("/api/sla?days=7")).json()
    row = report["monitors"][0]
    assert row["name"] == "Ödeme"
    assert row["downtime_minutes"] == 30.0

    csv = await client.get("/api/sla/export.csv?days=7")
    assert csv.status_code == 200
    assert csv.text.splitlines()[0].startswith("monitor,availability_percent")
    assert csv.text.splitlines()[1].startswith('"Ödeme",')


async def test_export_then_import_round_trip(client):
    created = await client.post(
        "/api/monitors",
        json={
            "name": "Sipariş",
            "url": "https://example.com/orders",
            "headers": {"Authorization": "Bearer gizli"},
            "webhook_url": "https://hooks.slack.com/services/SECRET",
            "tags": ["kritik"],
        },
    )
    assert created.status_code == 201

    export = (await client.get("/api/monitors/export")).json()
    assert export["version"] == 1
    item = export["monitors"][0]
    assert "headers" not in item
    assert "webhook_url" not in item
    assert "heartbeat_token" not in item
    assert item["name"] == "Sipariş"

    await client.delete(f"/api/monitors/{created.json()['id']}")
    first = await client.post("/api/monitors/import", json={"monitors": export["monitors"]})
    assert first.json() == {"created": 1, "skipped": 0, "errors": []}

    second = await client.post("/api/monitors/import", json={"monitors": export["monitors"]})
    assert second.json()["skipped"] == 1

    broken = await client.post(
        "/api/monitors/import",
        json={
            "monitors": [
                {"name": "", "url": "bozuk"},
                {"name": "Yeni", "url": "https://example.com/new"},
            ]
        },
    )
    body = broken.json()
    assert body["created"] == 1
    assert body["errors"][0]["index"] == 0
