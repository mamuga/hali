"""GDACS REST adapter for current East Africa disaster alerts."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from hali.config import settings

from .base import BaseAdapter
from .models import GeoJSONGeometry, HazardType, NormalisedAlert, RawPayload, Severity, SourceName, ValidatedAlert
from .normaliser import GDACS_HAZARD_MAP, GDACS_SEVERITY_MAP, parse_iso_datetime, to_multipolygon_geojson, utc_now

logger = structlog.get_logger(__name__)
GDACS_SEARCH_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"

# GDACS SEARCH ignores the bbox query param server-side (verified: identical
# results regardless of bbox value), so East Africa scoping must happen here.
# Must match the `countries` table (IGAD member states).
IGAD_ISO2 = {"KE", "ET", "SO", "UG", "DJ", "ER", "SD", "SS"}
IGAD_ISO3 = {"KEN", "ETH", "SOM", "UGA", "DJI", "ERI", "SDN", "SSD"}

ISO3_TO_ISO2 = {
    "KEN": "KE",
    "ETH": "ET",
    "SOM": "SO",
    "UGA": "UG",
    "DJI": "DJ",
    "ERI": "ER",
    "SDN": "SD",
    "SSD": "SS",
}

# SEARCH caps its response at 100 events and sorts globally by date, so a single
# combined query is dominated by whatever hazard is most frequent worldwide —
# earthquakes. Asking for all six types at once returned 100 events from China,
# Japan, Angola and Australia and *zero* from East Africa, while asking for
# drought alone returned 14 events including the live Orange drought over
# Ethiopia, Kenya and Somalia. Querying each type separately gives each its own
# 100-slot budget.
GDACS_EVENT_TYPES_SEPARATE = True

# Events are matched on their whole date range, not their start date. The
# regional drought began in April and is still current, so a same-day window
# (fromdate == todate == today) never sees it.
GDACS_LOOKBACK_DAYS = 60


def _igad_countries(props: dict[str, Any]) -> list[str]:
    """IGAD member states this event touches, as ISO2, or [] if none.

    A regional event names only its primary country in `iso3` and the rest in
    `affectedcountries`. The live Orange drought is filed under ETH but also
    covers Kenya and Somalia; reading `iso3` alone would attribute it to
    Ethiopia only, so Kenyan and Somali subscribers would never be matched.

    The previous implementation took `iso3[:2]`, which happens to give the right
    ISO2 for all eight IGAD states by coincidence and silently mismaps anything
    else (e.g. TCD -> "TC"). Use an explicit table instead.
    """
    codes: set[str] = set()

    primary = str(props.get("iso3") or "").strip().upper()
    if primary:
        codes.add(primary)

    for entry in props.get("affectedcountries") or []:
        if isinstance(entry, dict):
            code = str(entry.get("iso3") or "").strip().upper()
            if code:
                codes.add(code)

    return sorted(ISO3_TO_ISO2[c] for c in codes & IGAD_ISO3)


# How long an ongoing event stays visible after GDACS last updated it. Slow
# hazards are re-scored every few days, so this only has to outlive one cycle.
ONGOING_EVENT_EXTENSION = timedelta(days=7)


def _valid_to(props: dict[str, Any]) -> Any:
    """Expiry for an event, honouring GDACS's `iscurrent` flag.

    For a slow-onset hazard `todate` is the date GDACS last re-scored the event,
    not the date it ends. The regional drought is flagged `iscurrent: true` with
    a `todate` already in the past, so taking it literally files an active
    emergency as expired — invisible on the map and skipped by the broadcast,
    which only sends for alerts still valid.
    """
    parsed = parse_iso_datetime(props.get("todate"))
    is_current = str(props.get("iscurrent", "")).lower() in ("true", "1", "yes")
    if not is_current:
        return parsed

    now = utc_now()
    if parsed is None or parsed <= now:
        return now + ONGOING_EVENT_EXTENSION
    return parsed


class GdacsAdapter(BaseAdapter):
    source = SourceName.GDACS

    async def extract(self) -> list[RawPayload]:
        try:
            features = await self._fetch_with_retry()
            return [
                RawPayload(
                    source=self.source,
                    raw_data=feature,
                    source_event_id=str(feature.get("properties", {}).get("eventid", "unknown")),
                )
                for feature in features
            ]
        except Exception as exc:
            logger.error("gdacs.extract_failed", error=str(exc))
            return []

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(settings.max_retry_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_with_retry(self) -> list[dict[str, Any]]:
        minx, miny, maxx, maxy = settings.east_africa_bbox.split(",")
        now = utc_now()
        todate = now.strftime("%Y-%m-%d")
        fromdate = (now - timedelta(days=GDACS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        event_types = [t.strip() for t in settings.gdacs_event_types.split(",") if t.strip()]

        features: list[dict[str, Any]] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(timeout=settings.ingest_timeout_seconds) as client:
            for event_type in event_types:
                params = {
                    "alertlevel": settings.gdacs_alert_levels,
                    "eventlist": event_type,
                    "fromdate": fromdate,
                    "todate": todate,
                    "bbox": f"{minx},{miny},{maxx},{maxy}",
                }
                try:
                    response = await client.get(GDACS_SEARCH_URL, params=params)
                    response.raise_for_status()
                    batch = response.json().get("features", [])
                except httpx.HTTPError as exc:
                    # One hazard type failing must not lose the others.
                    logger.warning("gdacs.fetch_type_failed", event_type=event_type, error=str(exc))
                    continue

                kept = 0
                for feature in batch:
                    event_id = str(feature.get("properties", {}).get("eventid", ""))
                    if event_id and event_id in seen:
                        continue
                    seen.add(event_id)
                    features.append(feature)
                    kept += 1

                logger.info(
                    "gdacs.fetch_type_ok",
                    event_type=event_type,
                    returned=len(batch),
                    kept=kept,
                    capped=len(batch) >= 100,
                )

        logger.info("gdacs.fetch_ok", count=len(features), types=len(event_types))
        return features

    def validate(self, raw: RawPayload) -> ValidatedAlert | None:
        try:
            props = raw.raw_data.get("properties", {})
            geom = raw.raw_data.get("geometry")
            if not geom or not geom.get("coordinates"):
                logger.warning("gdacs.validate_no_geometry", event_id=raw.source_event_id)
                return None

            event_type = props.get("eventtype", "")
            if event_type not in GDACS_HAZARD_MAP:
                logger.warning("gdacs.validate_unknown_type", event_type=event_type, event_id=raw.source_event_id)

            alert_level = props.get("alertlevel", "Green")
            affected = _igad_countries(props)
            if not affected:
                logger.debug(
                    "gdacs.validate_outside_east_africa",
                    event_id=raw.source_event_id,
                    iso3=props.get("iso3"),
                )
                return None

            source_url = props.get("url") or props.get("link")
            if isinstance(source_url, dict):
                source_url = source_url.get("report") or source_url.get("details") or source_url.get("geometry")
            if source_url is not None:
                source_url = str(source_url)
            return ValidatedAlert(
                source=self.source,
                source_event_id=raw.source_event_id,
                hazard_type=GDACS_HAZARD_MAP.get(event_type, HazardType.OTHER),
                severity=GDACS_SEVERITY_MAP.get(alert_level, Severity.GREEN),
                geometry=GeoJSONGeometry(type=geom["type"], coordinates=geom["coordinates"]),
                valid_from=parse_iso_datetime(props.get("fromdate")),
                valid_to=_valid_to(props),
                affected_countries=affected,
                extra={
                    "country_name": props.get("countryname", ""),
                    "event_name": props.get("eventname", ""),
                    "alert_level": alert_level,
                    "source_url": source_url,
                },
            )
        except Exception as exc:
            logger.error("gdacs.validate_error", event_id=raw.source_event_id, error=str(exc))
            return None

    def transform(self, validated: ValidatedAlert) -> NormalisedAlert:
        geom_dict = {"type": validated.geometry.type, "coordinates": validated.geometry.coordinates}
        multipolygon = to_multipolygon_geojson(geom_dict)
        severity = validated.severity.value
        return NormalisedAlert(
            source=self.source,
            source_event_id=validated.source_event_id,
            hazard_type=validated.hazard_type,
            severity=validated.severity,
            geojson_geometry=multipolygon,
            affected_countries=validated.affected_countries,
            valid_from=validated.valid_from or utc_now(),
            valid_to=validated.valid_to or (utc_now() + timedelta(hours=48)),
            dedup_hash=NormalisedAlert.build_dedup_hash(self.source.value, validated.source_event_id, severity),
            raw_payload_id=validated.raw_payload_id,
            source_url=validated.extra.get("source_url"),
        )
