import json
import re
from datetime import timedelta
from pathlib import Path

from prometheus_client.parser import text_string_to_metric_families

from app.database import SessionLocal
from app.models import Check, Incident, Monitor, utcnow

DASHBOARD = Path(__file__).resolve().parents[2] / "docs" / "grafana" / "pulsewatch-dashboard.json"


async def make_monitor(client, name="Metrik API"):
    response = await client.post(
        "/api/monitors", json={"name": name, "url": "https://example.com/m"}
    )
    return response.json()["id"]


async def make_key(client):
    return (await client.post("/api/api-keys", json={"name": "prometheus"})).json()["key"]


async def test_metrics_need_a_key_and_parse_as_prometheus(client):
    monitor_id = await make_monitor(client)
    key = await make_key(client)
    async with SessionLocal() as session:
        session.add(
            Check(
                monitor_id=monitor_id,
                kind="http",
                status_code=200,
                response_time_ms=120.0,
                success=True,
                checked_at=utcnow(),
            )
        )
        session.add(
            Check(
                monitor_id=monitor_id,
                kind="http",
                status_code=503,
                response_time_ms=90.0,
                success=False,
                error="HTTP 503",
                checked_at=utcnow(),
            )
        )
        monitor = await session.get(Monitor, monitor_id)
        monitor.status = "down"
        monitor.last_response_time_ms = 90.0
        await session.commit()

    assert (await client.get("/api/metrics")).status_code == 401

    response = await client.get("/api/metrics", headers={"X-API-Key": key})
    assert response.status_code == 200
    families = {family.name: family for family in text_string_to_metric_families(response.text)}

    up = {
        sample.labels["monitor"]: sample.value
        for sample in families["pulsewatch_monitor_up"].samples
    }
    assert up == {"Metrik API": 0.0}

    checks = {
        sample.labels["result"]: sample.value
        for sample in families["pulsewatch_checks_24h"].samples
        if sample.labels["monitor"] == "Metrik API"
    }
    assert checks == {"success": 1.0, "failure": 1.0}

    codes = {
        sample.labels["code"]: sample.value
        for sample in families["pulsewatch_http_status_24h"].samples
    }
    assert codes == {"200": 1.0, "503": 1.0}

    bearer = await client.get("/api/metrics", headers={"Authorization": f"Bearer {key}"})
    assert bearer.status_code == 200


async def test_grafana_dashboard_only_uses_exported_metrics(client):
    text = (await client.get("/api/metrics", headers={"X-API-Key": await make_key(client)})).text
    exported = set(re.findall(r"^# TYPE (\S+)", text, re.M))
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    expressions = [
        target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])
    ]
    used = {name for expr in expressions for name in re.findall(r"pulsewatch_[a-z0-9_]+", expr)}
    assert used
    assert used <= exported


async def test_site_settings_are_validated_and_normalized(client):
    bad_color = await client.put("/api/site", json={"accent_color": "red"})
    assert bad_color.status_code == 422

    bad_logo = await client.put("/api/site", json={"logo_url": "ftp://cdn.example.com/x.png"})
    assert bad_logo.status_code == 422

    bad_domain = await client.put("/api/site", json={"custom_domain": "bozuk"})
    assert bad_domain.status_code == 422

    saved = await client.put(
        "/api/site",
        json={
            "logo_url": "https://cdn.example.com/logo.png",
            "accent_color": "#FF8800",
            "custom_domain": "https://Durum.Sirketim.com/",
            "sla_target_percent": 99.95,
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["accent_color"] == "#ff8800"
    assert body["custom_domain"] == "durum.sirketim.com"
    assert body["status_url"] == "https://durum.sirketim.com/status"
    assert body["feed_url"] == "https://durum.sirketim.com/api/status-page/feed.xml"

    public = (await client.get("/api/site")).json()
    assert public["sla_target_percent"] == 99.95


async def test_incident_feed_lists_recent_incidents(client):
    monitor_id = await make_monitor(client, "Akış API")
    async with SessionLocal() as session:
        session.add(
            Incident(
                monitor_id=monitor_id,
                status="open",
                cause="HTTP 503",
                started_at=utcnow() - timedelta(minutes=5),
            )
        )
        await session.commit()

    response = await client.get("/api/status-page/feed.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/rss+xml")
    assert "<item>" in response.text
    assert "Akış API: Açık" in response.text


async def test_region_reports_are_stored_without_touching_status(client):
    monitor_id = await make_monitor(client, "Bölge API")
    key = await make_key(client)
    headers = {"X-API-Key": key}

    assert (await client.get("/api/agent/monitors")).status_code == 401
    listed = (await client.get("/api/agent/monitors", headers=headers)).json()
    assert any(item["id"] == monitor_id for item in listed)

    report = await client.post(
        "/api/agent/results",
        headers=headers,
        json={
            "region": "Eu-West",
            "results": [
                {
                    "monitor_id": monitor_id,
                    "success": True,
                    "status_code": 200,
                    "response_time_ms": 120,
                },
                {"monitor_id": 999999, "success": False},
            ],
        },
    )
    assert report.status_code == 201
    assert report.json() == {"region": "eu-west", "stored": 1, "skipped": 1}

    bad = await client.post(
        "/api/agent/results",
        headers=headers,
        json={"region": "bad region!", "results": [{"monitor_id": monitor_id, "success": True}]},
    )
    assert bad.status_code == 422

    regions = (await client.get(f"/api/monitors/{monitor_id}/regions")).json()
    assert [item["region"] for item in regions] == ["eu-west"]
    assert regions[0]["success"] is True

    monitor = (await client.get(f"/api/monitors/{monitor_id}")).json()
    assert monitor["status"] == "unknown"
