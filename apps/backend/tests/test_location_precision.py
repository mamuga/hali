"""Country-precision reports must stay out of the spatial layer.

USSD and WhatsApp reports are stored at a country interior point. Several of
them from one country are byte-identical coordinates, which DBSCAN reads as a
dense cluster and the heatmap renders as a hot blob — both describing the
channel rather than anything on the ground.

These assert on the emitted SQL because the filter lives there; a fake
connection cannot enforce a WHERE clause on its own.
"""
from hali.ai import spatial_clustering
from hali.repositories.reports import ReportRepository


class RecordingConnection:
    def __init__(self, result=None):
        self.queries: list[str] = []
        self._result = result

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        return []

    async def fetchval(self, sql, *args):
        self.queries.append(sql)
        return self._result


class RecordingPool:
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


async def test_hotspot_detection_reads_gps_reports_only():
    conn = RecordingConnection()
    await spatial_clustering.detect_emerging_hotspots(RecordingPool(conn))

    assert conn.queries, "expected the report query to run"
    assert "location_precision = 'gps'" in conn.queries[0]


async def test_heatmap_excludes_country_precision_reports():
    conn = RecordingConnection(result='{"type":"FeatureCollection","features":[]}')
    await ReportRepository(RecordingPool(conn)).heatmap(7)

    assert "location_precision = 'gps'" in conn.queries[0]


async def test_channel_reports_default_to_country_precision():
    """A caller that forgets the argument must not silently claim GPS accuracy."""
    captured = {}

    class Conn:
        async def fetchrow(self, sql, *args):
            captured["sql"] = sql
            captured["args"] = args
            return {"id": "x"}

    await ReportRepository(RecordingPool(Conn())).create_from_channel(
        hazard_type="flood",
        description="mafuriko",
        lat=0.02,
        lng=37.9,
        channel="ussd",
    )

    assert "location_precision" in captured["sql"]
    assert captured["args"][-1] == "country"
