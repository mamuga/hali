"""Unit tests for WorldPop population exposure."""
import httpx
import pytest

from hali.services import population

POLYGON = {"type": "Polygon", "coordinates": [[[36.0, -1.0], [36.1, -1.0], [36.1, -0.9], [36.0, -0.9], [36.0, -1.0]]]}
MULTIPOLYGON = {"type": "MultiPolygon", "coordinates": [POLYGON["coordinates"], POLYGON["coordinates"]]}


@pytest.fixture
def patch_client(monkeypatch):
    # Bind the real class first — patching population.httpx.AsyncClient patches
    # the shared httpx module, so building the mock client afterwards would
    # recurse into the replacement.
    real_async_client = httpx.AsyncClient

    def apply(handler):
        def factory(**kwargs):
            return real_async_client(transport=httpx.MockTransport(handler))

        monkeypatch.setattr(population.httpx, "AsyncClient", factory)

    return apply


def test_multipolygon_splits_into_parts():
    assert len(population._to_polygons(MULTIPOLYGON)) == 2
    assert len(population._to_polygons(POLYGON)) == 1
    assert population._to_polygons({"type": "Point", "coordinates": [1, 2]}) == []


async def test_sums_all_parts_of_a_multipolygon(patch_client):
    def handler(request):
        return httpx.Response(200, json={"data": {"total_population": 1000.4}})

    patch_client(handler)
    # WorldPop refuses MultiPolygon, so each part is a separate call and summed.
    assert await population.compute_population_exposure(MULTIPOLYGON) == 2000


async def test_returns_none_when_any_part_fails(patch_client):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"data": {"total_population": 1000}})
        raise httpx.ReadTimeout("timeout")

    patch_client(handler)
    # A partial sum would silently under-report the affected population.
    assert await population.compute_population_exposure(MULTIPOLYGON) is None


async def test_rejects_unsupported_geometry(patch_client):
    patch_client(lambda request: httpx.Response(200, json={}))
    assert await population.compute_population_exposure({"type": "LineString", "coordinates": []}) is None


async def test_task_error_is_not_treated_as_success(patch_client):
    def handler(request):
        if "tasks" in str(request.url):
            # A failed task still reports status "finished".
            return httpx.Response(200, json={"status": "finished", "error": True, "error_message": "Unsupported Geometry"})
        return httpx.Response(200, json={"taskid": "abc"})

    patch_client(handler)
    population.TASK_POLL_INTERVAL_SECONDS = 0
    assert await population.compute_population_exposure(POLYGON) is None


async def test_polls_task_when_stats_defers(patch_client):
    def handler(request):
        if "tasks" in str(request.url):
            return httpx.Response(200, json={"status": "finished", "error": False, "data": {"total_population": 4242}})
        return httpx.Response(200, json={"taskid": "abc"})

    patch_client(handler)
    population.TASK_POLL_INTERVAL_SECONDS = 0
    assert await population.compute_population_exposure(POLYGON) == 4242


async def test_retries_a_transient_failure(patch_client):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("transient")
        return httpx.Response(200, json={"data": {"total_population": 500}})

    patch_client(handler)
    assert await population.compute_population_exposure(POLYGON) == 500
    assert calls["n"] == 2


def test_extract_total_handles_junk():
    assert population._extract_total({}) is None
    assert population._extract_total({"data": None}) is None
    assert population._extract_total({"data": {"total_population": None}}) is None
    assert population._extract_total({"data": {"total_population": "not a number"}}) is None
    assert population._extract_total({"data": {"total_population": "12.7"}}) == 12
