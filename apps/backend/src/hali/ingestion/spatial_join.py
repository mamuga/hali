"""Resolve which countries an alert geometry actually touches.

`IngestionLoader` already does this for the adapters that go through it (GDACS,
GFS, CHIRPS, GLOFAS, ICPAC). The subnational adapters — FEWS NET and HAPI —
bypass the loader because they write finished polygons directly, and both were
recording `affected_countries = [iso2]`, where `iso2` is simply the country
whose data package was downloaded.

That is right for most districts and wrong for every border one. Measured on the
live feed: 85 of 445 FEWS NET alerts and 13 of 76 HAPI alerts have geometry
crossing into a neighbouring country they did not list — 19% of the subnational
feed. The consequences are not cosmetic. Subscriber targeting matches on
`preferred_iso2 = ANY(affected_countries)`, so someone in Dollo Ado who selected
Ethiopia would not be alerted to a Crisis classification whose polygon covers
them but is filed under Somalia; and country rollups attribute the whole of a
shared hazard to one side of the border.

The download country is always kept even when the geometry misses it, because
the publisher's own attribution is authoritative for provenance — the union is
the honest answer, not a replacement.
"""
from __future__ import annotations

import asyncpg
import structlog

logger = structlog.get_logger(__name__)


async def countries_for_geometry(
    conn: asyncpg.Connection, geojson: str, *, always_include: str | None = None
) -> list[str]:
    """ISO2 codes whose national boundary intersects this geometry.

    Falls back to `always_include` alone if the lookup fails, so a transient
    error downgrades the attribution rather than dropping the alert.
    """
    codes: set[str] = {always_include} if always_include else set()
    try:
        rows = await conn.fetch(
            """
            SELECT iso2 FROM countries
            WHERE ST_Intersects(
                geom, ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($1), 4326))
            )
            """,
            geojson,
        )
        codes.update(row["iso2"] for row in rows)
    except Exception as exc:
        logger.warning("spatial_join.country_lookup_failed", error=str(exc))
    return sorted(codes)
