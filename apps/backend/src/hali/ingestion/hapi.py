"""HDX HAPI dekadal rainfall anomalies at admin2.

The adapter that answers "drought in Turkana, floods in Tana River".

Every other feed HALI ingests reports *events*: something happened, here is a
point. East Africa's dominant hazards are *conditions* — a district that has had
41% of its normal rainfall for three dekads is in trouble, and no event feed
will ever say so. HAPI publishes the rainfall anomaly per admin2 unit per dekad,
free, with instant self-service auth, and the geometry comes from the COD-AB
boundaries loaded under the same P-codes.

Verified coverage at admin2 for the dekad ending 2026-07-10:
KEN 73 units, SOM 74, SDN 93, SSD 77, UGA 70, ETH 64. Eritrea has no series.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import asyncpg
import httpx
import structlog

from hali.config import settings

from .models import HazardType, Severity, SourceName
from .normaliser import utc_now
from .spatial_join import countries_for_geometry

logger = structlog.get_logger(__name__)

HAPI_BASE_URL = "https://hapi.humdata.org/api/v2"
RAINFALL_PATH = "climate/rainfall"

ISO2_TO_ISO3 = {
    "KE": "KEN",
    "ET": "ETH",
    "SO": "SOM",
    "UG": "UGA",
    "SD": "SDN",
    "SS": "SSD",
}

# Anomaly is expressed as a percentage of the long-term average for that dekad,
# so 100 is normal. Thresholds follow the convention used by FEWS NET and ICPAC
# for dekadal monitoring: a third below normal is a meaningful deficit, half
# below is severe, and double is a flood signal.
DROUGHT_RED_MAX = 50.0
DROUGHT_ORANGE_MAX = 67.0
FLOOD_ORANGE_MIN = 150.0
FLOOD_RED_MIN = 200.0

# A single dry dekad is weather; several in a row is drought. Requiring a run of
# deficits stops one dry ten-day window raising a red alert across a country.
DROUGHT_CONSECUTIVE_DEKADS = 2

# How far back to pull. Enough to establish a run and to survive HAPI publishing
# a dekad late, without dragging years of history over the wire.
LOOKBACK_DAYS = 90

# Dekadal data, so an alert should outlive one publication cycle but not linger
# once the next dekad contradicts it.
ALERT_VALIDITY = timedelta(days=14)

REQUEST_TIMEOUT_SECONDS = 90
PAGE_LIMIT = 10_000


class HapiError(RuntimeError):
    pass


def app_identifier() -> str:
    """HAPI's app identifier is base64 of "app:email" — self-service, no approval.

    Computed locally rather than round-tripping HAPI's encode endpoint, which
    returns exactly this.
    """
    configured = getattr(settings, "hapi_app_identifier", "") or ""
    if configured:
        return configured
    email = getattr(settings, "hapi_email", "") or "hali@example.org"
    return base64.b64encode(f"hali:{email}".encode()).decode()


def classify(anomaly_pct: float, dry_run_length: int) -> tuple[HazardType, Severity] | None:
    """Map a rainfall anomaly to a hazard and severity, or None if unremarkable."""
    if anomaly_pct >= FLOOD_RED_MIN:
        return HazardType.FLOOD, Severity.RED
    if anomaly_pct >= FLOOD_ORANGE_MIN:
        return HazardType.FLOOD, Severity.ORANGE

    # Drought needs persistence; a single dry dekad is not yet a hazard.
    if dry_run_length < DROUGHT_CONSECUTIVE_DEKADS:
        return None
    if anomaly_pct <= DROUGHT_RED_MAX:
        return HazardType.DROUGHT, Severity.RED
    if anomaly_pct <= DROUGHT_ORANGE_MAX:
        return HazardType.DROUGHT, Severity.ORANGE
    return None


async def fetch_rainfall(client: httpx.AsyncClient, iso3: str) -> list[dict[str, Any]]:
    params = {
        "location_code": iso3,
        "admin_level": 2,
        "limit": PAGE_LIMIT,
        "app_identifier": app_identifier(),
    }
    response = await client.get(f"{HAPI_BASE_URL}/{RAINFALL_PATH}", params=params)
    response.raise_for_status()
    return response.json().get("data", [])


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_observations(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduce raw rows to one current observation per admin2 unit.

    HAPI can return several rows for the same unit and dekad (different
    provider revisions), and the whole history for every unit. Keep the most
    recent dekad per unit, and count how many consecutive dekads before it were
    also in deficit.
    """
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        pcode = row.get("admin2_code")
        anomaly = row.get("rainfall_anomaly_pct")
        end = _parse(row.get("reference_period_end"))
        if not pcode or anomaly is None or end is None:
            continue
        by_unit[pcode].append({**row, "_end": end, "_anomaly": float(anomaly)})

    current: dict[str, dict[str, Any]] = {}
    for pcode, series in by_unit.items():
        # Newest first, de-duplicated by dekad end.
        series.sort(key=lambda r: r["_end"], reverse=True)
        deduped: list[dict[str, Any]] = []
        seen: set[datetime] = set()
        for row in series:
            if row["_end"] in seen:
                continue
            seen.add(row["_end"])
            deduped.append(row)

        head = deduped[0]
        dry_run = 0
        for row in deduped:
            if row["_anomaly"] <= DROUGHT_ORANGE_MAX:
                dry_run += 1
            else:
                break

        current[pcode] = {
            "pcode": pcode,
            "admin1_name": head.get("admin1_name"),
            "admin2_name": head.get("admin2_name"),
            "anomaly_pct": head["_anomaly"],
            "rainfall": head.get("rainfall"),
            "average": head.get("rainfall_long_term_average"),
            "period_start": _parse(head.get("reference_period_start")),
            "period_end": head["_end"],
            "dry_run_dekads": dry_run,
        }
    return current


