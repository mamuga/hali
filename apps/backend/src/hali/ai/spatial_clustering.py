"""DBSCAN clustering of community reports into emerging hotspots.

An "emerging hotspot" is a spatial cluster of recent community reports that no
active official alert covers — i.e. the community is reporting something the
official feeds have not caught yet.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import asyncpg
import structlog

logger = structlog.get_logger(__name__)

EARTH_RADIUS_KM = 6371.0
CLUSTER_RADIUS_KM = 50.0
MIN_REPORTS_PER_CLUSTER = 3
REPORT_WINDOW_DAYS = 7
# A cluster whose centroid falls within this distance of an active alert is
# considered already covered by official warning, so it is not "emerging".
ALERT_COVERAGE_METRES = 100_000
# Report count at which confidence saturates at 1.0.
CONFIDENCE_SATURATION = 10


async def detect_emerging_hotspots(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Cluster recent reports and return those not covered by an active alert.

    Returns GeoJSON Feature dicts, ordered by report count descending.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ST_Y(location) AS lat, ST_X(location) AS lng, hazard_type, reported_at
            FROM community_reports
            WHERE reported_at > NOW() - make_interval(days => $1)
            """,
            REPORT_WINDOW_DAYS,
        )

    if len(rows) < MIN_REPORTS_PER_CLUSTER:
        logger.info("hotspots.insufficient_reports", report_count=len(rows))
        return []

    # DBSCAN is CPU-bound; keep it off the event loop.
    labels = await asyncio.to_thread(_cluster, [(r["lat"], r["lng"]) for r in rows])

    clusters: dict[int, list[asyncpg.Record]] = {}
    for row, label in zip(rows, labels, strict=True):
        if label != -1:  # -1 is DBSCAN's noise label
            clusters.setdefault(label, []).append(row)

    if not clusters:
        logger.info("hotspots.no_clusters", report_count=len(rows))
        return []

    ordered = list(clusters.values())
    centroids = [(_mean(c, "lng"), _mean(c, "lat")) for c in ordered]

    covered = await _covered_by_active_alert(pool, centroids)

    hotspots: list[dict[str, Any]] = []
    for cluster, (lng, lat), is_covered in zip(ordered, centroids, covered, strict=True):
        if is_covered:
            continue
        report_count = len(cluster)
        hotspots.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "report_count": report_count,
                    "dominant_hazard": _dominant_hazard(cluster),
                    "confidence": min(report_count / CONFIDENCE_SATURATION, 1.0),
                    "status": "UNCONFIRMED — no official alert",
                    "first_reported": min(r["reported_at"] for r in cluster),
                },
            }
        )

    hotspots.sort(key=lambda h: h["properties"]["report_count"], reverse=True)
    logger.info("hotspots.detected", clusters=len(ordered), emerging=len(hotspots), reports=len(rows))
    return hotspots


def _cluster(coords: list[tuple[float, float]]) -> list[int]:
    """Run DBSCAN over (lat, lng) pairs using great-circle distance."""
    import numpy as np
    from sklearn.cluster import DBSCAN

    radians = np.radians(np.array(coords))
    model = DBSCAN(
        eps=CLUSTER_RADIUS_KM / EARTH_RADIUS_KM,  # haversine metric works in radians
        min_samples=MIN_REPORTS_PER_CLUSTER,
        algorithm="ball_tree",
        metric="haversine",
    ).fit(radians)
    return [int(label) for label in model.labels_]


def _mean(cluster: list[asyncpg.Record], key: str) -> float:
    return sum(float(r[key]) for r in cluster) / len(cluster)


def _dominant_hazard(cluster: list[asyncpg.Record]) -> str:
    counts: dict[str, int] = {}
    for row in cluster:
        hazard = row["hazard_type"] or "other"
        counts[hazard] = counts.get(hazard, 0) + 1
    # Ties break alphabetically so repeated runs give a stable answer.
    return max(sorted(counts), key=lambda h: counts[h])


async def _covered_by_active_alert(pool: asyncpg.Pool, centroids: list[tuple[float, float]]) -> list[bool]:
    """One batched query for all centroids rather than a query per cluster."""
    lngs = [c[0] for c in centroids]
    lats = [c[1] for c in centroids]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT EXISTS (
                SELECT 1 FROM alerts a
                WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
                  AND ST_DWithin(
                      a.geom::geography,
                      ST_SetSRID(ST_MakePoint(c.lng, c.lat), 4326)::geography,
                      $3
                  )
            ) AS covered
            FROM unnest($1::float8[], $2::float8[]) WITH ORDINALITY AS c(lng, lat, ord)
            ORDER BY c.ord
            """,
            lngs,
            lats,
            ALERT_COVERAGE_METRES,
        )
    return [row["covered"] for row in rows]


async def store_hotspots(pool: asyncpg.Pool, hotspots: list[dict[str, Any]]) -> int:
    """Replace the hotspot table contents in a single transaction.

    Wrapping the delete and insert together means a concurrent map request never
    observes an empty table mid-refresh.
    """
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM emerging_hotspots")
        if not hotspots:
            return 0
        await conn.executemany(
            """
            INSERT INTO emerging_hotspots
                (location, report_count, dominant_hazard, confidence, first_reported)
            VALUES (ST_SetSRID(ST_MakePoint($1, $2), 4326), $3, $4, $5, $6)
            """,
            [
                (
                    h["geometry"]["coordinates"][0],
                    h["geometry"]["coordinates"][1],
                    h["properties"]["report_count"],
                    h["properties"]["dominant_hazard"],
                    h["properties"]["confidence"],
                    _as_datetime(h["properties"]["first_reported"]),
                )
                for h in hotspots
            ],
        )
    return len(hotspots)


def _as_datetime(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


async def run_hotspot_detection(pool: asyncpg.Pool) -> dict[str, Any]:
    """Detect and persist hotspots. Used by the scheduler and the admin endpoint."""
    hotspots = await detect_emerging_hotspots(pool)
    stored = await store_hotspots(pool, hotspots)
    return {"detected": len(hotspots), "stored": stored}
