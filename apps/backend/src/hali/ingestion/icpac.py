"""ICPAC digilib Standardised Precipitation Index adapter."""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import httpx
import structlog

from hali.config import settings

from .base import BaseAdapter
from .models import GeoJSONGeometry, HazardType, NormalisedAlert, RawPayload, Severity, SourceName, ValidatedAlert
from .normaliser import bbox_to_multipolygon_geojson, raster_threshold_to_geojson, utc_now

logger = structlog.get_logger(__name__)
ICPAC_SPI_URL = "{base}/SOURCES/.ICPAC/.SPI/T/%28{month}%20{year}%29VALUE/data.nc"
DROUGHT_SEVERE = -2.0
DROUGHT_MODERATE = -1.0
FLOOD_WET = 2.0


class IcpacAdapter(BaseAdapter):
    source = SourceName.ICPAC

    async def extract(self) -> list[RawPayload]:
        if not settings.enable_icpac:
            return []
        try:
            now = utc_now()
            month, year = (12, now.year - 1) if now.month == 1 else (now.month - 1, now.year)
            month_name = now.replace(month=month).strftime("%b")
            url = ICPAC_SPI_URL.format(base=settings.icpac_digilib_base, month=month_name, year=year)
            nc_path = await self._download_nc(url)
            if not nc_path:
                return []
            return [
                RawPayload(
                    source=self.source,
                    raw_data={"local_nc_path": nc_path, "month": month_name, "year": year, "url": url},
                    source_event_id=f"icpac-spi-{year}-{month:02d}",
                )
            ]
        except Exception as exc:
            logger.error("icpac.extract_failed", error=str(exc))
            return []

    async def _download_nc(self, url: str) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url)
                response.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
            tmp.write(response.content)
            tmp.flush()
            tmp.close()
            return tmp.name
        except Exception as exc:
            logger.warning("icpac.download_failed", url=url, error=str(exc))
            return None

    def validate(self, raw: RawPayload) -> ValidatedAlert | None:
        nc_path = raw.raw_data.get("local_nc_path")
        if not nc_path or not os.path.exists(nc_path):
            return None
        return ValidatedAlert(
            source=self.source,
            source_event_id=raw.source_event_id,
            hazard_type=HazardType.DROUGHT,
            severity=Severity.GREEN,
            geometry=GeoJSONGeometry(type="Polygon", coordinates=[[[21, -12], [52, -12], [52, 24], [21, 24], [21, -12]]]),
            extra=raw.raw_data,
        )

    def transform(self, validated: ValidatedAlert) -> NormalisedAlert:
        import rasterio.transform
        import xarray as xr

        nc_path = validated.extra["local_nc_path"]
        event_id = validated.source_event_id
        try:
            ds = xr.open_dataset(nc_path)
            var_name = next((name for name in ds.data_vars if "spi" in name.lower()), None)
            if var_name is None:
                raise ValueError(f"No SPI variable found. Available: {list(ds.data_vars)}")
            spi_data = ds[var_name].values.squeeze()
            lats = ds.lat.values if "lat" in ds else ds.latitude.values
            lons = ds.lon.values if "lon" in ds else ds.longitude.values
            ds.close()
            transform = rasterio.transform.from_bounds(lons.min(), lats.min(), lons.max(), lats.max(), spi_data.shape[1], spi_data.shape[0])

            severe = raster_threshold_to_geojson(spi_data, transform, DROUGHT_SEVERE, above=False)
            if severe:
                geom, hazard, severity = severe, HazardType.DROUGHT, Severity.RED
            else:
                moderate = raster_threshold_to_geojson(spi_data, transform, DROUGHT_MODERATE, above=False)
                if moderate:
                    geom, hazard, severity = moderate, HazardType.DROUGHT, Severity.ORANGE
                else:
                    wet = raster_threshold_to_geojson(spi_data, transform, FLOOD_WET, above=True)
                    if wet:
                        geom, hazard, severity = wet, HazardType.FLOOD, Severity.ORANGE
                    else:
                        geom = bbox_to_multipolygon_geojson(21, -12, 52, 24)
                        hazard, severity = HazardType.OTHER, Severity.GREEN
        finally:
            if nc_path and os.path.exists(nc_path):
                os.unlink(nc_path)

        now = utc_now()
        return NormalisedAlert(
            source=self.source,
            source_event_id=event_id,
            hazard_type=hazard,
            severity=severity,
            geojson_geometry=geom,
            affected_countries=[],
            valid_from=now,
            valid_to=now + timedelta(days=30),
            dedup_hash=NormalisedAlert.build_dedup_hash(self.source.value, event_id, severity.value),
            raw_payload_id=validated.raw_payload_id,
        )
