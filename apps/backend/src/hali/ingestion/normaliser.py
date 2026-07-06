"""Pure normaliser utilities shared across ingestion adapters."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shapely.geometry import MultiPolygon, box, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from .models import HazardType, Severity

GDACS_HAZARD_MAP: dict[str, HazardType] = {
    "FL": HazardType.FLOOD,
    "DR": HazardType.DROUGHT,
    "TC": HazardType.CYCLONE,
    "EQ": HazardType.OTHER,
    "VO": HazardType.OTHER,
    "WF": HazardType.OTHER,
    "LS": HazardType.OTHER,
}

GDACS_SEVERITY_MAP: dict[str, Severity] = {
    "Green": Severity.GREEN,
    "Orange": Severity.ORANGE,
    "Red": Severity.RED,
}


def to_multipolygon_geojson(geojson: dict[str, Any]) -> dict[str, Any]:
    geom_type = geojson.get("type", "")
    if geom_type == "Point":
        shp = shape(geojson).buffer(0.5)
    elif geom_type in {"Polygon", "MultiPolygon"}:
        shp = shape(geojson)
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type!r}")

    if not shp.is_valid:
        shp = make_valid(shp)

    if shp.geom_type == "Polygon":
        shp = MultiPolygon([shp])
    elif shp.geom_type == "GeometryCollection":
        polygons = [part for part in shp.geoms if part.geom_type == "Polygon"]
        if not polygons:
            raise ValueError("GeometryCollection contains no polygons")
        shp = MultiPolygon(polygons)
    elif shp.geom_type != "MultiPolygon":
        raise ValueError(f"Cannot convert {shp.geom_type} to MultiPolygon")

    return dict(mapping(shp))


def bbox_to_multipolygon_geojson(min_lng: float, min_lat: float, max_lng: float, max_lat: float) -> dict[str, Any]:
    return dict(mapping(MultiPolygon([box(min_lng, min_lat, max_lng, max_lat)])))


def raster_threshold_to_geojson(data_array: Any, transform: Any, threshold: float, above: bool = True) -> dict[str, Any] | None:
    import numpy as np
    import rasterio.features

    mask = (data_array > threshold) if above else (data_array < threshold)
    mask = mask.astype(np.uint8)
    if mask.sum() == 0:
        return None

    shapes = list(rasterio.features.shapes(mask, transform=transform))
    polygons = [shape(geom) for geom, value in shapes if value == 1]
    if not polygons:
        return None

    merged = unary_union(polygons)
    if merged.is_empty:
        return None
    if not merged.is_valid:
        merged = make_valid(merged)
    if merged.geom_type == "Polygon":
        merged = MultiPolygon([merged])
    elif merged.geom_type == "GeometryCollection":
        polygons = [part for part in merged.geoms if part.geom_type == "Polygon"]
        if not polygons:
            return None
        merged = MultiPolygon(polygons)
    return dict(mapping(merged))


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (AttributeError, ValueError):
        return None


def utc_now() -> datetime:
    return datetime.now(UTC)
