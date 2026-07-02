from hali.config import Settings
from hali.ingestion.base import AdapterStatus, NormalizedAlert


class GfsAdapter:
    source = "gfs"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def status(self) -> AdapterStatus:
        enabled = self.settings.enable_gfs
        return AdapterStatus(self.source, enabled, "enabled" if enabled else "disabled", "gfs adapter requires source-specific credentials/data configuration before use")

    async def fetch(self) -> list[NormalizedAlert]:
        if not self.settings.enable_gfs:
            return []
        raise RuntimeError("gfs adapter is enabled but no data endpoint/credentials are configured")
