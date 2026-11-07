from datetime import UTC, datetime

from app.models import Monitor
from app.services.monitoring import (
    ProbeResult,
    _assert_response,
    _format_duration,
    _is_private_target,
    _json_path_value,
    _result_status,
)


class FakeResponse:
    def __init__(self, text="", payload=None):
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_json_path_reads_nested_values():
    payload = {"data": {"items": [{"name": "pulse"}]}}
    assert _json_path_value(payload, "$.data.items[0].name") == "pulse"


def test_private_addresses_are_detected():
    assert _is_private_target("http://127.0.0.1:8000/health")
    assert _is_private_target("http://localhost/health")
    assert not _is_private_target("https://api.github.com")


def test_duration_labels_are_turkish():
    assert _format_duration(45) == "45 sn"
    assert _format_duration(3700) == "1 sa 1 dk"
    assert _format_duration(90000) == "1 gün 1 sa"


def test_result_status_handles_paused_and_slow_checks():
    monitor = Monitor(name="Orders", url="https://example.com", active=False)
    fast = ProbeResult(True, 200, 80.0, None, datetime.now(UTC))
    slow = ProbeResult(True, 200, 900.0, None, datetime.now(UTC))

    assert _result_status(monitor, fast, maintenance=False) == "paused"

    monitor.active = True
    monitor.slow_threshold_ms = 500
    assert _result_status(monitor, fast, maintenance=False) == "up"
    assert _result_status(monitor, slow, maintenance=False) == "degraded"
    assert _result_status(monitor, fast, maintenance=True) == "maintenance"


def test_keyword_assertion():
    monitor = Monitor(name="Orders", url="https://example.com", expected_keyword="ok")

    assert _assert_response(monitor, FakeResponse(text="status: ok")) is None
    assert "bulunamadı" in _assert_response(monitor, FakeResponse(text="fail"))


def test_json_value_assertion():
    monitor = Monitor(
        name="Orders",
        url="https://example.com",
        json_path="$.status",
        expected_json_value="healthy",
    )

    assert _assert_response(monitor, FakeResponse(payload={"status": "healthy"})) is None
    assert "beklenen" in _assert_response(monitor, FakeResponse(payload={"status": "down"}))
