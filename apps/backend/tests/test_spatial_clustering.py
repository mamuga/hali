"""Unit tests for DBSCAN hotspot detection (no database required)."""
from datetime import UTC, datetime, timedelta

import pytest

from hali.ai import spatial_clustering


class FakeConnection:
    def __init__(self, reports, covered):
        self._reports = reports
        self._covered = covered
        self.executed: list[tuple] = []

    async def fetch(self, sql, *args):
        if "community_reports" in sql:
            return self._reports
        # The batched coverage check returns one row per centroid, in order.
        return [{"covered": flag} for flag in self._covered]

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def executemany(self, sql, rows):
        self.executed.append((sql, rows))

    def transaction(self):
        return _NullContext()


class _NullContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _ConnContext(self._conn)


class _ConnContext:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _report(lat, lng, hazard="flood", age_hours=1):
    return {
        "id": f"{lat}-{lng}",
        "lat": lat,
        "lng": lng,
        "hazard_type": hazard,
        "reported_at": datetime.now(UTC) - timedelta(hours=age_hours),
    }


async def test_returns_empty_when_below_min_samples():
    conn = FakeConnection([_report(-1.29, 36.82), _report(-1.30, 36.83)], covered=[])
    assert await spatial_clustering.detect_emerging_hotspots(FakePool(conn)) == []


async def test_detects_uncovered_cluster():
    # Five reports within ~2km of each other in Nairobi.
    reports = [_report(-1.29 + i * 0.005, 36.82 + i * 0.005) for i in range(5)]
    conn = FakeConnection(reports, covered=[False])

    hotspots = await spatial_clustering.detect_emerging_hotspots(FakePool(conn))

    assert len(hotspots) == 1
    props = hotspots[0]["properties"]
    assert props["report_count"] == 5
    assert props["dominant_hazard"] == "flood"
    assert props["confidence"] == pytest.approx(0.5)
    assert hotspots[0]["geometry"]["type"] == "Point"
    lng, lat = hotspots[0]["geometry"]["coordinates"]
    assert lng == pytest.approx(36.83, abs=0.02)
    assert lat == pytest.approx(-1.28, abs=0.02)


async def test_cluster_covered_by_active_alert_is_not_emerging():
    reports = [_report(-1.29 + i * 0.005, 36.82 + i * 0.005) for i in range(5)]
    conn = FakeConnection(reports, covered=[True])
    assert await spatial_clustering.detect_emerging_hotspots(FakePool(conn)) == []


async def test_scattered_reports_do_not_form_a_cluster():
    # Points >50km apart across East Africa — DBSCAN should mark all as noise.
    reports = [_report(-1.29, 36.82), _report(9.02, 38.75), _report(2.05, 45.32)]
    conn = FakeConnection(reports, covered=[])
    assert await spatial_clustering.detect_emerging_hotspots(FakePool(conn)) == []


async def test_dominant_hazard_is_the_majority_label():
    reports = [
        _report(-1.29, 36.82, "flood"),
        _report(-1.295, 36.825, "flood"),
        _report(-1.30, 36.83, "flood"),
        _report(-1.305, 36.835, "drought"),
    ]
    conn = FakeConnection(reports, covered=[False])
    hotspots = await spatial_clustering.detect_emerging_hotspots(FakePool(conn))
    assert hotspots[0]["properties"]["dominant_hazard"] == "flood"


async def test_store_hotspots_replaces_in_one_transaction():
    conn = FakeConnection([], covered=[])
    hotspots = [
        {
            "geometry": {"coordinates": [36.82, -1.29]},
            "properties": {
                "report_count": 4,
                "dominant_hazard": "flood",
                "confidence": 0.4,
                "first_reported": datetime.now(UTC),
            },
        }
    ]
    stored = await spatial_clustering.store_hotspots(FakePool(conn), hotspots)

    assert stored == 1
    assert "DELETE FROM emerging_hotspots" in conn.executed[0][0]
    assert "INSERT INTO emerging_hotspots" in conn.executed[1][0]


async def test_store_hotspots_clears_table_when_nothing_detected():
    conn = FakeConnection([], covered=[])
    assert await spatial_clustering.store_hotspots(FakePool(conn), []) == 0
    # Stale hotspots must still be cleared, or the map keeps showing resolved ones.
    assert "DELETE FROM emerging_hotspots" in conn.executed[0][0]
