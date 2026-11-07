from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
MonitorType = Literal["http", "heartbeat"]
ChannelKind = Literal["slack", "discord", "telegram", "webhook"]


def validate_http_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("URL zorunludur")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Geçerli bir http:// veya https:// adresi girin")
    if len(value) > 2048:
        raise ValueError("URL 2048 karakterden uzun olamaz")
    return value


def coerce_expected_codes(value):
    if value is None or value == "":
        return [200]
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
        try:
            return [int(part) for part in parts]
        except ValueError as exc:
            raise ValueError(
                "Beklenen kodlar virgülle ayrılmış sayı olmalı (örn. 200,201)"
            ) from exc
    return value


def clean_expected_codes(codes: list[int]) -> list[int]:
    if not codes:
        raise ValueError("En az bir beklenen durum kodu girin")
    cleaned = sorted({int(code) for code in codes})
    for code in cleaned:
        if code < 100 or code > 599:
            raise ValueError("HTTP durum kodları 100 ile 599 arasında olmalı")
    return cleaned


def clean_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    cleaned: list[str] = []
    for tag in tags:
        value = str(tag).strip()
        if not value:
            continue
        if len(value) > 30:
            raise ValueError("Etiketler en fazla 30 karakter olabilir")
        if value.casefold() not in {item.casefold() for item in cleaned}:
            cleaned.append(value)
    if len(cleaned) > 10:
        raise ValueError("En fazla 10 etiket ekleyebilirsiniz")
    return cleaned


