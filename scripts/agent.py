import argparse
import time
from datetime import UTC, datetime

import httpx


def check(probe, monitor):
    started = time.perf_counter()
    try:
        response = probe.request(
            monitor["method"], monitor["url"], timeout=monitor["timeout_seconds"]
        )
    except httpx.HTTPError as exc:
        return {
            "monitor_id": monitor["id"],
            "success": False,
            "status_code": None,
            "response_time_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": type(exc).__name__,
        }
    success = response.status_code in monitor["expected_codes"]
    return {
        "monitor_id": monitor["id"],
        "success": success,
        "status_code": response.status_code,
        "response_time_ms": round((time.perf_counter() - started) * 1000, 1),
        "error": None if success else f"Beklenmeyen HTTP {response.status_code}",
    }


def run_round(api, probe, region):
    monitors = api.get("/agent/monitors").json()
    results = [check(probe, monitor) for monitor in monitors]
    if results:
        reply = api.post("/agent/results", json={"region": region, "results": results})
        reply.raise_for_status()
    stamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"{stamp} bolge={region} monitor={len(results)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="PulseWatch bölge ajanı")
    parser.add_argument("--url", required=True, help="PulseWatch adresi, örnek: http://localhost:8010")
    parser.add_argument("--key", required=True, help="API anahtarı")
    parser.add_argument("--region", required=True, help="Bölge adı, örnek: eu-west")
    parser.add_argument("--interval", type=int, default=60, help="Turlar arası bekleme (saniye)")
    parser.add_argument("--once", action="store_true", help="Tek tur çalışıp çıkar")
    args = parser.parse_args()

    headers = {"X-API-Key": args.key}
    with httpx.Client(base_url=args.url.rstrip("/") + "/api", headers=headers, timeout=20) as api:
        with httpx.Client(follow_redirects=True) as probe:
            while True:
                try:
                    run_round(api, probe, args.region)
                except httpx.HTTPError as exc:
                    print(f"baglanti hatasi: {type(exc).__name__}", flush=True)
                if args.once:
                    break
                time.sleep(args.interval)


if __name__ == "__main__":
    main()
