# Entegrasyon

Örneklerde adres Docker kurulumuna göre `http://localhost:8080`. `start.bat` ile çalıştırdıysanız `http://localhost:8010` kullanın.

## Rozet

```html
<img src="http://localhost:8080/api/badge/overall.svg" alt="Servis durumu">
```

Tek bir monitör için `/api/badge/monitors/{id}.svg`. Rozetler herkese açıktır.

## Durum sayfası ve RSS

- `/status`: herkese açık durum sayfası.
- `/api/status-page/feed.xml`: kesinti akışı (RSS).

## JSON API

Anahtarlar sayfasından bir API anahtarı oluşturun ve `X-API-Key` başlığında gönderin.

| Yol | Anahtar gerekir mi |
|---|---|
| `/api/v1/status` | Hayır |
| `/api/v1/monitors` | Evet |
| `/api/v1/monitors/{id}/stats?hours=24` | Evet |
| `/api/v1/incidents` | Evet |

```python
import httpx

response = httpx.get(
    "http://localhost:8080/api/v1/monitors",
    headers={"X-API-Key": "pw_live_..."},
)
for monitor in response.json():
    print(monitor["name"], monitor["status"], monitor["uptime_percent"])
```

API anahtarını tarayıcıda çalışan koda koymayın.

## Webhook

Kanal olarak "Genel webhook" ekleyin. Bir olay olduğunda adresinize şöyle bir istek gider:

```json
{
  "event": "monitor.down",
  "kind": "down",
  "title": "GitHub API yanıt vermiyor",
  "text": "GitHub API kontrolü başarısız: HTTP 503",
  "monitor": {
    "id": 1,
    "name": "GitHub API",
    "url": "https://api.github.com",
    "monitor_type": "http",
    "method": "GET",
    "status": "down",
    "last_status_code": 503,
    "last_response_time_ms": 412.3
  },
  "incident_id": 12,
  "dashboard_url": "http://localhost:8080/monitors/1",
  "status_page_url": "http://localhost:8080/status",
  "timestamp": "2026-11-07T14:22:07+00:00"
}
```

`kind` değeri `down`, `recovery`, `degraded` veya `test` olur. Gizli anahtar girdiyseniz her istek `X-PulseWatch-Signature: sha256=...` başlığıyla imzalanır. İmzayı ham gövde üzerinden HMAC-SHA256 ile hesaplayıp karşılaştırın:

```python
import hashlib
import hmac


def is_valid(secret, raw_body, signature):
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")
```

## Heartbeat

Heartbeat monitörü ekleyin ve adresini kopyalayın. Görev bittiğinde o adrese istek atın. Süre içinde istek gelmezse monitör düşer ve bildirim gider.

```bash
0 * * * * /usr/local/bin/yedekle.sh && curl -fsS -X POST http://localhost:8080/api/ping/<token>
```

## Prometheus

`GET /api/metrics` Prometheus biçiminde metrik verir ve API anahtarı ister. Docker kurulumunda 8080 portundan erişilir:

```yaml
scrape_configs:
  - job_name: pulsewatch
    metrics_path: /api/metrics
    static_configs:
      - targets: ["localhost:8080"]
    http_headers:
      X-API-Key:
        values: ["pw_live_..."]
```

Hazır Grafana paneli: `docs/grafana/pulsewatch-dashboard.json`.

## Bölge ajanı

Başka bir konumdan kontrol yapmak için `scripts/agent.py` çalıştırın. Sonuçlar monitörün Bölgeler kartında görünür. Bildirimler yalnızca merkez kontrolünden gider.

```bash
python scripts/agent.py --url https://pulsewatch.sirketim.com --key pw_live_... --region eu-west --interval 60
```
