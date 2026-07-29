"""WorldPop raster aggregation and loading.

The aggregation is the part worth testing: a sign error or an off-by-one in the
affine transform puts every population cell in the wrong place, and the result
still looks plausible in aggregate.
"""
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from hali.ingestion.worldpop import (
    BLOCK,
    ISO2_TO_ISO3,
    MIN_CELL_POPULATION,
    WORLDPOP_URL_TEMPLATE,
    WorldPopIngestError,
    aggregate_raster,
    run_ingest,
)


def _write_raster(path: Path, data: np.ndarray, *, west=34.0, north=5.0, res=0.0083333, nodata=None):
    transform = from_origin(west, north, res, res)
    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": transform,
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)
    return path


class TestAggregation:
    def test_sums_each_block(self, tmp_path):
        # One 5x5 block where every pixel holds 4 people -> 100 in one cell.
        data = np.full((BLOCK, BLOCK), 4.0)
        path = _write_raster(tmp_path / "a.tif", data)

        records = aggregate_raster(path, "KE")

        assert len(records) == 1
        iso2, lng, lat, pop = records[0]
        assert iso2 == "KE"
        assert pop == 100

    def test_cell_centre_falls_inside_the_block(self, tmp_path):
        data = np.full((BLOCK, BLOCK), 4.0)
        res = 0.01
        path = _write_raster(tmp_path / "a.tif", data, west=34.0, north=5.0, res=res)

        _, lng, lat, _ = aggregate_raster(path, "KE")[0]

        # Block spans lng 34.00..34.05 and lat 4.95..5.00; centre is the middle.
        assert 34.0 < lng < 34.05
        assert 4.95 < lat < 5.0
        assert lng == pytest.approx(34.025, abs=1e-6)
        assert lat == pytest.approx(4.975, abs=1e-6)

    def test_latitude_decreases_going_south(self, tmp_path):
        """A sign error here silently mirrors the whole grid across the equator."""
        data = np.full((BLOCK * 2, BLOCK), 4.0)
        path = _write_raster(tmp_path / "a.tif", data, north=5.0, res=0.01)

        records = sorted(aggregate_raster(path, "KE"), key=lambda r: -r[2])

        assert records[0][2] > records[1][2]
        assert records[0][2] == pytest.approx(4.975, abs=1e-6)

    def test_negative_values_are_clamped(self, tmp_path):
        data = np.full((BLOCK, BLOCK), -9999.0)
        path = _write_raster(tmp_path / "a.tif", data)

        assert aggregate_raster(path, "KE") == []

    def test_nodata_sentinel_is_excluded(self, tmp_path):
        """WorldPop marks no-data with a large negative sentinel; if it is only
        clamped to zero rather than removed, block sums stay correct here but
        the intent is lost — assert it explicitly."""
        data = np.full((BLOCK, BLOCK), -3.4e38)
        data[0, 0] = 10.0
        path = _write_raster(tmp_path / "a.tif", data, nodata=-3.4e38)

        records = aggregate_raster(path, "KE")

        assert len(records) == 1
        assert records[0][3] == 10

    def test_nan_is_ignored(self, tmp_path):
        data = np.full((BLOCK, BLOCK), np.nan)
        data[0, 0] = 7.0
        path = _write_raster(tmp_path / "a.tif", data)

        records = aggregate_raster(path, "KE")

        assert len(records) == 1
        assert records[0][3] == 7

    def test_near_empty_cells_are_dropped(self, tmp_path):
        """Smoothed floats over empty desert would otherwise add tens of
        thousands of rows carrying essentially zero people."""
        data = np.full((BLOCK, BLOCK), 0.004)
        path = _write_raster(tmp_path / "a.tif", data)

        assert aggregate_raster(path, "KE") == []
        assert MIN_CELL_POPULATION >= 1

    def test_partial_trailing_block_is_dropped(self, tmp_path):
        # 7x7 with BLOCK=5 -> only the complete 5x5 block is emitted.
        data = np.ones((BLOCK + 2, BLOCK + 2)) * 4.0
        path = _write_raster(tmp_path / "a.tif", data)

        assert len(aggregate_raster(path, "KE")) == 1

    def test_raster_smaller_than_one_block(self, tmp_path):
        data = np.ones((2, 2)) * 100.0
        path = _write_raster(tmp_path / "a.tif", data)

        assert aggregate_raster(path, "KE") == []

    def test_population_is_conserved_across_blocks(self, tmp_path):
        rng = np.random.default_rng(0)
        data = rng.integers(1, 50, size=(BLOCK * 4, BLOCK * 4)).astype("float32")
        path = _write_raster(tmp_path / "a.tif", data)

        records = aggregate_raster(path, "KE")

        # Rounding is per cell, so allow one person of drift per cell.
        assert sum(r[3] for r in records) == pytest.approx(data.sum(), abs=len(records))


class TestConfiguration:
    def test_every_igad_country_is_mapped(self):
        assert set(ISO2_TO_ISO3) == {"KE", "ET", "SO", "UG", "DJ", "ER", "SD", "SS"}

    def test_url_template_matches_the_verified_pattern(self):
        url = WORLDPOP_URL_TEMPLATE.format(year=2020, iso3="KEN", iso3_lower="ken")
        assert url == (
            "https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/"
            "2020/KEN/ken_ppp_2020_1km_Aggregated_UNadj.tif"
        )

    async def test_unknown_country_code_is_rejected_before_downloading(self):
        with pytest.raises(WorldPopIngestError, match="unknown country codes"):
            await run_ingest(pool=None, only=["KE", "ZZ"])
