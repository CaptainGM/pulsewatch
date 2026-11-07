from datetime import timedelta

from app.database import SessionLocal
from app.models import Check, Monitor, utcnow
from app.services.retention import prune_old_checks

MONITOR_PAYLOAD = {
    "name": "Orders API",
    "url": "https://example.com/health",
    "monitor_type": "http",
    "interval_seconds": 60,
}


async def test_health_endpoint_reports_ok(client):
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_create_and_list_monitor(client):
    created = await client.post("/api/monitors", json=MONITOR_PAYLOAD)
    assert created.status_code == 201
    assert created.json()["name"] == "Orders API"

    listed = await client.get("/api/monitors")
    assert [item["name"] for item in listed.json()] == ["Orders API"]


async def test_invalid_monitor_is_rejected(client):
    response = await client.post("/api/monitors", json={"name": "", "url": "not a url"})

    assert response.status_code == 422


async def test_empty_dashboard_has_no_status_codes(client):
    response = await client.get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["monitors"] == 0
    assert body["status_counts"] == []


async def test_integration_api_requires_a_key(client):
    assert (await client.get("/api/v1/status")).status_code == 200
    assert (await client.get("/api/v1/monitors")).status_code == 401

    created = await client.post("/api/api-keys", json={"name": "Test"})
    assert created.status_code == 201
    key = created.json()["key"]

    authorized = await client.get("/api/v1/monitors", headers={"X-API-Key": key})
    assert authorized.status_code == 200


async def test_prune_removes_only_old_checks(client):
    async with SessionLocal() as session:
        monitor = Monitor(name="Old data", url="https://example.com")
        session.add(monitor)
        await session.flush()
        session.add(
            Check(
                monitor_id=monitor.id,
                kind="http",
                status_code=200,
                response_time_ms=10.0,
                success=True,
                checked_at=utcnow() - timedelta(days=40),
            )
        )
        session.add(
            Check(
                monitor_id=monitor.id,
                kind="http",
                status_code=200,
                response_time_ms=10.0,
                success=True,
                checked_at=utcnow(),
            )
        )
        await session.commit()

    removed = await prune_old_checks()

    assert removed == 1
