"""NOAA GFS precipitation forecast GeoTIFF adapter."""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from hali.config import settings

from .base import BaseAdapter
from .models import GeoJSONGeometry, HazardType, NormalisedAlert, RawPayload, Severity, SourceName, ValidatedAlert
from .normaliser import bbox_to_multipolygon_geojson, raster_threshold_to_geojson, utc_now

logger = structlog.get_logger(__name__)
GFS_BASE_URL = "https://ftp.cpc.ncep.noaa.gov/GIS/gfs_0.25/prec"
EXTREME_RAINFALL_MM = 75.0


class GfsAdapter(BaseAdapter):
    source = SourceName.GFS

    async def extract(self) -> list[RawPayload]:
        if not settings.enable_gfs:
            return []
        try:
            date_str = utc_now().strftime("%Y%m%d")
            filename = f"gfs_{date_str}00_024.tif"
            url = f"{GFS_BASE_URL}/{filename}"
            tif_path = await self._download_tif(url)
            if not tif_path:
                return []
            return [RawPayload(source=self.source, raw_data={"local_tif_path": tif_path, "date": date_str, "url": url}, source_event_id=f"gfs-{date_str}")]
        except Exception as exc:
            logger.error("gfs.extract_failed", error=str(exc))
            return []

    @retry(retry=retry_if_exception_type(httpx.HTTPError), stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=False)
    async def _download_tif(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url)
                response.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
            tmp.write(response.content)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception as exc:
            logger.warning("gfs.download_failed", url=url, error=str(exc))
            return None

    def validate(self, raw: RawPayload) -> ValidatedAlert | None:
        tif_path = raw.raw_data.get("local_tif_path")
        if not tif_path or not os.path.exists(tif_path):
            return None
        minx, miny, maxx, maxy = 21.0, -12.0, 52.0, 24.0
        return ValidatedAlert(
            source=self.source,
            source_event_id=raw.source_event_id,
            hazard_type=HazardType.FLOOD,
            severity=Severity.GREEN,
            geometry=GeoJSONGeometry(type="Polygon", coordinates=[[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]),
            extra=raw.raw_data,
        )

    def transform(self, validated: ValidatedAlert) -> NormalisedAlert:
        import rasterio

        tif_path = validated.extra["local_tif_path"]
        date_str = validated.extra["date"]
        try:
            with rasterio.open(tif_path) as src:
                data = src.read(1)
                geom = raster_threshold_to_geojson(data, src.transform, EXTREME_RAINFALL_MM, above=True)
                if geom:
                    severity = Severity.RED if float(data.max()) > 150 else Severity.ORANGE
                    hazard = HazardType.FLOOD
                else:
                    geom = bbox_to_multipolygon_geojson(21, -12, 52, 24)
                    severity = Severity.GREEN
                    hazard = HazardType.OTHER
        finally:
            if tif_path and os.path.exists(tif_path):
                os.unlink(tif_path)

        now = utc_now()
        return NormalisedAlert(
            source=self.source,
            source_event_id=validated.source_event_id,
            hazard_type=hazard,
            severity=severity,
            geojson_geometry=geom,
            affected_countries=[],
            valid_from=now,
            valid_to=now + timedelta(hours=24),
            dedup_hash=NormalisedAlert.build_dedup_hash(self.source.value, date_str, severity.value),
            raw_payload_id=validated.raw_payload_id,
            source_url=validated.extra.get("url"),
        )
