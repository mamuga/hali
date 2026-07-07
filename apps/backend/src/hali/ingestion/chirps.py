"""CHIRPS daily rainfall GeoTIFF adapter."""
from __future__ import annotations

import ftplib
import gzip
import io
import os
import re
import tempfile
from datetime import date as date_cls
from datetime import timedelta

import structlog

from hali.config import settings

from .base import BaseAdapter
from .models import GeoJSONGeometry, HazardType, NormalisedAlert, RawPayload, Severity, SourceName, ValidatedAlert
from .normaliser import bbox_to_multipolygon_geojson, raster_threshold_to_geojson, utc_now

logger = structlog.get_logger(__name__)
CHIRPS_FTP_PATH = "/pub/org/chc/products/CHIRPS-2.0/africa_daily/tifs/p05"
CHIRPS_FILENAME_RE = re.compile(r"chirps-v2\.0\.(\d{4})\.(\d{2})\.(\d{2})\.tif\.gz")
FLOOD_THRESHOLD_MM = 50.0
DROUGHT_THRESHOLD_MM = 2.0


class ChirpsAdapter(BaseAdapter):
    source = SourceName.CHIRPS

    async def extract(self) -> list[RawPayload]:
        if not settings.enable_chirps:
            return []
        try:
            result = await self._download_latest()
            if not result:
                return []
            file_path, found_date = result
            return [
                RawPayload(
                    source=self.source,
                    raw_data={"local_tif_path": file_path, "date": str(found_date)},
                    source_event_id=f"chirps-{found_date}",
                )
            ]
        except Exception as exc:
            logger.error("chirps.extract_failed", error=str(exc))
            return []

    async def _download_latest(self) -> tuple[str, date_cls] | None:
        """CHIRPS provisional daily data lags real time by several weeks, so
        find the newest file actually published rather than assuming T-1
        exists.
        """
        import asyncio

        return await asyncio.get_running_loop().run_in_executor(None, self._ftp_download_latest)

    def _ftp_download_latest(self) -> tuple[str, date_cls] | None:
        cutoff = utc_now().date() - timedelta(days=1)
        try:
            ftp = ftplib.FTP(settings.chirps_ftp_host, timeout=60)
            ftp.login()

            candidates: list[tuple[date_cls, str]] = []
            for year in {cutoff.year, cutoff.year - 1}:
                try:
                    names = ftp.nlst(f"{CHIRPS_FTP_PATH}/{year}")
                except ftplib.error_perm:
                    continue
                for name in names:
                    match = CHIRPS_FILENAME_RE.search(name)
                    if not match:
                        continue
                    found = date_cls(int(match[1]), int(match[2]), int(match[3]))
                    if found <= cutoff:
                        candidates.append((found, name))

            if not candidates:
                ftp.quit()
                logger.warning("chirps.no_files_available", cutoff=str(cutoff))
                return None

            latest_date, latest_name = max(candidates, key=lambda c: c[0])
            buffer = io.BytesIO()
            ftp.retrbinary(f"RETR {CHIRPS_FTP_PATH}/{latest_date.year}/{os.path.basename(latest_name)}", buffer.write)
            ftp.quit()

            buffer.seek(0)
            with gzip.open(buffer) as gz:
                data = gz.read()
            tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
            tmp.write(data)
            tmp.flush()
            tmp.close()
            return tmp.name, latest_date
        except Exception as exc:
            logger.warning("chirps.ftp_failed", error=str(exc))
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

        tif_path = validated.extra.get("local_tif_path")
        date_str = validated.extra.get("date", "unknown")
        try:
            with rasterio.open(tif_path) as src:
                data = src.read(1)
                transform = src.transform
                flood_geom = raster_threshold_to_geojson(data, transform, FLOOD_THRESHOLD_MM, above=True)
                if flood_geom:
                    hazard = HazardType.FLOOD
                    severity = Severity.RED if float(data.max()) > 100 else Severity.ORANGE
                    geometry = flood_geom
                else:
                    drought_geom = raster_threshold_to_geojson(data, transform, DROUGHT_THRESHOLD_MM, above=False)
                    if drought_geom:
                        hazard = HazardType.DROUGHT
                        severity = Severity.ORANGE
                        geometry = drought_geom
                    else:
                        hazard = HazardType.OTHER
                        severity = Severity.GREEN
                        geometry = bbox_to_multipolygon_geojson(21, -12, 52, 24)
        finally:
            if tif_path and os.path.exists(tif_path):
                os.unlink(tif_path)

        now = utc_now()
        return NormalisedAlert(
            source=self.source,
            source_event_id=validated.source_event_id,
            hazard_type=hazard,
            severity=severity,
            geojson_geometry=geometry,
            affected_countries=[],
            valid_from=now,
            valid_to=now + timedelta(hours=24),
            dedup_hash=NormalisedAlert.build_dedup_hash(self.source.value, date_str, severity.value),
            raw_payload_id=validated.raw_payload_id,
        )
