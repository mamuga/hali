"""Population exposure per alert, via the free WorldPop stats API.

The result is cached in `alerts.population_exposed`. That column is nullable on
purpose: a failed or pending WorldPop call leaves NULL rather than 0, so the UI
can omit the figure instead of asserting that nobody lives in the alert zone.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import asyncpg
import httpx
import structlog

logger = structlog.get_logger(__name__)

WORLDPOP_STATS_URL = "https://api.worldpop.org/v1/services/stats"
WORLDPOP_TASK_URL = "https://api.worldpop.org/v1/tasks"
WORLDPOP_DATASET = "wpgppop"
WORLDPOP_YEAR = 2020
REQUEST_TIMEOUT_SECONDS = 60
# The stats endpoint always answers with a task id; the result arrives on the
# task endpoint a second or two later.
TASK_POLL_ATTEMPTS = 8
TASK_POLL_INTERVAL_SECONDS = 2.0
# WorldPop rejects MultiPolygon ("This operation supports only Polygons"), so a
# multi-part alert zone costs one call per part. Cap it so a pathological
# geometry cannot burn the ~1000 calls/day quota on a single alert.
MAX_PARTS_PER_GEOMETRY = 25
# WorldPop read-timeouts under parallel load — 13 simultaneous requests lost 8
# of them. Keep the fan-out narrow and retry rather than accept an undercount.
MAX_CONCURRENT_PARTS = 3
PART_ATTEMPTS = 3


async def compute_population_exposure(geojson_geometry: dict[str, Any]) -> int | None:
    """Estimated people inside a geometry, or None if WorldPop could not answer.

    Alert zones are MultiPolygons, which WorldPop refuses, so each part is
    requested separately and the results summed.

    Returns None unless every part answered. A partial sum is an undercount,
    and silently publishing "~150,000 people affected" when the true figure is
    higher is worse for an evacuation decision than publishing nothing — the
    next scheduled run retries.
    """
    parts = _to_polygons(geojson_geometry)
    if not parts:
        logger.warning("population.unsupported_geometry", geometry_type=geojson_geometry.get("type"))
        return None

    truncated = len(parts) > MAX_PARTS_PER_GEOMETRY
    if truncated:
        # Largest parts first, so a truncated sum still captures most of the population.
        parts = sorted(parts, key=_rough_area, reverse=True)[:MAX_PARTS_PER_GEOMETRY]

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PARTS)

    async def fetch(part: dict[str, Any]) -> int | None:
        async with semaphore:
            return await _population_for_polygon(client, part)

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            results = await asyncio.gather(*(fetch(part) for part in parts))
    except Exception as exc:
        # Never let an external API failure block alert processing.
        logger.warning("population.lookup_failed", error=str(exc))
        return None

    if any(value is None for value in results):
        answered = sum(1 for value in results if value is not None)
        logger.warning("population.incomplete", parts=len(parts), answered=answered)
        return None
    if truncated:
        logger.warning("population.truncated", parts=len(parts))
    return sum(results)


def _to_polygons(geometry: dict[str, Any]) -> list[dict[str, Any]]:
    geom_type = geometry.get("type")
    if geom_type == "Polygon":
        return [geometry]
    if geom_type == "MultiPolygon":
        return [{"type": "Polygon", "coordinates": part} for part in geometry.get("coordinates", [])]
    return []


def _rough_area(polygon: dict[str, Any]) -> float:
    """Bounding-box area of the outer ring — only used to rank parts by size."""
    try:
        ring = polygon["coordinates"][0]
        lngs = [point[0] for point in ring]
        lats = [point[1] for point in ring]
        return (max(lngs) - min(lngs)) * (max(lats) - min(lats))
    except (KeyError, IndexError, ValueError, TypeError):
        return 0.0


async def _population_for_polygon(client: httpx.AsyncClient, polygon: dict[str, Any]) -> int | None:
    params = {
        "dataset": WORLDPOP_DATASET,
        "year": WORLDPOP_YEAR,
        "geojson": json.dumps(polygon),
        "runasync": "false",
    }
    for attempt in range(1, PART_ATTEMPTS + 1):
        try:
            response = await client.get(WORLDPOP_STATS_URL, params=params)
            response.raise_for_status()
            payload = response.json()

            total = _extract_total(payload)
            if total is not None:
                return total

            task_id = payload.get("taskid")
            if task_id:
                return await _poll_task(client, task_id)

            logger.warning("population.unexpected_response")
            return None
        except Exception as exc:
            if attempt == PART_ATTEMPTS:
                logger.warning("population.part_failed", error=str(exc), error_type=type(exc).__name__, attempts=attempt)
                return None
            await asyncio.sleep(attempt * 2)
    return None


async def _poll_task(client: httpx.AsyncClient, task_id: str) -> int | None:
    for _ in range(TASK_POLL_ATTEMPTS):
        await asyncio.sleep(TASK_POLL_INTERVAL_SECONDS)
        response = await client.get(f"{WORLDPOP_TASK_URL}/{task_id}")
        response.raise_for_status()
        payload = response.json()
        # `error` is a boolean flag alongside `status`, so check it first —
        # a failed task still reports status "finished".
        if payload.get("error"):
            logger.warning("population.task_error", task_id=task_id, error=payload.get("error_message"))
            return None
        if payload.get("status") == "finished":
            return _extract_total(payload)
    logger.warning("population.task_timeout", task_id=task_id)
    return None


def _extract_total(payload: dict[str, Any]) -> int | None:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    total = data.get("total_population")
    if total is None:
        return None
    try:
        return int(float(total))
    except (TypeError, ValueError):
        return None


async def backfill_population_exposure(pool: asyncpg.Pool, limit: int = 25) -> dict[str, Any]:
    """Fill population_exposed for alerts that do not have it yet.

    Bounded per run: WorldPop allows ~1000 calls/day and this runs on a schedule,
    so a large backlog drains over several runs rather than exhausting the quota.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ST_AsGeoJSON(geom) AS geojson
            FROM alerts
            WHERE population_exposed IS NULL
              AND (valid_to > NOW() OR valid_to IS NULL)
            ORDER BY processed_at DESC
            LIMIT $1
            """,
            limit,
        )

    updated = 0
    failed = 0
    for row in rows:
        total = await compute_population_exposure(json.loads(row["geojson"]))
        if total is None:
            failed += 1
            continue
        async with pool.acquire() as conn:
            await conn.execute("UPDATE alerts SET population_exposed = $2 WHERE id = $1", row["id"], total)
        updated += 1

    logger.info("population.backfill_complete", considered=len(rows), updated=updated, failed=failed)
    return {"considered": len(rows), "updated": updated, "failed": failed}
