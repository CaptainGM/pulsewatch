from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "PulseWatch"
    version: str = "2.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./data/pulsewatch.db"
    redis_url: str = ""

    cors_origins: str = "http://localhost:8010,http://localhost:5180"

    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 5
    scheduler_batch_size: int = 50
    check_concurrency: int = 8

    retention_days: int = 30

    telegram_api_base: str = "https://api.telegram.org"
    frontend_dist: str = ""

    public_url: str = "http://localhost:8010"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://openidconnect.googleapis.com/v1/userinfo"
    oauth_allowed_domains: str = ""
    oauth_auto_create: bool = False
    alert_webhook_url: str = ""
    webhook_signing_secret: str = ""
    frontend_url: str = "http://localhost:8010"
    public_status_path: str = "/status"

    workspace_name: str = "PulseWatch"
    status_page_title: str = "PulseWatch Durum Sayfası"
    status_page_description: str = (
        "Tüm servislerin canlı durumu ve geçmiş erişilebilirlik bilgileri."
    )

    seed_demo: bool = False

    allow_private_networks: bool = True
    auth_enabled: bool = False
    admin_email: str = "admin@pulsewatch.local"
    admin_password: str = "pulsewatch"
    jwt_secret: str = "change-me-in-production-pulsewatch-secret"
    access_token_minutes: int = 720

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw or raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
