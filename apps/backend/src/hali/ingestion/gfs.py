"""NOAA GFS precipitation forecast GeoTIFF adapter.

NOAA publishes a whole-day zip bundle (shapefile + GeoTIFF per forecast lead
time) rather than a single file per lead time - verified against the live
server, since the previously coded single-file URL scheme
(GIS/gfs_0.25/prec/gfs_{date}00_024.tif) no longer exists.
"""
from __future__ import annotations

import os
import tempfile
import zipfile
from datetime import timedelta

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from hali.config import settings

from .base import BaseAdapter
from .models import GeoJSONGeometry, HazardType, NormalisedAlert, RawPayload, Severity, SourceName, ValidatedAlert
from .normaliser import bbox_to_multipolygon_geojson, raster_threshold_to_geojson, utc_now

logger = structlog.get_logger(__name__)
GFS_BASE_URL = "https://ftp.cpc.ncep.noaa.gov/GIS/gfs_0.25"
LEAD_TIME_HOURS = 24  # next-24h precipitation forecast, matches original single-file intent
EXTREME_RAINFALL_MM = 75.0
EAST_AFRICA_BBOX = (21.0, -12.0, 52.0, 24.0)  # minx, miny, maxx, maxy
MAX_LOOKBACK_DAYS = 3  # publish time varies; search backward if today's isn't up yet


class GfsAdapter(BaseAdapter):
    source = SourceName.GFS

    async def extract(self) -> list[RawPayload]:
        if not settings.enable_gfs:
            return []
        try:
            for days_back in range(MAX_LOOKBACK_DAYS):
                date_str = (utc_now().date() - timedelta(days=days_back)).strftime("%Y%m%d")
                url = f"{GFS_BASE_URL}/gfs_precip_shp_tif_{date_str}.zip"
                zip_path = await self._download_zip(url)
                if zip_path:
                    return [
                        RawPayload(
                            source=self.source,
                            raw_data={"local_zip_path": zip_path, "date": date_str, "url": url},
                            source_event_id=f"gfs-{date_str}",
                        )
                    ]
            logger.warning("gfs.no_recent_file_found", lookback_days=MAX_LOOKBACK_DAYS)
            return []
        except Exception as exc:
            logger.error("gfs.extract_failed", error=str(exc))
            return []

    @retry(retry=retry_if_exception_type(httpx.HTTPError), stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=False)
    async def _download_zip(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.get(url)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.write(response.content)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception as exc:
            logger.warning("gfs.download_failed", url=url, error=str(exc))
            return None

    def validate(self, raw: RawPayload) -> ValidatedAlert | None:
        zip_path = raw.raw_data.get("local_zip_path")
        if not zip_path or not os.path.exists(zip_path):
            return None
        minx, miny, maxx, maxy = EAST_AFRICA_BBOX
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
        from rasterio.windows import from_bounds

        zip_path = validated.extra["local_zip_path"]
        date_str = validated.extra["date"]
        tif_path: str | None = None
        try:
            member = f"gfs_precip_shp_tif_{date_str}/gfs_precip_gis_{LEAD_TIME_HOURS}_{date_str}.tif"
            with zipfile.ZipFile(zip_path) as zf:
                tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
                with zf.open(member) as src_member:
                    tmp.write(src_member.read())
                tmp.flush()
                tmp.close()
                tif_path = tmp.name

            with rasterio.open(tif_path) as src:
                # Global 0.25deg raster - crop to East Africa before thresholding
                # so a storm elsewhere in the world can't produce a "flood alert"
                # geometry outside our region.
                window = from_bounds(*EAST_AFRICA_BBOX, transform=src.transform)
                data = src.read(1, window=window)
                window_transform = src.window_transform(window)
                geom = raster_threshold_to_geojson(data, window_transform, EXTREME_RAINFALL_MM, above=True)
                if geom:
                    severity = Severity.RED if float(data.max()) > 150 else Severity.ORANGE
                    hazard = HazardType.FLOOD
                else:
                    geom = bbox_to_multipolygon_geojson(*EAST_AFRICA_BBOX)
                    severity = Severity.GREEN
                    hazard = HazardType.OTHER
        finally:
            if tif_path and os.path.exists(tif_path):
                os.unlink(tif_path)
            if zip_path and os.path.exists(zip_path):
                os.unlink(zip_path)

        now = utc_now()
        return NormalisedAlert(
            source=self.source,
            source_event_id=validated.source_event_id,
            hazard_type=hazard,
            severity=severity,
            geojson_geometry=geom,
            affected_countries=[],
            valid_from=now,
            valid_to=now + timedelta(hours=LEAD_TIME_HOURS),
            dedup_hash=NormalisedAlert.build_dedup_hash(self.source.value, date_str, severity.value),
            raw_payload_id=validated.raw_payload_id,
            source_url=validated.extra.get("url"),
        )
