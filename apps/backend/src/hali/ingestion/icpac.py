from hali.config import Settings
from hali.ingestion.base import AdapterStatus, NormalizedAlert


class IcpacAdapter:
    source = "icpac"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def status(self) -> AdapterStatus:
        enabled = self.settings.enable_icpac
        return AdapterStatus(self.source, enabled, "enabled" if enabled else "disabled", "icpac adapter requires source-specific credentials/data configuration before use")

    async def fetch(self) -> list[NormalizedAlert]:
        if not self.settings.enable_icpac:
            return []
        raise RuntimeError("icpac adapter is enabled but no data endpoint/credentials are configured")
