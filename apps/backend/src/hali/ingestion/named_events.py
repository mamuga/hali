"""Named-event feeds: IFRC GO appeals and WHO Disease Outbreak News.

These cover the hazards HALI's physical models cannot see. CHIRPS and GFS
describe rainfall; nothing in the pipeline knows that Somalia opened a locust
appeal yesterday, that Kenya has an active cholera response, or that Bundibugyo
Ebola is circulating in Uganda. Those are reported by humanitarian
organisations, not measured by satellites.

Both APIs are keyless. Verified 2026-07-28: 14 IGAD appeals since October 2025,
and 3,192 WHO outbreak notices.

Geometry is the country polygon — these feeds are country-scoped, and inventing
a finer footprint would imply precision the source does not have. The subnational
signal comes from HAPI and FEWS NET instead.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

import asyncpg
import httpx
import structlog

from .models import HazardType, Severity, SourceName
from .normaliser import utc_now

logger = structlog.get_logger(__name__)

IFRC_APPEAL_URL = "https://goadmin.ifrc.org/api/v2/appeal/"
WHO_DON_URL = "https://www.who.int/api/news/diseaseoutbreaknews"

IGAD_ISO2 = {"KE", "ET", "SO", "UG", "DJ", "ER", "SD", "SS"}

IGAD_COUNTRY_NAMES = {
    "Kenya": "KE",
    "Ethiopia": "ET",
    "Somalia": "SO",
    "Uganda": "UG",
    "Djibouti": "DJ",
    "Eritrea": "ER",
    "Sudan": "SD",
    "South Sudan": "SS",
}

# IFRC disaster-type ids, from the live feed. `Other` covers the locust appeal
# ("Somalia Insect Infestation"), so the title is inspected for those.
IFRC_DTYPE_TO_HAZARD = {
    1: HazardType.EPIDEMIC,
    12: HazardType.FLOOD,
    24: HazardType.LANDSLIDE,
    20: HazardType.DROUGHT,
    4: HazardType.CYCLONE,
    15: HazardType.WILDFIRE,
    62: HazardType.HEATWAVE,
}

TITLE_HAZARD_HINTS: list[tuple[re.Pattern[str], HazardType]] = [
    (re.compile(r"locust|insect infestation|armyworm", re.I), HazardType.LOCUST),
    (re.compile(r"cholera|ebola|marburg|dengue|measles|outbreak|virus", re.I), HazardType.EPIDEMIC),
    (re.compile(r"flood", re.I), HazardType.FLOOD),
    (re.compile(r"drought", re.I), HazardType.DROUGHT),
    (re.compile(r"landslide|mudslide", re.I), HazardType.LANDSLIDE),
    (re.compile(r"wildfire|bushfire", re.I), HazardType.WILDFIRE),
    (re.compile(r"heat ?wave", re.I), HazardType.HEATWAVE),
    (re.compile(r"cyclone|storm", re.I), HazardType.CYCLONE),
]

# An appeal is a standing response, not a moment. Keep it visible for a while,
# but not indefinitely — a stale appeal on the map is worse than none.
APPEAL_VALIDITY_DAYS = 60
OUTBREAK_VALIDITY_DAYS = 45
APPEAL_LOOKBACK_DAYS = 300

REQUEST_TIMEOUT_SECONDS = 90


def hazard_from_title(title: str, fallback: HazardType = HazardType.OTHER) -> HazardType:
    for pattern, hazard in TITLE_HAZARD_HINTS:
        if pattern.search(title):
            return hazard
    return fallback


def countries_in_text(text: str) -> list[str]:
    """IGAD countries named in a free-text title.

    Ordered longest-first so "South Sudan" is not swallowed by "Sudan".
    """
    found: set[str] = set()
    for name in sorted(IGAD_COUNTRY_NAMES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", text):
            found.add(IGAD_COUNTRY_NAMES[name])
    # "South Sudan" also matches "Sudan"; drop the parent when the child matched.
    if "SS" in found and "South Sudan" in text and not re.search(r"\bSudan\b(?!ese)(?<!South Sudan)", text):
        found.discard("SD")
    return sorted(found)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _country_geometry(conn: asyncpg.Connection, iso2_list: list[str]) -> str | None:
    """Union of the named countries, as GeoJSON."""
    return await conn.fetchval(
        "SELECT ST_AsGeoJSON(ST_Union(geom)) FROM countries WHERE iso2 = ANY($1::text[])",
        iso2_list,
    )


async def _upsert(
    conn: asyncpg.Connection,
    *,
    hazard: HazardType,
    severity: Severity,
    countries: list[str],
    geojson: str,
    valid_from: datetime,
    valid_to: datetime,
    dedup: str,
    source: SourceName,
    url: str | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO alerts (hazard_type, severity, affected_countries, geom,
                            valid_from, valid_to, dedup_hash, source, source_url)
        VALUES ($1, $2, $3,
                ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))),
                $5, $6, $7, $8, $9)
        ON CONFLICT (dedup_hash) DO UPDATE
          SET severity = EXCLUDED.severity, valid_to = EXCLUDED.valid_to
        """,
        hazard.value,
        severity.value,
        countries,
        geojson,
        valid_from,
        valid_to,
        dedup,
        source.value,
        url,
    )


