from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class AwareDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Monitor(Base):
    __tablename__ = "monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(600), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    monitor_type: Mapped[str] = mapped_column(String(20), default="http", nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    headers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_codes: Mapped[list[int]] = mapped_column(JSON, default=lambda: [200], nullable=False)

    expected_keyword: Mapped[str | None] = mapped_column(String(500), nullable=True)
    json_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    expected_json_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    slow_threshold_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ssl_expires_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    ssl_issuer: Mapped[str | None] = mapped_column(String(300), nullable=True)

    heartbeat_token: Mapped[str | None] = mapped_column(
        String(80), unique=True, index=True, nullable=True
    )
    heartbeat_grace_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)

    interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    alert_after_failures: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    alert_channel_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False, index=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True, index=True)

    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    checks: Mapped[list["Check"]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    maintenance_windows: Mapped[list["MaintenanceWindow"]] = relationship(
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def expected_code_list(self) -> list[int]:
        return list(self.expected_codes or [200])

    @property
    def ssl_days_left(self) -> int | None:
        if self.ssl_expires_at is None:
            return None
        expires = self.ssl_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return max(0, (expires - utcnow()).days)


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (Index("ix_checks_monitor_checked_at", "monitor_id", "checked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="http", nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, nullable=False, index=True
    )

    monitor: Mapped[Monitor] = relationship(back_populates="checks")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_monitor_status", "monitor_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    cause: Mapped[str] = mapped_column(String(500), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)

    monitor: Mapped[Monitor] = relationship(back_populates="incidents")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), nullable=True, index=True
    )
    incident_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    webhook_status: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    webhook_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    deliveries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, nullable=False, index=True
    )


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int | None] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(600), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)

    monitor: Mapped[Monitor | None] = relationship(back_populates="maintenance_windows")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    last_used_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)


class Workspace(Base):
    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(120), default="PulseWatch", nullable=False)
    status_page_title: Mapped[str] = mapped_column(
        String(160), default="PulseWatch Durum Sayfası", nullable=False
    )
    status_page_description: Mapped[str] = mapped_column(
        String(600),
        default="Tüm servislerin canlı durumu ve geçmiş erişilebilirlik bilgileri.",
        nullable=False,
    )
    status_page_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    support_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Istanbul", nullable=False)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(300), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(20), default="local", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(AwareDateTime, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accent_color: Mapped[str] = mapped_column(String(7), default="#3ce7b0", nullable=False)
    custom_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sla_target_percent: Mapped[float] = mapped_column(Float, default=99.9, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class RegionCheck(Base):
    __tablename__ = "region_checks"
    __table_args__ = (Index("ix_region_checks_monitor_region", "monitor_id", "region"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_id: Mapped[int] = mapped_column(
        ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(40), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        AwareDateTime, default=utcnow, nullable=False, index=True
    )


JSONDict = dict[str, Any]
