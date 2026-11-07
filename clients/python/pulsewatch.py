import httpx


class PulseWatch:
    def __init__(self, base_url, api_key=None, timeout=10):
        headers = {"X-API-Key": api_key} if api_key else {}
        self.http = httpx.Client(
            base_url=base_url.rstrip("/") + "/api",
            headers=headers,
            timeout=timeout,
        )

    def _get(self, path, **params):
        response = self.http.get(path, params=params or None)
        response.raise_for_status()
        return response.json()

    def status(self):
        return self._get("/v1/status")

    def monitors(self):
        return self._get("/v1/monitors")

    def incidents(self):
        return self._get("/v1/incidents")

    def stats(self, monitor_id, hours=24):
        return self._get(f"/v1/monitors/{monitor_id}/stats", hours=hours)

    def ping(self, token):
        response = self.http.post(f"/ping/{token}")
        response.raise_for_status()
        return response.json()
