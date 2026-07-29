"""Load OCHA COD administrative boundaries from HDX.

These are the geometry HALI attaches to every subnational indicator. HAPI
publishes rainfall, food security and conflict keyed on admin2 P-codes but ships
no geometry; COD-AB carries the matching polygons. Verified: all 73 Kenyan
admin2 codes HAPI returns match a COD-AB polygon exactly.

One-shot load, like the population grid — administrative boundaries change on
the order of years. Trigger with `POST /api/admin/ingest-boundaries`.
"""
from __future__ import annotations

import asyncio
import io
import json
import zipfile
from typing import Any

import asyncpg
import httpx
import structlog

logger = structlog.get_logger(__name__)

HDX_PACKAGE_URL = "https://data.humdata.org/api/3/action/package_show?id=cod-ab-{iso3}"

# Djibouti and Eritrea are absent on purpose: HDX publishes no COD-AB GeoJSON
# for Djibouti (SHP/GDB only, GADM-derived), and HAPI has no rainfall series for
# Eritrea at all. Djibouti also has a single admin2 unit with data, so the loss
# is one polygon.
BOUNDARY_COUNTRIES = {
    "KE": "KEN",
    "ET": "ETH",
    "SO": "SOM",
    "UG": "UGA",
    "SD": "SDN",
    "SS": "SSD",
}

ADMIN_LEVEL = 2
DOWNLOAD_TIMEOUT_SECONDS = 300
INSERT_BATCH = 500


class BoundaryIngestError(RuntimeError):
    pass


async def _geojson_resource_url(client: httpx.AsyncClient, iso3: str) -> str:
    response = await client.get(HDX_PACKAGE_URL.format(iso3=iso3.lower()))
    response.raise_for_status()
    resources = response.json()["result"]["resources"]
    for resource in resources:
        if resource.get("format") == "GeoJSON":
            return resource["url"]
    raise BoundaryIngestError(f"{iso3}: no GeoJSON resource in cod-ab-{iso3.lower()}")


def _extract_admin_layer(archive: bytes, level: int) -> list[dict[str, Any]]:
    """Pull the admin{level} FeatureCollection out of the COD-AB zip."""
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        candidates = [n for n in bundle.namelist() if f"admin{level}" in n.lower() and n.endswith(".geojson")]
        if not candidates:
            raise BoundaryIngestError(f"no admin{level} layer in archive: {bundle.namelist()}")
        return json.loads(bundle.read(candidates[0]))["features"]


def _rows(features: list[dict[str, Any]], iso2: str, level: int) -> list[tuple]:
    rows = []
    for feature in features:
        props = feature.get("properties") or {}
        pcode = props.get(f"adm{level}_pcode")
        name = props.get(f"adm{level}_name")
        if not pcode or not name:
            continue
        rows.append(
            (
                pcode,
                iso2,
                level,
                name,
                props.get(f"adm{level - 1}_name"),
                props.get(f"adm{level - 1}_pcode"),
                json.dumps(feature["geometry"]),
            )
        )
    return rows


async def _store(pool: asyncpg.Pool, iso2: str, level: int, rows: list[tuple]) -> int:
    if not rows:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM admin_boundaries WHERE iso2 = $1 AND level = $2", iso2, level
            )
            for start in range(0, len(rows), INSERT_BATCH):
                await conn.executemany(
                    """
                    INSERT INTO admin_boundaries
                        (pcode, iso2, level, name, parent_name, parent_pcode, geom)
                    VALUES ($1, $2, $3, $4, $5, $6,
                            ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($7), 4326))))
                    ON CONFLICT (pcode) DO UPDATE
                      SET name = EXCLUDED.name,
                          parent_name = EXCLUDED.parent_name,
                          parent_pcode = EXCLUDED.parent_pcode,
                          geom = EXCLUDED.geom,
                          updated_at = NOW()
                    """,
                    rows[start : start + INSERT_BATCH],
                )
    return len(rows)


DOWNLOAD_ATTEMPTS = 3


async def _download_with_retry(client: httpx.AsyncClient, url: str, iso2: str) -> bytes:
    last: Exception | None = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
        except Exception as exc:
            last = exc
            logger.warning(
                "boundaries.download_retry", iso2=iso2, attempt=attempt, error=str(exc)
            )
            await asyncio.sleep(attempt * 3)
    raise BoundaryIngestError(f"{iso2}: download failed after {DOWNLOAD_ATTEMPTS} attempts: {last}")


async def ingest_boundaries(pool: asyncpg.Pool, level: int = ADMIN_LEVEL) -> dict[str, Any]:
    results = []
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
        for iso2, iso3 in BOUNDARY_COUNTRIES.items():
            try:
                url = await _geojson_resource_url(client, iso3)
                # Uganda's archive is 38 MB and HDX drops the connection under
                # load often enough that a single attempt loses a whole country.
                content = await _download_with_retry(client, url, iso2)
                features = _extract_admin_layer(content, level)
                stored = await _store(pool, iso2, level, _rows(features, iso2, level))
                logger.info("boundaries.loaded", iso2=iso2, units=stored)
                results.append({"iso2": iso2, "units": stored, "error": None})
            except Exception as exc:
                logger.error("boundaries.failed", iso2=iso2, error=str(exc))
                results.append({"iso2": iso2, "units": 0, "error": str(exc)})

    return {
        "level": level,
        "countries": len(BOUNDARY_COUNTRIES),
        "succeeded": sum(1 for r in results if r["error"] is None),
        "total_units": sum(r["units"] for r in results),
        "per_country": results,
    }
