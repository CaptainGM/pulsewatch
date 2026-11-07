from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.metrics import _percentile, build_series, compute_stats, status_class

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
SINCE = NOW - timedelta(hours=24)


def make_row(minutes_ago, *, success=True, status=200, ms=100.0, kind="http"):
    return SimpleNamespace(
        id=minutes_ago,
        monitor_id=1,
        kind=kind,
        checked_at=NOW - timedelta(minutes=minutes_ago),
        success=success,
        status_code=status,
        response_time_ms=ms,
        error=None if success else "hata",
        response_size_bytes=None,
    )


def test_status_class_groups_codes():
    assert status_class(200) == "2xx"
    assert status_class(404) == "4xx"
    assert status_class(503) == "5xx"
    assert status_class(None) == "net"


def test_percentile_interpolates_between_values():
    assert _percentile([1, 2, 3, 4], 50) == 2.5
    assert _percentile([10], 95) == 10
    assert _percentile([], 95) is None


def test_compute_stats_counts_errors_and_status_codes():
    rows = [make_row(i + 1, ms=100.0) for i in range(6)]
    rows.append(make_row(10, success=False, status=503))
    rows.append(make_row(20, success=False, status=404))
    rows.append(make_row(30, success=False, status=None, ms=0.0))

    stats = compute_stats(rows, window_hours=24, buckets=24, since=SINCE, until=NOW)

    assert stats["total_checks"] == 9
    assert stats["error_count"] == 3
    assert stats["uptime_percent"] == 66.67
    assert stats["error_rate_percent"] == 33.33
    assert stats["avg_response_ms"] == 100.0
    assert stats["class_counts"] == {"2xx": 6, "3xx": 0, "4xx": 1, "5xx": 1, "net": 1}
    assert {item["code"] for item in stats["status_counts"]} == {200, 404, 503}
    assert len(stats["series"]) == 24


def test_heartbeat_rows_do_not_affect_response_times():
    rows = [make_row(5, ms=0.0, kind="heartbeat"), make_row(6, ms=250.0)]
    stats = compute_stats(rows, window_hours=24, buckets=4, since=SINCE, until=NOW)

    assert stats["avg_response_ms"] == 250.0
    assert stats["class_counts"]["2xx"] == 1


def test_build_series_places_rows_in_the_right_bucket():
    rows = [make_row(24 * 60 - 1), make_row(1)]
    series = build_series(rows, SINCE, NOW, 24)

    assert series[0]["checks"] == 1
    assert series[-1]["checks"] == 1
    assert sum(point["checks"] for point in series) == 2
