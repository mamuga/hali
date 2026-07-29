"""WorldPop population grid ingestion.

Replaces the per-alert call to WorldPop's REST API in services/population.py.
That approach cost a network round trip per alert, could not answer a
user-drawn polygon at all, and returned nothing when the service was slow — so
exposure figures went missing exactly when the system was busiest.

This loads the 1 km UN-adjusted rasters once, aggregates them to ~5 km cells,
and stores points in PostGIS. Every exposure figure afterwards is a local
`SUM(pop)` over a GiST index: fast, offline-capable, and identical whether the
geometry is an alert zone or a shape someone drew on a phone.

Static data, so this is a one-shot/quarterly job rather than part of the
scheduled pipeline. Disabled by default; trigger with
`POST /api/admin/trigger-ingest?source=worldpop`.

The URL pattern below was verified with HEAD requests against all eight
countries (27 MB total) rather than assumed.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import structlog

from hali.config import settings

logger = structlog.get_logger(__name__)

WORLDPOP_URL_TEMPLATE = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/"
    "{year}/{iso3}/{iso3_lower}_ppp_{year}_1km_Aggregated_UNadj.tif"
)

ISO2_TO_ISO3 = {
    "KE": "KEN",
    "ET": "ETH",
    "SO": "SOM",
    "UG": "UGA",
    "DJ": "DJI",
    "ER": "ERI",
    "SD": "SDN",
    "SS": "SSD",
}

POPULATION_YEAR = 2020
SOURCE_NAME = "worldpop_1km_unadj"

# Aggregate 5x5 native pixels into one ~5 km cell. At 1 km the eight countries
# are several million populated pixels, which is more rows than this buys us in
# accuracy: alert zones are tens of kilometres across, so 5 km cells change the
# exposure total by far less than the underlying model's own error.
BLOCK = 5

# Cells below this are dropped. WorldPop stores smoothed floats, so genuinely
# empty desert carries values like 0.004 that would otherwise add tens of
# thousands of rows of noise across the Sahara and the Chalbi.
MIN_CELL_POPULATION = 1

DOWNLOAD_TIMEOUT_SECONDS = 300
COPY_BATCH = 10_000


class WorldPopIngestError(RuntimeError):
    pass


async def download_raster(iso3: str, destination: Path, year: int = POPULATION_YEAR) -> Path:
    """Stream one country's raster to disk."""
    url = WORLDPOP_URL_TEMPLATE.format(year=year, iso3=iso3, iso3_lower=iso3.lower())
    logger.info("worldpop.download_start", iso3=iso3, url=url)

    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise WorldPopIngestError(f"{iso3}: HTTP {response.status_code} for {url}")
            with destination.open("wb") as handle:
                async for chunk in response.aiter_bytes(chunk_size=1 << 20):
                    handle.write(chunk)

    size_mb = destination.stat().st_size / 1e6
    logger.info("worldpop.download_done", iso3=iso3, size_mb=round(size_mb, 1))
    return destination


