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
        today = utc_now().strftime("%Y-%m-%d")
        params = {
            "alertlevel": settings.gdacs_alert_levels,
            "eventlist": settings.gdacs_event_types,
            "fromdate": today,
            "todate": today,
            "bbox": f"{minx},{miny},{maxx},{maxy}",
        }
        async with httpx.AsyncClient(timeout=settings.ingest_timeout_seconds) as client:
            response = await client.get(GDACS_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()
        features = data.get("features", [])
        logger.info("gdacs.fetch_ok", count=len(features))
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
            iso3 = props.get("iso3") or ""
            iso2 = iso3[:2].upper()
            if iso2 not in IGAD_ISO2:
                logger.debug("gdacs.validate_outside_east_africa", event_id=raw.source_event_id, iso3=iso3)
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
                valid_to=parse_iso_datetime(props.get("todate")),
                affected_countries=[iso2],
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
