"""Loader unit tests with mocked DB calls."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from hali.ingestion.loader import Loader
from hali.ingestion.models import HazardType, NormalisedAlert, RawPayload, Severity, SourceName
from hali.ingestion.normaliser import bbox_to_multipolygon_geojson


@pytest.fixture
def loader(mock_pool):
    pool, conn = mock_pool
    return Loader(pool), conn


def make_normalised(severity="red") -> NormalisedAlert:
    return NormalisedAlert(
        source=SourceName.GDACS,
        source_event_id="test-evt-001",
        hazard_type=HazardType.FLOOD,
        severity=Severity(severity),
        geojson_geometry=bbox_to_multipolygon_geojson(36.0, -1.0, 42.0, 5.0),
        affected_countries=["KE"],
        valid_from=None,
        valid_to=None,
        dedup_hash=NormalisedAlert.build_dedup_hash("gdacs", "test-evt-001", severity),
    )


@pytest.mark.asyncio
async def test_store_raw_returns_uuid(loader):
    ldr, conn = loader
    expected_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": expected_id})
    raw = RawPayload(source=SourceName.GDACS, raw_data={"test": True}, source_event_id="test-001")
    assert await ldr.store_raw(raw) == expected_id
    conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_alert_returns_true_on_insert(loader):
    ldr, conn = loader
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    assert await ldr.upsert_alert(make_normalised()) is True


@pytest.mark.asyncio
async def test_upsert_alert_returns_false_on_duplicate(loader):
    ldr, conn = loader
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    assert await ldr.upsert_alert(make_normalised()) is False