class MonitorBase(BaseModel):
    monitor_type: MonitorType = "http"
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=600)
    url: str | None = None
    method: HttpMethod = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = Field(default=None, max_length=20000)
    expected_codes: list[int] = Field(default_factory=lambda: [200])
    expected_keyword: str | None = Field(default=None, max_length=500)
    json_path: str | None = Field(default=None, max_length=300)
    expected_json_value: str | None = Field(default=None, max_length=500)
    slow_threshold_ms: int | None = Field(default=None, ge=1, le=600000)
    interval_seconds: int = Field(default=60, ge=10, le=86400)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    active: bool = True
    alert_after_failures: int = Field(default=2, ge=1, le=20)
    heartbeat_grace_seconds: int = Field(default=60, ge=10, le=86400)
    alert_channel_ids: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    webhook_url: str | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("İsim boş olamaz")
        return value

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("expected_codes", mode="before")
    @classmethod
    def _codes_before(cls, value):
        return coerce_expected_codes(value)

    @field_validator("expected_codes")
    @classmethod
    def _codes_after(cls, value: list[int]) -> list[int]:
        return clean_expected_codes(value)

    @field_validator("headers", mode="before")
    @classmethod
    def _headers_before(cls, value):
        return value or {}

    @field_validator("headers")
    @classmethod
    def _headers_after(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 30:
            raise ValueError("En fazla 30 header ekleyebilirsiniz")
        cleaned: dict[str, str] = {}
        for key, item in value.items():
            key = str(key).strip()
            if not key:
                raise ValueError("Header adı boş olamaz")
            cleaned[key] = str(item)
        return cleaned

    @field_validator("body")
    @classmethod
    def _body_clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("expected_keyword", "json_path", "expected_json_value")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_before(cls, value):
        return value or []

    @field_validator("tags")
    @classmethod
    def _tags_after(cls, value: list[str]) -> list[str]:
        return clean_tags(value)

    @field_validator("alert_channel_ids", mode="before")
    @classmethod
    def _channels_before(cls, value):
        return value or []

    @field_validator("alert_channel_ids")
    @classmethod
    def _channels_after(cls, value: list[int]) -> list[int]:
        return sorted({int(item) for item in value})

    @field_validator("webhook_url")
    @classmethod
    def _check_webhook(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return validate_http_url(value)

    @model_validator(mode="after")
    def _validate_type_fields(self):
        if self.monitor_type == "http":
            if not self.url:
                raise ValueError("HTTP monitörü için URL zorunludur")
            self.url = validate_http_url(self.url)
        else:
            if self.url:
                self.url = validate_http_url(self.url)
            else:
                self.url = None
        return self


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    monitor_type: MonitorType | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=600)
    url: str | None = None
    method: HttpMethod | None = None
    headers: dict[str, str] | None = None
    body: str | None = Field(default=None, max_length=20000)
    expected_codes: list[int] | None = None
    expected_keyword: str | None = Field(default=None, max_length=500)
    json_path: str | None = Field(default=None, max_length=300)
    expected_json_value: str | None = Field(default=None, max_length=500)
    slow_threshold_ms: int | None = Field(default=None, ge=1, le=600000)
    interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    active: bool | None = None
    alert_after_failures: int | None = Field(default=None, ge=1, le=20)
    heartbeat_grace_seconds: int | None = Field(default=None, ge=10, le=86400)
    alert_channel_ids: list[int] | None = None
    tags: list[str] | None = None
    webhook_url: str | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("İsim boş olamaz")
        return value

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return validate_http_url(value) if value else None

    @field_validator("expected_codes", mode="before")
    @classmethod
    def _codes_before(cls, value):
        if value is None:
            return None
        return coerce_expected_codes(value)

    @field_validator("expected_codes")
    @classmethod
    def _codes_after(cls, value: list[int] | None) -> list[int] | None:
        return clean_expected_codes(value) if value is not None else None

    @field_validator("headers")
    @classmethod
    def _headers_after(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        if len(value) > 30:
            raise ValueError("En fazla 30 header ekleyebilirsiniz")
        return {str(key).strip(): str(item) for key, item in value.items()}

    @field_validator("body")
    @classmethod
    def _body_clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("expected_keyword", "json_path", "expected_json_value")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_before(cls, value):
        return value

    @field_validator("tags")
    @classmethod
    def _tags_after(cls, value: list[str] | None) -> list[str] | None:
        return clean_tags(value) if value is not None else None

    @field_validator("alert_channel_ids")
    @classmethod
    def _channels_after(cls, value: list[int] | None) -> list[int] | None:
        return sorted({int(item) for item in value}) if value is not None else None

    @field_validator("webhook_url")
    @classmethod
    def _check_webhook(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return validate_http_url(value) if value else None

    @model_validator(mode="after")
    def _validate_update(self):
        if self.monitor_type == "http" and self.url is not None:
            self.url = validate_http_url(self.url)
        return self


class MonitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    url: str | None
    monitor_type: str
    method: str
    headers: dict[str, str]
    body: str | None
    expected_codes: list[int]
    expected_keyword: str | None
    json_path: str | None
    expected_json_value: str | None
    slow_threshold_ms: int | None
    ssl_expires_at: datetime | None
    ssl_issuer: str | None
    ssl_days_left: int | None
    heartbeat_token: str | None
    heartbeat_grace_seconds: int
    last_heartbeat_at: datetime | None
    interval_seconds: int
    timeout_seconds: int
    active: bool
    alert_after_failures: int
    alert_channel_ids: list[int]
    tags: list[str]
    webhook_url: str | None
    status: str
    last_status_code: int | None
    last_response_time_ms: float | None
    last_error: str | None
    last_checked_at: datetime | None
    next_check_at: datetime | None
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    kind: str
    status_code: int | None
    response_time_ms: float
    response_size_bytes: int | None
    success: bool
    error: str | None
    checked_at: datetime


class StatusCount(BaseModel):
    code: int
    count: int
    percent: float


class SeriesPoint(BaseModel):
    start: datetime
    avg_ms: float | None = None
    p95_ms: float | None = None
    checks: int = 0
    errors: int = 0
    uptime_percent: float | None = None
    classes: dict[str, int] = Field(default_factory=dict)


class LatencyBucket(BaseModel):
    label: str
    count: int


class MonitorStats(BaseModel):
    window_hours: int
    buckets: int
    total_checks: int
    success_count: int
    error_count: int
    uptime_percent: float | None
    avg_response_ms: float | None
    p50_response_ms: float | None = None
    p95_response_ms: float | None
    p99_response_ms: float | None = None
    min_response_ms: float | None
    max_response_ms: float | None
    error_rate_percent: float | None
    status_counts: list[StatusCount]
    class_counts: dict[str, int]
    series: list[SeriesPoint]
    latency_histogram: list[LatencyBucket] = Field(default_factory=list)
    last_check: CheckOut | None = None


class IncidentOut(BaseModel):
    id: int
    monitor_id: int
    monitor_name: str
    status: str
    cause: str
    last_error: str | None
    failure_count: int
    acknowledged: bool
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None


class NotificationOut(BaseModel):
    id: int
    monitor_id: int | None
    monitor_name: str | None
    incident_id: int | None
    kind: str
    title: str
    message: str
    read: bool
    webhook_status: str
    webhook_error: str | None
    deliveries: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class MonitorCard(BaseModel):
    id: int
    name: str
    description: str | None = None
    url: str | None = None
    monitor_type: str = "http"
    method: str
    status: str
    active: bool
    interval_seconds: int
    tags: list[str] = Field(default_factory=list)
    last_checked_at: datetime | None
    last_heartbeat_at: datetime | None = None
    last_response_time_ms: float | None
    last_status_code: int | None
    last_error: str | None
    ssl_days_left: int | None = None
    uptime_percent: float | None
    avg_response_ms: float | None
    error_count: int
    total_checks: int
    error_rate_percent: float | None
    sparkline: list[float]
    recent_checks: list[CheckOut]


class DashboardTotals(BaseModel):
    monitors: int
    up: int
    down: int
    degraded: int = 0
    maintenance: int = 0
    paused: int
    unknown: int
    checks: int
    errors: int


class DashboardOut(BaseModel):
    generated_at: datetime
    window_hours: int
    totals: DashboardTotals
    uptime_percent: float | None
    avg_response_ms: float | None
    p95_response_ms: float | None
    error_rate_percent: float | None
    class_counts: dict[str, int]
    status_counts: list[StatusCount] = []
    series: list[SeriesPoint]
    monitors: list[MonitorCard]
    recent_incidents: list[IncidentOut]
    unread_notifications: int


class CheckRunOut(BaseModel):
    check: CheckOut
    monitor: MonitorOut


class WebhookTestIn(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        return validate_http_url(value)


class WebhookTestOut(BaseModel):
    success: bool
    message: str


class UserOut(BaseModel):
    email: str
    name: str
    demo: bool = False
    role: str = "admin"


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class AuthConfigOut(BaseModel):
    enabled: bool
    demo: bool
    workspace_name: str
    version: str
    google: bool = False


class ChannelBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: ChannelKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Kanal adı boş olamaz")
        return value


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: ChannelKind | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    config: dict[str, Any]
    enabled: bool
    last_status: str
    last_error: str | None
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Anahtar adı boş olamaz")
        return value


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ApiKeyCreatedOut(ApiKeyOut):
    key: str


class MaintenanceBase(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=600)
    monitor_id: int | None = None
    starts_at: datetime
    ends_at: datetime

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Başlık boş olamaz")
        return value

    @model_validator(mode="after")
    def _validate_range(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("Bitiş zamanı başlangıçtan sonra olmalı")
        return self


class MaintenanceCreate(MaintenanceBase):
    pass


class MaintenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    monitor_id: int | None
    monitor_name: str | None = None
    starts_at: datetime
    ends_at: datetime
    active: bool = False
    created_at: datetime


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status_page_title: str
    status_page_description: str
    status_page_public: bool
    support_url: str | None
    timezone: str


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status_page_title: str | None = Field(default=None, min_length=1, max_length=160)
    status_page_description: str | None = Field(default=None, min_length=1, max_length=600)
    status_page_public: bool | None = None
    support_url: str | None = None
    timezone: str | None = Field(default=None, max_length=64)


class DailyUptime(BaseModel):
    day: date
    uptime_percent: float | None
    checks: int


class StatusComponent(BaseModel):
    id: int
    name: str
    description: str | None
    url: str | None
    monitor_type: str
    status: str
    tags: list[str]
    uptime_24h: float | None
    uptime_7d: float | None
    uptime_30d: float | None
    avg_response_ms: float | None
    last_checked_at: datetime | None
    last_heartbeat_at: datetime | None
    ssl_days_left: int | None
    daily: list[DailyUptime]


class StatusIncident(BaseModel):
    id: int
    monitor_id: int
    monitor_name: str
    status: str
    cause: str
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None


class StatusMaintenance(BaseModel):
    id: int
    title: str
    description: str | None
    monitor_id: int | None
    monitor_name: str | None
    starts_at: datetime
    ends_at: datetime
    active: bool


class StatusTotals(BaseModel):
    monitors: int
    operational: int
    degraded: int
    down: int
    maintenance: int


class StatusPageOut(BaseModel):
    workspace_name: str
    title: str
    description: str
    support_url: str | None
    overall_status: str
    generated_at: datetime
    uptime_24h: float | None
    uptime_7d: float | None
    uptime_30d: float | None
    avg_response_ms: float | None
    totals: StatusTotals
    components: list[StatusComponent]
    incidents: list[StatusIncident]
    maintenance: list[StatusMaintenance]
    public: bool


class StatusPageSettingsOut(BaseModel):
    title: str
    description: str
    public: bool
    support_url: str | None
    status_page_url: str
    badge_url: str


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "viewer"] = "viewer"


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["admin", "viewer"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


class UserListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    active: bool
    auth_provider: str
    created_at: datetime
    last_login_at: datetime | None


class SiteIn(BaseModel):
    logo_url: str | None = Field(default=None, max_length=500)
    accent_color: str = Field(default="#3ce7b0", pattern=r"^#[0-9a-fA-F]{6}$")
    custom_domain: str | None = Field(default=None, max_length=255)
    sla_target_percent: float = Field(default=99.9, ge=90, le=100)


class SiteOut(SiteIn):
    status_url: str
    feed_url: str


class RegionResultIn(BaseModel):
    monitor_id: int
    success: bool
    status_code: int | None = Field(default=None, ge=100, le=999)
    response_time_ms: float | None = Field(default=None, ge=0, le=600000)
    error: str | None = Field(default=None, max_length=500)


class RegionReportIn(BaseModel):
    region: str = Field(min_length=1, max_length=40)
    results: list[RegionResultIn] = Field(min_length=1, max_length=500)


class MonitorImportIn(BaseModel):
    monitors: list[dict[str, Any]] = Field(min_length=1, max_length=500)