async def _geometry_for(conn: asyncpg.Connection, pcodes: list[str]) -> dict[str, str]:
    """P-code -> GeoJSON geometry, for units we hold a boundary for."""
    rows = await conn.fetch(
        """
        SELECT pcode, ST_AsGeoJSON(geom) AS geojson
        FROM admin_boundaries
        WHERE level = 2 AND pcode = ANY($1::text[])
        """,
        pcodes,
    )
    return {r["pcode"]: r["geojson"] for r in rows}


async def run_ingest(pool: asyncpg.Pool, only: list[str] | None = None) -> dict[str, Any]:
    """Turn current rainfall anomalies into subnational alerts."""
    targets = only or list(ISO2_TO_ISO3)
    unknown = [t for t in targets if t not in ISO2_TO_ISO3]
    if unknown:
        raise HapiError(f"unsupported country codes: {unknown}")

    created = 0
    skipped_no_geometry = 0
    per_country = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for iso2 in targets:
            iso3 = ISO2_TO_ISO3[iso2]
            try:
                rows = await fetch_rainfall(client, iso3)
            except Exception as exc:
                logger.error("hapi.fetch_failed", iso2=iso2, error=str(exc))
                per_country.append({"iso2": iso2, "alerts": 0, "error": str(exc)})
                continue

            observations = latest_observations(rows)
            flagged = {
                pcode: obs
                for pcode, obs in observations.items()
                if classify(obs["anomaly_pct"], obs["dry_run_dekads"]) is not None
            }

            country_created = 0
            if flagged:
                async with pool.acquire() as conn:
                    geometries = await _geometry_for(conn, list(flagged))
                    for pcode, obs in flagged.items():
                        geojson = geometries.get(pcode)
                        if not geojson:
                            skipped_no_geometry += 1
                            continue
                        hazard, severity = classify(obs["anomaly_pct"], obs["dry_run_dekads"])
                        inserted = await _upsert_alert(conn, iso2, obs, hazard, severity, geojson)
                        country_created += int(inserted)

            created += country_created
            per_country.append(
                {
                    "iso2": iso2,
                    "units": len(observations),
                    "flagged": len(flagged),
                    "alerts": country_created,
                    "error": None,
                }
            )
            logger.info(
                "hapi.country_done",
                iso2=iso2,
                units=len(observations),
                flagged=len(flagged),
                alerts=country_created,
            )

    return {
        "source": SourceName.HAPI.value,
        "countries": len(targets),
        "alerts_upserted": created,
        "skipped_no_geometry": skipped_no_geometry,
        "per_country": per_country,
    }


async def _upsert_alert(
    conn: asyncpg.Connection,
    iso2: str,
    obs: dict[str, Any],
    hazard: HazardType,
    severity: Severity,
    geojson: str,
) -> bool:
    """Insert or refresh the alert for one admin2 unit and dekad.

    The dedup hash includes the dekad, so a new observation for the same unit
    supersedes rather than duplicating, and a unit that recovers simply stops
    producing alerts once the old one expires.
    """
    dedup = f"hapi:{obs['pcode']}:{obs['period_end'].date()}:{hazard.value}"

    # valid_from is when the condition was observed; valid_to runs from *now*,
    # not from the dekad end. HAPI publishes a dekad well after it closes — the
    # latest available on 2026-07-28 ended 2026-07-10 — so dating the expiry off
    # period_end produced 76 alerts that were already expired the moment they
    # were written. A rainfall deficit does not stop mattering because the
    # reporting lag was long.
    valid_from = obs["period_end"]
    valid_to = utc_now() + ALERT_VALIDITY
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
        hazard.value,
        severity.value,
        countries,
        geojson,
        valid_from,
        valid_to,
        dedup,
        SourceName.HAPI.value,
        "https://data.humdata.org/dataset/hdx-hapi-rainfall",
    )
    return True


def describe(obs: dict[str, Any]) -> str:
    """Human-readable summary, used in logs and as AI prompt context."""
    return (
        f"{obs['admin2_name']}, {obs['admin1_name']}: "
        f"{obs['anomaly_pct']:.0f}% of normal rainfall "
        f"for the dekad ending {obs['period_end'].date()}"
    )