async def ingest_ifrc(pool: asyncpg.Pool) -> dict[str, Any]:
    """IFRC GO emergency appeals for IGAD member states.

    Note: the `/api/v2/event/` endpoint silently ignores its `countries__iso3`
    filter and returns the global list, so appeals are fetched and filtered here.
    """
    since = (utc_now() - timedelta(days=APPEAL_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    params = {"limit": 400, "start_date__gt": since}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(IFRC_APPEAL_URL, params=params)
        response.raise_for_status()
        results = response.json().get("results", [])

    upserted = 0
    skipped = 0
    async with pool.acquire() as conn:
        for appeal in results:
            country = appeal.get("country") or {}
            iso2 = country.get("iso")
            if iso2 not in IGAD_ISO2:
                continue

            name = str(appeal.get("name") or "")
            dtype_id = (appeal.get("dtype") or {}).get("id")
            hazard = hazard_from_title(name, IFRC_DTYPE_TO_HAZARD.get(dtype_id, HazardType.OTHER))

            start = _parse_date(appeal.get("start_date")) or utc_now()
            declared_end = _parse_date(appeal.get("end_date"))
            if declared_end is not None and declared_end <= utc_now():
                skipped += 1
                continue

            # IFRC appeal end dates run years out — several in the live feed end
            # in 2028. Honouring that literally parks an alert on the map for two
            # years with nothing to refresh it. Cap the horizon so the alert has
            # to be re-confirmed by the next ingest run to stay visible.
            horizon = utc_now() + timedelta(days=APPEAL_VALIDITY_DAYS)
            valid_to = min(declared_end, horizon) if declared_end else horizon

            geojson = await _country_geometry(conn, [iso2])
            if not geojson:
                skipped += 1
                continue

            await _upsert(
                conn,
                hazard=hazard,
                # An IFRC appeal means a national society has formally asked for
                # help — serious, but it is a response status rather than a
                # forecast, so it does not warrant red on its own.
                severity=Severity.ORANGE,
                countries=[iso2],
                geojson=geojson,
                valid_from=start,
                valid_to=valid_to,
                dedup=f"ifrc:{appeal.get('aid') or appeal.get('code') or name}",
                source=SourceName.IFRC,
                url="https://go.ifrc.org/emergencies",
            )
            upserted += 1

    logger.info("ifrc.ingest_done", upserted=upserted, skipped=skipped, scanned=len(results))
    return {"source": "ifrc", "scanned": len(results), "upserted": upserted, "skipped": skipped}


async def ingest_who(pool: asyncpg.Pool, top: int = 60) -> dict[str, Any]:
    """WHO Disease Outbreak News entries naming an IGAD country.

    WHO publishes no structured country field, so the country is read from the
    title. That is why only `epidemic` alerts come from here — the titles are
    reliably of the form "<disease> - <country>".
    """
    params = {
        "sf_provider": "dynamicProvider372",
        "sf_culture": "en",
        "$orderby": "PublicationDateAndTime desc",
        "$top": top,
        "$count": "true",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(WHO_DON_URL, params=params)
        response.raise_for_status()
        items = response.json().get("value", [])

    upserted = 0
    async with pool.acquire() as conn:
        for item in items:
            title = str(item.get("Title") or "")
            countries = countries_in_text(title)
            if not countries:
                continue

            published = _parse_date(item.get("PublicationDateAndTime")) or utc_now()
            valid_to = published + timedelta(days=OUTBREAK_VALIDITY_DAYS)
            if valid_to <= utc_now():
                continue

            geojson = await _country_geometry(conn, countries)
            if not geojson:
                continue

            await _upsert(
                conn,
                hazard=hazard_from_title(title, HazardType.EPIDEMIC),
                severity=Severity.ORANGE,
                countries=countries,
                geojson=geojson,
                valid_from=published,
                valid_to=valid_to,
                dedup=f"who:{item.get('Id') or item.get('UrlName') or title}",
                source=SourceName.WHO,
                url="https://www.who.int/emergencies/disease-outbreak-news",
            )
            upserted += 1

    logger.info("who.ingest_done", upserted=upserted, scanned=len(items))
    return {"source": "who", "scanned": len(items), "upserted": upserted}
