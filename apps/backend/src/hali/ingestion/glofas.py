"""GloFAS CDS river discharge forecast adapter."""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import structlog

from hali.config import settings

from .base import BaseAdapter
from .models import GeoJSONGeometry, HazardType, NormalisedAlert, RawPayload, Severity, SourceName, ValidatedAlert
from .normaliser import bbox_to_multipolygon_geojson, utc_now

logger = structlog.get_logger(__name__)


class GloFASAdapter(BaseAdapter):
    source = SourceName.GLOFAS

    def __init__(self, pool):
        super().__init__(pool)
        if not settings.glofas_cds_api_key:
            raise ValueError(
                "ENABLE_GLOFAS=true but GLOFAS_CDS_API_KEY is not set. "
                "Register at https://cds.climate.copernicus.eu and set the key."
            )

    async def extract(self) -> list[RawPayload]:
        if not settings.enable_glofas:
            return []
        try:
            import asyncio

            grib_path = await asyncio.get_running_loop().run_in_executor(None, self._download_glofas)
            if not grib_path:
                return []
            today = utc_now().date()
            return [RawPayload(source=self.source, raw_data={"local_grib_path": grib_path, "date": str(today)}, source_event_id=f"glofas-{today}")]
        except Exception as exc:
            logger.error("glofas.extract_failed", error=str(exc))
            return []

    def _download_glofas(self) -> str | None:
        try:
            import cdsapi

            client = cdsapi.Client(url=settings.glofas_cds_url, key=settings.glofas_cds_api_key, quiet=True)
            tmp = tempfile.NamedTemporaryFile(suffix=".grib2", delete=False)
            tmp.close()
            client.retrieve(
                "cems-glofas-forecast",
                {
                    "system_version": "version_4_0",
                    "hydrological_model": "lisflood",
                    "product_type": "control_forecast",
                    "variable": "river_discharge_in_the_last_24_hours",
                    "leadtime_hour": ["24", "48"],
                    "area": [24, 21, -12, 52],
                    "format": "grib2",
                },
                tmp.name,
            )
            return tmp.name
        except Exception as exc:
            logger.warning("glofas.cds_download_failed", error=str(exc))
            return None

    def validate(self, raw: RawPayload) -> ValidatedAlert | None:
        grib_path = raw.raw_data.get("local_grib_path")
        if not grib_path or not os.path.exists(grib_path):
            return None
        return ValidatedAlert(
            source=self.source,
            source_event_id=raw.source_event_id,
            hazard_type=HazardType.FLOOD,
            severity=Severity.ORANGE,
            geometry=GeoJSONGeometry(type="Polygon", coordinates=[[[21, -12], [52, -12], [52, 24], [21, 24], [21, -12]]]),
            extra=raw.raw_data,
        )

    def transform(self, validated: ValidatedAlert) -> NormalisedAlert:
        grib_path = validated.extra.get("local_grib_path")
        date_str = validated.extra.get("date", "unknown")
        try:
            try:
                import cfgrib

                ds = cfgrib.open_dataset(grib_path)
                var_name = "dis24" if "dis24" in ds else next(iter(ds.data_vars))
                max_discharge = float(ds[var_name].max().values)
                severity = Severity.RED if max_discharge > 5000 else Severity.ORANGE if max_discharge > 2000 else Severity.GREEN
                ds.close()
            except Exception:
                severity = Severity.ORANGE
            geom = bbox_to_multipolygon_geojson(21, -12, 52, 24)
        finally:
            if grib_path and os.path.exists(grib_path):
                os.unlink(grib_path)

        now = utc_now()
        return NormalisedAlert(
            source=self.source,
            source_event_id=validated.source_event_id,
            hazard_type=HazardType.FLOOD,
            severity=severity,
            geojson_geometry=geom,
            affected_countries=[],
            valid_from=now,
            valid_to=now + timedelta(hours=72),
            dedup_hash=NormalisedAlert.build_dedup_hash(self.source.value, date_str, severity.value),
            raw_payload_id=validated.raw_payload_id,
        )


GlofasAdapter = GloFASAdapter
