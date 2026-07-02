from hali.config import Settings
from hali.ingestion.base import AdapterStatus, NormalizedAlert


class ChirpsAdapter:
    source = "chirps"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def status(self) -> AdapterStatus:
        enabled = self.settings.enable_chirps
        return AdapterStatus(self.source, enabled, "enabled" if enabled else "disabled", "chirps adapter requires source-specific credentials/data configuration before use")

    async def fetch(self) -> list[NormalizedAlert]:
        if not self.settings.enable_chirps:
            return []
        raise RuntimeError("chirps adapter is enabled but no data endpoint/credentials are configured")
