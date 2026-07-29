"""The boundaries endpoint feeds both the map outlines and the outside-IGAD mask.

Its payload is downloaded by every map view, including on 2G, so the
simplification is not cosmetic — the raw 1:10m geometry is ~4x the bytes.
"""
import pytest

from hali.repositories.spatial import SpatialRepository
from hali.routers.spatial import DEFAULT_BOUNDARY_TOLERANCE


class RecordingConnection:
    def __init__(self, value):
        self.calls: list[tuple] = []
        self._value = value

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return self._value


class RecordingPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Ctx(self._conn)


class _Ctx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


EMPTY = '{"type":"FeatureCollection","features":[]}'


async def test_passes_the_tolerance_through_to_postgis():
    conn = RecordingConnection(EMPTY)
    await SpatialRepository(RecordingPool(conn)).countries_geojson(0.05)

    sql, args = conn.calls[0]
    assert args == (0.05,)


async def test_uses_topology_preserving_simplification():
    """ST_Simplify can self-intersect and drop rings, tearing holes in the mask."""
    conn = RecordingConnection(EMPTY)
    await SpatialRepository(RecordingPool(conn)).countries_geojson(DEFAULT_BOUNDARY_TOLERANCE)

    sql, _ = conn.calls[0]
    assert "ST_SimplifyPreserveTopology" in sql
    assert "ST_Simplify(" not in sql


async def test_returns_iso2_and_name_for_the_mask_and_labels():
    conn = RecordingConnection(EMPTY)
    await SpatialRepository(RecordingPool(conn)).countries_geojson(DEFAULT_BOUNDARY_TOLERANCE)

    sql, _ = conn.calls[0]
    assert "'iso2', iso2" in sql
    assert "'name', name" in sql


async def test_parses_a_json_string_result():
    conn = RecordingConnection(EMPTY)
    result = await SpatialRepository(RecordingPool(conn)).countries_geojson(0.02)

    assert result == {"type": "FeatureCollection", "features": []}


async def test_accepts_a_dict_result_unchanged():
    """asyncpg returns dict or str depending on codec registration."""
    payload = {"type": "FeatureCollection", "features": []}
    conn = RecordingConnection(payload)

    assert await SpatialRepository(RecordingPool(conn)).countries_geojson(0.02) is payload


def test_default_tolerance_is_small_enough_to_be_invisible_at_min_zoom():
    # ~2 km at the equator. The map's minimum zoom shows the whole region, where
    # a 2 km deviation is well under one pixel.
    assert 0 < DEFAULT_BOUNDARY_TOLERANCE <= 0.05


@pytest.mark.parametrize("tolerance", [0.0, 0.5])
async def test_boundary_tolerances_are_accepted(tolerance):
    """0 means full detail; the upper bound is the router's clamp."""
    conn = RecordingConnection(EMPTY)
    await SpatialRepository(RecordingPool(conn)).countries_geojson(tolerance)

    assert conn.calls[0][1] == (tolerance,)
