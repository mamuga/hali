"""FEWS NET IPC food-security classifications.

The only source HALI ingests that hands over finished hazard polygons. FEWS NET
publishes the IPC phase per admin2 x livelihood zone — 640 units for Kenya
alone — so a "Crisis" classification arrives already shaped like the area it
describes, rather than as a grid cell or a point to buffer.

This complements HAPI rather than duplicating it. HAPI reports the *input*
(this district has had 41% of normal rainfall); FEWS NET reports the *outcome*
(households here are in Crisis). A district can be dry without being in crisis,
and in crisis for reasons other than rain — conflict, market collapse,
displacement. Both are stored as `drought`, distinguished by source.

REFRESH CADENCE — read this before treating it as a live feed. FEWS NET
publishes a full current-situation analysis roughly every four months, not
monthly: verified for Kenya in 2026, only February and June carry a `_CS` layer,
while January, March, April and May carry projections only and July is empty.
So this is a slow-moving baseline layer. The scheduler polls weekly and the
adapter searches backwards for the newest real analysis, but the underlying data
changes about three times a year. Alerts carry a 120-day validity to bridge the
gap between releases.

Verified 2026-07-28: KE/ET/SO/UG/SD/SS return data, Djibouti and Eritrea return
an empty archive.
"""
from __future__ import annotations

import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import asyncpg
import httpx
import structlog

from .models import HazardType, Severity, SourceName
from .normaliser import utc_now
from .spatial_join import countries_for_geometry

logger = structlog.get_logger(__name__)

FEWSNET_IPC_URL = "https://fdw.fews.net/api/ipcpackage/"

# Djibouti and Eritrea are excluded: both return a 4-byte empty archive.
FEWSNET_COUNTRIES = ["KE", "ET", "SO", "UG", "SD", "SS"]

# IPC Acute Food Insecurity phases.
#   1 Minimal · 2 Stressed · 3 Crisis · 4 Emergency · 5 Famine
# Phase 3 is the humanitarian action threshold, so it is where an alert starts.
IPC_ALERT_THRESHOLD = 3
IPC_PHASE_SEVERITY = {
    3: Severity.ORANGE,
    4: Severity.RED,
    5: Severity.RED,
}

IPC_PHASE_NAME = {
    1: "Minimal",
    2: "Stressed",
    3: "Crisis",
    4: "Emergency",
    5: "Famine",
}

# The classification is republished every few months; keep an alert alive well
# past one cycle so a district does not silently drop off between releases.
ALERT_VALIDITY = timedelta(days=120)

DOWNLOAD_TIMEOUT_SECONDS = 300
# Anything smaller than this is FEWS NET's empty-archive response.
MIN_ARCHIVE_BYTES = 1024


class FewsNetError(RuntimeError):
    pass


def _collection_date(now: datetime | None = None, months_back: int = 1) -> str:
    """FEWS NET keys packages on the first of a month.

    Requesting the current month returns empty — the classification for a month
    is published during it — so the search starts at the previous month.
    """
    now = now or utc_now()
    month_index = (now.year * 12 + now.month - 1) - months_back
    return f"{month_index // 12:04d}-{month_index % 12 + 1:02d}-01"


# How far back to look for the most recent full analysis.
#
# FEWS NET does not publish a current-situation layer every month. Verified for
# Kenya in 2026: February and June carry `_CS` (plus ML1/ML2), while January,
# March, April and May carry **projections only** and July is empty. So a full
# CS release lands roughly every four months.
#
# Asking only for last month therefore finds nothing for most of the year — from
# August this adapter would have silently refreshed zero alerts until October
# while the existing ones aged out. Walking backwards finds the newest real
# analysis whenever it was published.
MAX_MONTHS_BACK = 8


async def download_package(client: httpx.AsyncClient, iso2: str, collection_date: str) -> bytes:
    response = await client.get(
        FEWSNET_IPC_URL, params={"country_code": iso2, "collection_date": collection_date}
    )
    response.raise_for_status()
    return response.content


def _current_situation_layer(archive: bytes) -> tuple[Any, str] | None:
    """Open the `*_CS` (current situation) shapefile inside the package.

    The archive also holds ML1/ML2 (near- and medium-term projections) and IDP
    variants. Projections would be a genuinely useful separate layer, but
    presenting a forecast as a current alert would misrepresent it.
    """
    import shapefile

    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = bundle.namelist()
        base = next(
            (n[:-4] for n in names if n.endswith("_CS.shp") and "_IDP" not in n),
            None,
        )
        if base is None:
            return None
        reader = shapefile.Reader(
            shp=io.BytesIO(bundle.read(base + ".shp")),
            dbf=io.BytesIO(bundle.read(base + ".dbf")),
            shx=io.BytesIO(bundle.read(base + ".shx")),
        )
        return reader, base


def group_units(reader: Any) -> dict[tuple[str, str, int], list[dict[str, Any]]]:
    """Collapse livelihood-zone units into one entry per district and phase.

    Kenya's June 2026 package holds 640 units, 272 of them at phase 3. Emitting
    one alert per unit would bury the map in slivers of the same district; the
    272 group into 36 districts, which is the level people actually reason at
    ("Garissa is in Crisis"), while the geometry stays the real union of the
    livelihood zones rather than a bounding box.
    """
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in reader.shapeRecords():
        attrs = record.record
        try:
            phase = int(attrs["CS"] or 0)
        except (TypeError, ValueError):
            continue
        if phase < IPC_ALERT_THRESHOLD:
            continue
        admin1 = str(attrs["ADMIN1"] or "").strip()
        admin2 = str(attrs["ADMIN2"] or "").strip() or admin1
        if not admin1 and not admin2:
            continue
        groups[(admin1, admin2, phase)].append(record.shape.__geo_interface__)
    return groups


