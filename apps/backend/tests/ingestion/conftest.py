"""Shared fixtures for ingestion tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.fixture
def gdacs_feature():
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[36.0, -1.0], [42.0, -1.0], [42.0, 5.0], [36.0, 5.0], [36.0, -1.0]]],
        },
        "properties": {
            "eventid": "1001234",
            "eventtype": "FL",
            "alertlevel": "Orange",
            "countryname": "Kenya",
            "iso3": "KEN",
            "fromdate": "2026-07-01T00:00:00Z",
            "todate": "2026-07-04T00:00:00Z",
            "eventname": "Flood Kenya",
        },
    }
