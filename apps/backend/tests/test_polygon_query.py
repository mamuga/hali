"""Guards on the area-of-interest endpoint.

`/api/spatial/query-polygon` is unauthenticated and accepts arbitrary GeoJSON
straight from a drawing tool, so the geometry has to be bounded before it
reaches PostGIS.
"""
import pytest
from pydantic import ValidationError

from hali.schemas.spatial import (
    MAX_RINGS,
    MAX_SPAN_DEGREES,
    MAX_VERTICES,
    PolygonQuery,
)


def _ring(x0=34.0, y0=2.0, x1=36.0, y1=4.0):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def _polygon(ring=None):
    return {"type": "Polygon", "coordinates": [ring or _ring()]}


class TestAcceptedShapes:
    def test_polygon(self):
        assert PolygonQuery(geometry=_polygon()).geometry["type"] == "Polygon"

    def test_multipolygon(self):
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [[_ring()], [_ring(38, 5, 40, 7)]],
        }
        assert PolygonQuery(geometry=geometry)

    def test_polygon_with_an_interior_ring(self):
        geometry = {"type": "Polygon", "coordinates": [_ring(30, 0, 40, 10), _ring(34, 4, 36, 6)]}
        assert PolygonQuery(geometry=geometry)

    def test_self_intersecting_ring_is_accepted_for_postgis_to_repair(self):
        """A hand-drawn bowtie is a user slip, not an attack — ST_MakeValid fixes it."""
        bowtie = [[34, 2], [36, 4], [36, 2], [34, 4], [34, 2]]
        assert PolygonQuery(geometry=_polygon(bowtie))


class TestRejectedGeometryTypes:
    @pytest.mark.parametrize(
        "geometry",
        [
            {"type": "Point", "coordinates": [34, 2]},
            {"type": "LineString", "coordinates": [[34, 2], [36, 4]]},
            {"type": "GeometryCollection", "geometries": []},
            {"coordinates": [_ring()]},
        ],
    )
    def test_non_area_geometries(self, geometry):
        with pytest.raises(ValidationError, match="Polygon or MultiPolygon"):
            PolygonQuery(geometry=geometry)


class TestRejectedCoordinates:
    @pytest.mark.parametrize("lat", [91, -91, 200])
    def test_latitude_out_of_range(self, lat):
        with pytest.raises(ValidationError, match="latitude"):
            PolygonQuery(geometry=_polygon([[34, lat], [36, 2], [36, 4], [34, lat]]))

    @pytest.mark.parametrize("lng", [181, -181, 999])
    def test_longitude_out_of_range(self, lng):
        with pytest.raises(ValidationError, match="longitude"):
            PolygonQuery(geometry=_polygon([[lng, 2], [36, 2], [36, 4], [lng, 2]]))

    def test_non_numeric_coordinates(self):
        with pytest.raises(ValidationError, match="numbers"):
            PolygonQuery(geometry=_polygon([["a", "b"], [36, 2], [36, 4], ["a", "b"]]))

    def test_booleans_are_not_numbers(self):
        """bool is a subclass of int in Python; it must not slip through."""
        with pytest.raises(ValidationError, match="numbers"):
            PolygonQuery(geometry=_polygon([[True, False], [36, 2], [36, 4], [True, False]]))

    def test_position_needs_two_values(self):
        with pytest.raises(ValidationError, match="lng, lat"):
            PolygonQuery(geometry=_polygon([[34], [36, 2], [36, 4], [34]]))


class TestSizeLimits:
    def test_planet_sized_polygon_is_rejected(self):
        """The case a geography-area cap alone cannot catch.

        ST_Area on `geography` reads a ring enclosing more than a hemisphere as
        its complement, so this measures ~2.8M km2 and passes any sane area cap
        — while ST_Intersects, which runs on planar `geometry`, matches every
        row we hold.
        """
        planet = [[-179, -89], [179, -89], [179, 89], [-179, 89], [-179, -89]]
        with pytest.raises(ValidationError, match="spans"):
            PolygonQuery(geometry=_polygon(planet))

    def test_span_just_over_the_limit_is_rejected(self):
        over = MAX_SPAN_DEGREES + 1
        with pytest.raises(ValidationError, match="spans"):
            PolygonQuery(geometry=_polygon(_ring(0, 0, over, 1)))

    def test_span_just_under_the_limit_is_accepted(self):
        under = MAX_SPAN_DEGREES - 1
        assert PolygonQuery(geometry=_polygon(_ring(0, 0, under, 1)))

    def test_span_is_measured_across_all_parts_of_a_multipolygon(self):
        """Two small squares far apart still describe a huge area of interest."""
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [[_ring(-100, 0, -99, 1)], [_ring(99, 0, 100, 1)]],
        }
        with pytest.raises(ValidationError, match="spans"):
            PolygonQuery(geometry=geometry)

    def test_too_many_vertices(self):
        huge = [[34.0 + i * 1e-6, 2.0] for i in range(MAX_VERTICES + 10)]
        with pytest.raises(ValidationError, match="vertices"):
            PolygonQuery(geometry=_polygon(huge))

    def test_too_many_rings(self):
        geometry = {"type": "Polygon", "coordinates": [_ring() for _ in range(MAX_RINGS + 1)]}
        with pytest.raises(ValidationError, match="rings"):
            PolygonQuery(geometry=geometry)


class TestDegenerateInput:
    def test_empty_coordinates(self):
        with pytest.raises(ValidationError, match="no coordinates"):
            PolygonQuery(geometry={"type": "Polygon", "coordinates": []})

    def test_ring_with_too_few_positions(self):
        with pytest.raises(ValidationError, match="at least 4"):
            PolygonQuery(geometry=_polygon([[34, 2], [36, 2], [34, 2]]))

    def test_empty_polygon_inside_a_multipolygon(self):
        with pytest.raises(ValidationError, match="empty polygon"):
            PolygonQuery(geometry={"type": "MultiPolygon", "coordinates": [[]]})