def aggregate_raster(path: Path, iso2: str) -> list[tuple[str, float, float, int]]:
    """Reduce a 1 km raster to ~5 km cells as (iso2, lng, lat, pop) tuples.

    CPU-bound; call through asyncio.to_thread.
    """
    import numpy as np
    import rasterio

    with rasterio.open(path) as src:
        data = src.read(1).astype("float64")
        nodata = src.nodata
        transform = src.transform

    # WorldPop marks no-data with a large negative sentinel. Clipping negatives
    # to zero without this leaves the sentinel contributing to block sums.
    if nodata is not None:
        data[data == nodata] = 0.0
    data[~np.isfinite(data)] = 0.0
    data[data < 0] = 0.0

    rows, cols = data.shape
    trimmed_rows = (rows // BLOCK) * BLOCK
    trimmed_cols = (cols // BLOCK) * BLOCK
    if trimmed_rows == 0 or trimmed_cols == 0:
        return []

    blocks = data[:trimmed_rows, :trimmed_cols].reshape(
        trimmed_rows // BLOCK, BLOCK, trimmed_cols // BLOCK, BLOCK
    ).sum(axis=(1, 3))

    populated = np.argwhere(blocks >= MIN_CELL_POPULATION)
    records: list[tuple[str, float, float, int]] = []
    for block_row, block_col in populated:
        # Centre of the block, in pixel coordinates, then through the affine
        # transform to lng/lat.
        col = block_col * BLOCK + BLOCK / 2.0
        row = block_row * BLOCK + BLOCK / 2.0
        lng, lat = transform * (col, row)
        records.append((iso2, float(lng), float(lat), int(round(blocks[block_row, block_col]))))

    logger.info(
        "worldpop.aggregated",
        iso2=iso2,
        cells=len(records),
        total_population=int(blocks.sum()),
    )
    return records


async def store_country(
    pool: asyncpg.Pool,
    iso2: str,
    records: list[tuple[str, float, float, int]],
    year: int = POPULATION_YEAR,
) -> int:
    """Replace one country-year slice, transactionally.

    Delete-then-insert inside one transaction so a re-run cannot double the
    population, and a failure mid-load cannot leave the country half-populated
    — a partial grid would silently understate every exposure figure that
    touches it.
    """
    if not records:
        return 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM pop_grid WHERE iso2 = $1 AND year = $2 AND source = $3",
                iso2,
                year,
                SOURCE_NAME,
            )
            for start in range(0, len(records), COPY_BATCH):
                batch = records[start : start + COPY_BATCH]
                await conn.executemany(
                    """
                    INSERT INTO pop_grid (iso2, geom, pop, year, source)
                    VALUES ($1, ST_SetSRID(ST_MakePoint($2, $3), 4326), $4, $5, $6)
                    """,
                    [(r[0], r[1], r[2], r[3], year, SOURCE_NAME) for r in batch],
                )

    logger.info("worldpop.stored", iso2=iso2, cells=len(records))
    return len(records)


async def ingest_country(pool: asyncpg.Pool, iso2: str, workdir: Path) -> dict[str, Any]:
    iso3 = ISO2_TO_ISO3[iso2]
    raster = workdir / f"{iso3.lower()}_ppp.tif"
    try:
        await download_raster(iso3, raster)
        records = await asyncio.to_thread(aggregate_raster, raster, iso2)
        stored = await store_country(pool, iso2, records)
        total = sum(r[3] for r in records)
        return {"iso2": iso2, "cells": stored, "population": total, "error": None}
    except Exception as exc:
        logger.error("worldpop.country_failed", iso2=iso2, error=str(exc))
        return {"iso2": iso2, "cells": 0, "population": 0, "error": str(exc)}
    finally:
        raster.unlink(missing_ok=True)


async def run_ingest(pool: asyncpg.Pool, only: list[str] | None = None) -> dict[str, Any]:
    """Load every IGAD country's population grid.

    Countries are processed one at a time: each raster is tens of megabytes
    decompressed, and holding eight in memory at once is the kind of thing that
    gets a container OOM-killed on a small Railway instance.
    """
    targets = only or list(ISO2_TO_ISO3)
    unknown = [t for t in targets if t not in ISO2_TO_ISO3]
    if unknown:
        raise WorldPopIngestError(f"unknown country codes: {unknown}")

    results = []
    with tempfile.TemporaryDirectory(prefix="hali-worldpop-") as tmp:
        workdir = Path(tmp)
        for iso2 in targets:
            results.append(await ingest_country(pool, iso2, workdir))

    succeeded = [r for r in results if r["error"] is None]
    return {
        "countries": len(targets),
        "succeeded": len(succeeded),
        "failed": [r["iso2"] for r in results if r["error"]],
        "total_cells": sum(r["cells"] for r in results),
        "total_population": sum(r["population"] for r in results),
        "per_country": results,
    }


def is_enabled() -> bool:
    return bool(getattr(settings, "enable_worldpop", False))
