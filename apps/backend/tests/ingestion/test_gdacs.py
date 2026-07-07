"""GDACS adapter unit tests."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from hali.ingestion.gdacs import GdacsAdapter
from hali.ingestion.models import HazardType, RawPayload, Severity, SourceName


@pytest.fixture
def adapter(mock_pool):
    pool, _ = mock_pool
    return GdacsAdapter(pool)


def test_adapter_source_name(adapter):
    assert adapter.source == SourceName.GDACS


def test_validate_valid_feature(adapter, gdacs_feature):
    raw = RawPayload(source=SourceName.GDACS, raw_data=gdacs_feature, source_event_id="1001234")
    validated = adapter.validate(raw)
    assert validated is not None
    assert validated.hazard_type == HazardType.FLOOD
    assert validated.severity == Severity.ORANGE
    assert validated.source_event_id == "1001234"


def test_validate_rejects_missing_geometry(adapter):
    raw = RawPayload(source=SourceName.GDACS, raw_data={"type": "Feature", "geometry": None, "properties": {"eventid": "999"}}, source_event_id="999")
    assert adapter.validate(raw) is None


def test_transform_produces_multipolygon(adapter, gdacs_feature):
    raw = RawPayload(source=SourceName.GDACS, raw_data=gdacs_feature, source_event_id="1001234")
    validated = adapter.validate(raw)
    assert validated is not None
    normalised = adapter.transform(validated)
    assert normalised.geojson_geometry["type"] == "MultiPolygon"
    assert normalised.hazard_type == HazardType.FLOOD
    assert len(normalised.dedup_hash) == 32


def test_transform_dedup_hash_stable(adapter, gdacs_feature):
    raw = RawPayload(source=SourceName.GDACS, raw_data=gdacs_feature, source_event_id="1001234")
    validated = adapter.validate(raw)
    assert validated is not None
    assert adapter.transform(validated).dedup_hash == adapter.transform(validated).dedup_hash


@pytest.mark.asyncio
async def test_extract_handles_http_error(adapter):
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("refused")):
        assert await adapter.extract() == []


def test_validate_rejects_outside_east_africa(adapter):
    """GDACS ignores the bbox query param server-side, so validate() must
    reject events outside the 8 IGAD countries itself."""
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [8.5, 47.0]},
        "properties": {"eventid": "5000", "eventtype": "EQ", "alertlevel": "Green", "iso3": "CHE"},
    }
    raw = RawPayload(source=SourceName.GDACS, raw_data=feature, source_event_id="5000")
    assert adapter.validate(raw) is None


def test_unknown_event_type_maps_to_other(adapter):
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [36.8, -1.3]},
        "properties": {"eventid": "9999", "eventtype": "UNKNOWN_TYPE", "alertlevel": "Orange", "iso3": "KEN"},
    }
    raw = RawPayload(source=SourceName.GDACS, raw_data=feature, source_event_id="9999")
    validated = adapter.validate(raw)
    assert validated is not None
    assert validated.hazard_type == HazardType.OTHER
