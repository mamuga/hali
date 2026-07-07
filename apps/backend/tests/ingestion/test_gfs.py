"""GFS adapter unit tests."""
from __future__ import annotations

import io
import zipfile
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from hali.ingestion.gfs import GfsAdapter
from hali.ingestion.models import HazardType, RawPayload, SourceName


@pytest.fixture
def adapter(mock_pool):
    pool, _ = mock_pool
    return GfsAdapter(pool)


def _build_global_tif_bytes(fill_value: float) -> bytes:
    """A tiny global-extent raster (mimics the real 0.25deg product's CRS/bounds)."""
    data = np.full((4, 8), fill_value, dtype="float32")
    transform = from_bounds(-180, -90, 180, 90, 8, 4)
    buf = io.BytesIO()
    with rasterio.io.MemoryFile() as mem:
        with mem.open(driver="GTiff", height=4, width=8, count=1, dtype="float32", crs="EPSG:4326", transform=transform) as dst:
            dst.write(data, 1)
        buf.write(mem.read())
    return buf.getvalue()


def _build_zip(date_str: str, fill_value: float) -> bytes:
    tif_bytes = _build_global_tif_bytes(fill_value)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"gfs_precip_shp_tif_{date_str}/gfs_precip_gis_24_{date_str}.tif", tif_bytes)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_extract_falls_back_to_earlier_date(adapter, tmp_path, monkeypatch):
    from hali.config import settings

    monkeypatch.setattr(settings, "enable_gfs", True)

    async def fake_download(url: str):
        if "20260707" in url:
            return None  # today's file not published yet
        path = tmp_path / "gfs.zip"
        path.write_bytes(_build_zip("20260706", 10.0))
        return str(path)

    with (
        patch.object(adapter, "_download_zip", side_effect=fake_download),
        patch("hali.ingestion.gfs.utc_now") as mock_now,
    ):
        import datetime

        mock_now.return_value = datetime.datetime(2026, 7, 7, tzinfo=datetime.UTC)
        payloads = await adapter.extract()

    assert len(payloads) == 1
    assert payloads[0].raw_data["date"] == "20260706"


def test_validate_rejects_missing_zip(adapter):
    raw = RawPayload(source=SourceName.GFS, raw_data={"local_zip_path": "/no/such/file.zip"}, source_event_id="gfs-x")
    assert adapter.validate(raw) is None


def test_transform_crops_to_east_africa_and_detects_extreme_rainfall(adapter, tmp_path):
    date_str = "20260706"
    zip_bytes = _build_zip(date_str, fill_value=200.0)  # well above EXTREME_RAINFALL_MM everywhere
    zip_path = tmp_path / "gfs.zip"
    zip_path.write_bytes(zip_bytes)

    raw = RawPayload(source=SourceName.GFS, raw_data={"local_zip_path": str(zip_path), "date": date_str, "url": "test"}, source_event_id=f"gfs-{date_str}")
    validated = adapter.validate(raw)
    assert validated is not None

    normalised = adapter.transform(validated)
    assert normalised.hazard_type == HazardType.FLOOD
    assert normalised.geojson_geometry["type"] == "MultiPolygon"
    assert not zip_path.exists()  # cleaned up


def test_transform_falls_back_to_bbox_when_below_threshold(adapter, tmp_path):
    date_str = "20260706"
    zip_bytes = _build_zip(date_str, fill_value=0.0)  # well below threshold everywhere
    zip_path = tmp_path / "gfs.zip"
    zip_path.write_bytes(zip_bytes)

    raw = RawPayload(source=SourceName.GFS, raw_data={"local_zip_path": str(zip_path), "date": date_str, "url": "test"}, source_event_id=f"gfs-{date_str}")
    validated = adapter.validate(raw)
    normalised = adapter.transform(validated)
    assert normalised.hazard_type == HazardType.OTHER
    assert normalised.geojson_geometry["type"] == "MultiPolygon"
