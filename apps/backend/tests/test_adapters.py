import pytest

from hali.ingestion.chirps import ChirpsAdapter
from hali.ingestion.gfs import GfsAdapter
from hali.ingestion.icpac import IcpacAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_cls", [ChirpsAdapter, GfsAdapter, IcpacAdapter])
async def test_disabled_adapters_extract_empty(adapter_cls) -> None:
    adapter = adapter_cls(None)
    assert await adapter.extract() == []


def test_glofas_requires_key_when_instantiated_without_credentials(monkeypatch) -> None:
    from hali.config import settings
    from hali.ingestion.glofas import GloFASAdapter

    monkeypatch.setattr(settings, "glofas_cds_api_key", "")
    with pytest.raises(ValueError):
        GloFASAdapter(None)
