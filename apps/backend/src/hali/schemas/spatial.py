"""Request schemas for the spatial analysis endpoints."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# An area-of-interest is drawn by hand on a phone or laptop. These bounds are
# generous for that and still refuse the shapes that would turn an open endpoint
# into a way to make PostGIS chew CPU: a million-vertex ring, or a polygon
# covering the planet that intersects every row in every table.
MAX_RINGS = 64
MAX_VERTICES = 10_000
MIN_RING_VERTICES = 4  # a closed triangle

# The primary size guard, and the only one that cannot be fooled.
#
# ST_Area on `geography` interprets a ring enclosing more than a hemisphere as
# its complement, so a polygon covering the whole planet measures ~2.8M km2 and
# slips under any plausible area cap — while ST_Intersects runs on planar
# `geometry`, where that same ring really does cover everything. Bounding the
# envelope in degrees has no such blind spot, and it costs no database round
# trip. IGAD spans ~32 deg by ~30 deg, so this is generous for any real AOI.
MAX_SPAN_DEGREES = 60.0

# Secondary check, applied after PostGIS measures the shape. Catches a wildly
# oversized area that still fits inside the span limit.
MAX_AREA_KM2 = 20_000_000  # ~13% of Earth's land area; IGAD itself is ~5.2M

Position = list[float]


class PolygonQuery(BaseModel):
    """A drawn area of interest.

    Only Polygon and MultiPolygon are accepted. A LineString or Point would be
    silently valid GeoJSON that then matches nothing, which reads as "there is
    no data here" rather than "you drew the wrong thing".
    """

    geometry: dict[str, Any] = Field(..., description="GeoJSON Polygon or MultiPolygon")

    @field_validator("geometry")
    @classmethod
    def _validate_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        geom_type = value.get("type")
        if geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("geometry must be a Polygon or MultiPolygon")

        coordinates = value.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("geometry has no coordinates")

        polygons = coordinates if geom_type == "MultiPolygon" else [coordinates]

        rings = 0
        vertices = 0
        lngs: list[float] = []
        lats: list[float] = []
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("geometry contains an empty polygon")
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < MIN_RING_VERTICES:
                    raise ValueError("every ring needs at least 4 positions and must be closed")
                rings += 1
                vertices += len(ring)
                for position in ring:
                    _validate_position(position)
                    lngs.append(position[0])
                    lats.append(position[1])

        if rings > MAX_RINGS:
            raise ValueError(f"geometry has {rings} rings, limit is {MAX_RINGS}")
        if vertices > MAX_VERTICES:
            raise ValueError(f"geometry has {vertices} vertices, limit is {MAX_VERTICES}")

        lng_span = max(lngs) - min(lngs)
        lat_span = max(lats) - min(lats)
        if lng_span > MAX_SPAN_DEGREES or lat_span > MAX_SPAN_DEGREES:
            raise ValueError(
                f"area of interest spans {lng_span:.0f} deg by {lat_span:.0f} deg, "
                f"limit is {MAX_SPAN_DEGREES:.0f} deg — draw a smaller region"
            )

        return value


def _validate_position(position: Any) -> None:
    if not isinstance(position, (list, tuple)) or len(position) < 2:
        raise ValueError("each position must be a [lng, lat] pair")
    lng, lat = position[0], position[1]
    if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
        raise ValueError("coordinates must be numbers")
    if isinstance(lng, bool) or isinstance(lat, bool):
        raise ValueError("coordinates must be numbers")
    if not -180 <= lng <= 180:
        raise ValueError(f"longitude {lng} is out of range")
    if not -90 <= lat <= 90:
        raise ValueError(f"latitude {lat} is out of range")


class PolygonQueryAlert(BaseModel):
    id: str
    hazard_type: str
    severity: Literal["green", "orange", "red"]
    headline: str
    valid_to: Any | None = None
    population_exposed: int | None = None
    overlap_km2: float


class PolygonQueryResult(BaseModel):
    area_km2: float
    alerts: list[PolygonQueryAlert]
    report_count: int
    report_hazards: list[str]
    emerging_hotspots: int
    #: None when no population grid has been ingested yet — never confuse that
    #: with "nobody lives here".
    population_estimate: int | None = None