def merge_geometry(shapes: list[dict[str, Any]]) -> str | None:
    """Union the livelihood-zone polygons of one district into a single GeoJSON."""
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    try:
        geoms = [shape(s).buffer(0) for s in shapes]
        merged = unary_union([g for g in geoms if not g.is_empty])
    except Exception as exc:
        logger.warning("fewsnet.geometry_failed", error=str(exc))
        return None
    if merged.is_empty:
        return None
    return json.dumps(mapping(merged))


async def _upsert(
    conn: asyncpg.Connection,
    *,
    iso2: str,
    admin1: str,
    admin2: str,
    phase: int,
    geojson: str,
    period: str,
) -> None:
    severity = IPC_PHASE_SEVERITY.get(phase, Severity.ORANGE)
    now = utc_now()
    countries = await countries_for_geometry(conn, geojson, always_include=iso2)
    await conn.execute(
        """
        INSERT INTO alerts (hazard_type, severity, affected_countries, geom,
                            valid_from, valid_to, dedup_hash, source, source_url)
        VALUES ($1, $2, $3,
                ST_Multi(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($4), 4326))),
                $5, $6, $7, $8, $9)
        ON CONFLICT (dedup_hash) DO UPDATE
          SET severity = EXCLUDED.severity,
              valid_to = EXCLUDED.valid_to,
              geom = EXCLUDED.geom,
              affected_countries = EXCLUDED.affected_countries
        """,
        HazardType.DROUGHT.value,
        severity.value,
        countries,
        geojson,
        now,
        now + ALERT_VALIDITY,
        f"fewsnet:{iso2}:{admin1}:{admin2}:{period}:ipc{phase}",
        SourceName.FEWSNET.value,
        "https://fews.net/",
    )


async def _newest_analysis(
    client: httpx.AsyncClient, iso2: str, start_date: str | None
) -> tuple[Any, str, str] | None:
    """Walk back month by month until a package with a `_CS` layer is found."""
    candidates = [start_date] if start_date else [
        _collection_date(months_back=n) for n in range(1, MAX_MONTHS_BACK + 1)
    ]

    for date in candidates:
        try:
            archive = await download_package(client, iso2, date)
        except Exception as exc:
            logger.warning("fewsnet.download_failed", iso2=iso2, date=date, error=str(exc))
            continue

        if len(archive) < MIN_ARCHIVE_BYTES:
            logger.debug("fewsnet.month_empty", iso2=iso2, date=date)
            continue

        opened = _current_situation_layer(archive)
        if opened is None:
            # Projection-only release (ML1/ML2 with no CS). Real, but it
            # describes a forecast, not the current situation.
            logger.debug("fewsnet.projection_only", iso2=iso2, date=date)
            continue

        reader, base = opened
        return reader, base, date

    return None


async def ingest_country(
    pool: asyncpg.Pool, client: httpx.AsyncClient, iso2: str, collection_date: str | None
) -> dict[str, Any]:
    found = await _newest_analysis(client, iso2, collection_date)
    if found is None:
        logger.info("fewsnet.no_analysis_found", iso2=iso2, months_searched=MAX_MONTHS_BACK)
        return {"iso2": iso2, "alerts": 0, "error": None, "note": "no current-situation release found"}
    reader, base, resolved_date = found

    groups = group_units(reader)
    period = base.split("_")[1] if "_" in base else resolved_date

    created = 0
    async with pool.acquire() as conn:
        for (admin1, admin2, phase), shapes in groups.items():
            geojson = merge_geometry(shapes)
            if not geojson:
                continue
            await _upsert(
                conn,
                iso2=iso2,
                admin1=admin1,
                admin2=admin2,
                phase=phase,
                geojson=geojson,
                period=period,
            )
            created += 1

    logger.info(
        "fewsnet.country_done",
        iso2=iso2,
        districts=len(groups),
        alerts=created,
        period=period,
        collection_date=resolved_date,
    )
    return {
        "iso2": iso2,
        "districts": len(groups),
        "alerts": created,
        "period": period,
        "collection_date": resolved_date,
        "error": None,
    }


async def run_ingest(
    pool: asyncpg.Pool, only: list[str] | None = None, collection_date: str | None = None
) -> dict[str, Any]:
    targets = only or FEWSNET_COUNTRIES
    unknown = [t for t in targets if t not in FEWSNET_COUNTRIES]
    if unknown:
        raise FewsNetError(f"unsupported country codes: {unknown}")

    date = collection_date
    results = []
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
        for iso2 in targets:
            results.append(await ingest_country(pool, client, iso2, date))

    return {
        "source": SourceName.FEWSNET.value,
        "requested_collection_date": date or "auto (newest CS release)",
        "countries": len(targets),
        "alerts_upserted": sum(r["alerts"] for r in results),
        "per_country": results,
    }
