"""The AOI service measures before it joins, and never invents a population."""
import pytest

from hali.schemas.spatial import MAX_AREA_KM2
from hali.services.spatial import SpatialService

SQUARE = {"type": "Polygon", "coordinates": [[[34, 2], [36, 2], [36, 4], [34, 4], [34, 2]]]}


class FakeRepo:
    def __init__(self, area, result=None):
        self.area = area
        self.result = result or {"area_km2": area, "alerts": []}
        self.area_calls = 0
        self.query_calls = 0

    async def aoi_area_km2(self, geojson):
        self.area_calls += 1
        return self.area

    async def query_polygon(self, geojson, lang):
        self.query_calls += 1
        return self.result


def _service(repo):
    service = SpatialService.__new__(SpatialService)
    service.repo = repo
    return service


async def test_oversized_area_is_rejected_before_any_spatial_join():
    """The whole point of measuring separately: never run the heavy query."""
    repo = FakeRepo(area=MAX_AREA_KM2 + 1)

    with pytest.raises(ValueError, match="exceeds"):
        await _service(repo).query_polygon(SQUARE, "en")

    assert repo.area_calls == 1
    assert repo.query_calls == 0, "the expensive query must not have run"


async def test_area_within_the_limit_runs_the_query():
    repo = FakeRepo(area=1000.0)

    result = await _service(repo).query_polygon(SQUARE, "en")

    assert repo.query_calls == 1
    assert result is repo.result


async def test_unparseable_geometry_is_a_value_error_not_a_crash():
    repo = FakeRepo(area=None)

    with pytest.raises(ValueError, match="could not be interpreted"):
        await _service(repo).query_polygon(SQUARE, "en")

    assert repo.query_calls == 0


async def test_language_is_passed_through_for_translated_headlines():
    repo = FakeRepo(area=1000.0)

    await _service(repo).query_polygon(SQUARE, "sw")

    assert repo.query_calls == 1


async def test_area_exactly_at_the_limit_is_allowed():
    repo = FakeRepo(area=float(MAX_AREA_KM2))

    await _service(repo).query_polygon(SQUARE, "en")

    assert repo.query_calls == 1
