"""Regression tests for the defects found in the spatial intelligence audit.

Each of these covers something that was live-broken on 2026-07-29 and passed
review because the code existed and looked right. They are written against the
specific failure, not the general shape of the function.
"""
from hali.ai import spatial_clustering
from hali.ingestion.spatial_join import countries_for_geometry

SQUARE = '{"type":"Polygon","coordinates":[[[34,0],[35,0],[35,1],[34,1],[34,0]]]}'


class FakeConn:
    """Records the SQL and args it was called with."""

    def __init__(self, rows=None, raises=False):
        self._rows = rows or []
        self._raises = raises
        self.calls: list[tuple] = []

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        if self._raises:
            raise RuntimeError("connection lost")
        return self._rows


class TestCrossBorderAttribution:
    """FEWS NET and HAPI recorded only the country whose package was downloaded.

    Measured on the live feed: 85 of 445 FEWS NET alerts and 13 of 76 HAPI
    alerts had geometry crossing a border they did not list, so subscriber
    targeting silently skipped everyone on the other side.
    """

    async def test_neighbouring_country_is_added(self):
        conn = FakeConn([{"iso2": "KE"}, {"iso2": "SO"}])
        assert await countries_for_geometry(conn, SQUARE, always_include="KE") == ["KE", "SO"]

    async def test_download_country_is_kept_even_if_geometry_misses_it(self):
        """The publisher's own attribution is authoritative for provenance."""
        conn = FakeConn([{"iso2": "SO"}])
        assert await countries_for_geometry(conn, SQUARE, always_include="KE") == ["KE", "SO"]

    async def test_result_is_deduplicated_and_ordered(self):
        conn = FakeConn([{"iso2": "SO"}, {"iso2": "KE"}, {"iso2": "KE"}])
        assert await countries_for_geometry(conn, SQUARE, always_include="KE") == ["KE", "SO"]

    async def test_lookup_failure_degrades_to_the_download_country(self):
        """A transient error must downgrade attribution, never drop the alert."""
        conn = FakeConn(raises=True)
        assert await countries_for_geometry(conn, SQUARE, always_include="ET") == ["ET"]

    async def test_lookup_failure_without_a_fallback_returns_empty(self):
        conn = FakeConn(raises=True)
        assert await countries_for_geometry(conn, SQUARE) == []

    async def test_uses_st_intersects_against_real_boundaries(self):
        conn = FakeConn([{"iso2": "KE"}])
        await countries_for_geometry(conn, SQUARE, always_include="KE")
        sql = conn.calls[0][0]
        assert "ST_Intersects" in sql
        assert "FROM countries" in sql


class TestHotspotCoverageIsHazardSpecific:
    """The coverage check asked "is any alert nearby", not "is this hazard
    already warned about".

    With 537 active alerts that suppressed 98.3% of sampled IGAD land, so no
    volume of community reports could ever have produced a hotspot.
    """

    async def test_hazard_type_is_matched(self):
        conn = FakeConn([{"covered": False}])
        pool = _pool(conn)
        await spatial_clustering._covered_by_active_alert(pool, [(35.0, 3.0)], ["flood"])
        sql, args = conn.calls[0]
        assert "a.hazard_type = c.hazard" in sql
        assert ["flood"] in args

    async def test_country_scoped_sources_cannot_provide_coverage(self):
        """An IFRC appeal covers the whole country, so every point sits inside
        one — letting it count would re-suppress everything."""
        assert set(spatial_clustering.NATIONAL_SCOPE_SOURCES) == {"ifrc", "who"}

        conn = FakeConn([{"covered": False}])
        await spatial_clustering._covered_by_active_alert(_pool(conn), [(35.0, 3.0)], ["flood"])
        sql, args = conn.calls[0]
        assert "a.source <> ALL" in sql
        assert ["ifrc", "who"] in args

    async def test_one_batched_query_regardless_of_cluster_count(self):
        conn = FakeConn([{"covered": False}] * 4)
        centroids = [(35.0, 3.0), (36.0, 4.0), (37.0, 5.0), (38.0, 6.0)]
        await spatial_clustering._covered_by_active_alert(
            _pool(conn), centroids, ["flood", "drought", "flood", "locust"]
        )
        assert len(conn.calls) == 1

    async def test_results_stay_aligned_with_their_clusters(self):
        """Ordering matters: a mismatch silently suppresses the wrong hotspot."""
        conn = FakeConn([{"covered": True}, {"covered": False}, {"covered": True}])
        got = await spatial_clustering._covered_by_active_alert(
            _pool(conn), [(35.0, 3.0), (36.0, 4.0), (37.0, 5.0)], ["flood", "drought", "flood"]
        )
        assert got == [True, False, True]
        assert "WITH ORDINALITY" in conn.calls[0][0]
        assert "ORDER BY c.ord" in conn.calls[0][0]


class TestCompoundRiskAreaIsUnioned:
    """Summing per-alert intersections double-counted every overlap.

    Kenya reported 2,708,468 km² of coverage against a true national area of
    585,764 km² — 4.6x the country — and the score built on it ran to 51,688,807.
    """

    def test_area_is_unioned_not_summed(self):
        from hali.repositories.spatial import SpatialRepository

        sql = SpatialRepository.compound_risk.__doc__
        assert "UNIONED, NOT SUMMED" in sql

    def test_query_dissolves_overlapping_footprints(self):
        import inspect

        from hali.repositories.spatial import SpatialRepository

        source = inspect.getsource(SpatialRepository.compound_risk)
        # The union is what dissolves the stack of overlapping district polygons.
        assert "ST_Union(ST_Intersection(a.geom, c.geom))" in source
        # And the bands are made disjoint so each km² counts once, at its worst.
        assert "ST_Difference" in source
        # Country-scoped advisories are excluded from the area maths.
        assert "a.source NOT IN ('ifrc', 'who')" in source

    def test_score_is_bounded(self):
        import inspect

        from hali.repositories.spatial import SpatialRepository

        source = inspect.getsource(SpatialRepository.compound_risk)
        assert "LEAST(" in source and "100.0" in source


class TestPopulationBackfillCoversTheWholeFeed:
    """The local cap was 500 against 523 eligible alerts, so the last 23 sat
    outside every run and kept whatever exposure they were first given."""

    def test_limit_clears_the_live_feed_with_headroom(self):
        from hali.services.population import DEFAULT_LOCAL_BACKFILL_LIMIT

        assert DEFAULT_LOCAL_BACKFILL_LIMIT >= 5000

    def test_country_scoped_sources_stay_excluded(self):
        from hali.services.population import COUNTRY_SCOPED_SOURCES

        assert set(COUNTRY_SCOPED_SOURCES) == {"ifrc", "who"}


def _pool(conn):
    class _Ctx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *exc):
            return False

    class _Pool:
        def acquire(self):
            return _Ctx()

    return _Pool()
