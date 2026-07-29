from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../../.env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"
    api_port: int = 8000
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"
    database_url: str = "postgresql+asyncpg://hali:hali@localhost:5433/hali"
    migration_database_url: str = "postgresql://hali:hali@localhost:5433/hali"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    africastalking_username: str = "sandbox"
    africastalking_api_key: str | None = None

    # WhatsApp Cloud API (Meta)
    whatsapp_token: str = ""  # permanent system user access token
    whatsapp_phone_number_id: str = ""
    # WABA ID — distinct from the phone number ID; needed for the
    # Message Templates API, which is scoped to the business account.
    whatsapp_business_account_id: str = ""
    whatsapp_verify_token: str = "hali_webhook_2026"
    whatsapp_app_secret: str = ""  # Meta App Secret, used to verify X-Hub-Signature-256
    whatsapp_api_version: str = "v21.0"

    # AI model config
    ai_primary_model: str = "claude-sonnet-4-6"
    ai_gemini_model: str = "gemini-2.5-flash"
    # llama-4-scout was retired from Groq and 404s; 3.3-70b is the current
    # general-purpose multilingual model there.
    ai_groq_model: str = "llama-3.3-70b-versatile"
    ai_ensemble_enabled: bool = True
    ai_min_clarity_score: float = 0.6

    # Fallback API keys
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # AI processing config
    ai_backlog_batch_size: int = 10
    ai_max_concurrent_alerts: int = 5
    ground_truth_upgrade_threshold: int = 3

    enable_scheduler: bool = True
    enable_gdacs: bool = True
    enable_chirps: bool = False
    enable_gfs: bool = False
    enable_glofas: bool = False
    enable_icpac: bool = False
    # One-shot/quarterly static load, not part of the scheduled pipeline.
    enable_worldpop: bool = False
    enable_hapi: bool = True
    enable_fewsnet: bool = True
    enable_ifrc: bool = True
    enable_who: bool = True
    # HAPI's app identifier is base64("app:email") — self-service, no approval.
    hapi_email: str = "hali@example.org"
    hapi_app_identifier: str = ""

    gdacs_url: str = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    glofas_cds_api_key: str = ""
    glofas_cds_url: str = "https://cds.climate.copernicus.eu/api"
    icpac_digilib_base: str = "http://digilib.icpac.net"
    chirps_ftp_host: str = "ftp.chc.ucsb.edu"

    enable_admin_endpoints: bool = True
    # Outbound SMS/WhatsApp fan-out after an alert finishes AI processing.
    # Turn off to run the pipeline without messaging real subscribers.
    enable_broadcast: bool = True

    # Admin API key - protects /api/admin/* endpoints.
    # Set ADMIN_API_KEY in Railway env vars to a strong random string.
    # Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    admin_api_key: str = ""

    east_africa_bbox: str = "21,-12,52,24"
    gdacs_alert_levels: str = "Green,Orange,Red"
    gdacs_event_types: str = "FL,DR,TC,EQ,VO,WF"
    ingest_timeout_seconds: int = 30
    max_retry_attempts: int = 3

    test_mode: bool = Field(default=False, validation_alias="HALI_TEST_MODE")

    @property
    def asyncpg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)

    @property
    def sms_enabled(self) -> bool:
        return bool(self.africastalking_api_key and self.africastalking_username)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def ai_enabled(self) -> bool:
        """True if at least one AI provider (Claude, Gemini, Groq) is configured."""
        return bool(self.anthropic_api_key or self.gemini_api_key or self.groq_api_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def admin_auth_enabled(self) -> bool:
        """Admin key auth is active only when a key is configured."""
        return bool(self.admin_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
