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

    enable_scheduler: bool = True
    enable_gdacs: bool = True
    enable_chirps: bool = False
    enable_gfs: bool = False
    enable_glofas: bool = False
    enable_icpac: bool = False

    gdacs_url: str = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    glofas_cds_api_key: str = ""
    glofas_cds_url: str = "https://cds.climate.copernicus.eu/api"
    icpac_digilib_base: str = "http://digilib.icpac.net"
    chirps_ftp_host: str = "ftp.chg.ucsb.edu"

    enable_admin_endpoints: bool = True
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
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
