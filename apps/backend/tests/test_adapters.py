import pytest

from hali.config import Settings
from hali.ingestion.chirps import ChirpsAdapter
from hali.ingestion.gfs import GfsAdapter
from hali.ingestion.glofas import GlofasAdapter
from hali.ingestion.icpac import IcpacAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_cls", [ChirpsAdapter, GfsAdapter, GlofasAdapter, IcpacAdapter])
async def test_disabled_adapters_are_safe(adapter_cls) -> None:
    adapter = adapter_cls(Settings(enable_chirps=False, enable_gfs=False, enable_glofas=False, enable_icpac=False))
    status = await adapter.status()
    assert status.status == "disabled"
    assert await adapter.fetch() == []
