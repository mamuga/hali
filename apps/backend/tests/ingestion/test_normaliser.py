"""Unit tests for normaliser pure functions."""
from hali.ingestion.models import HazardType, Severity
from hali.ingestion.normaliser import GDACS_HAZARD_MAP, GDACS_SEVERITY_MAP, bbox_to_multipolygon_geojson, parse_iso_datetime, to_multipolygon_geojson


def test_bbox_to_multipolygon():
    geom = bbox_to_multipolygon_geojson(33.0, -4.0, 42.0, 5.0)
    assert geom["type"] == "MultiPolygon"
    assert len(geom["coordinates"]) == 1


def test_polygon_to_multipolygon():
    polygon = {"type": "Polygon", "coordinates": [[[36.0, -1.0], [42.0, -1.0], [42.0, 5.0], [36.0, 5.0], [36.0, -1.0]]]}
    assert to_multipolygon_geojson(polygon)["type"] == "MultiPolygon"


def test_multipolygon_passthrough():
    mp = bbox_to_multipolygon_geojson(21, -12, 52, 24)
    assert to_multipolygon_geojson(mp)["type"] == "MultiPolygon"


def test_parse_iso_datetime_utc():
    dt = parse_iso_datetime("2026-07-01T00:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_iso_datetime_none():
    assert parse_iso_datetime(None) is None
    assert parse_iso_datetime("") is None
    assert parse_iso_datetime("not-a-date") is None


def test_gdacs_hazard_map_complete():
    assert GDACS_HAZARD_MAP["FL"] == HazardType.FLOOD
    assert GDACS_HAZARD_MAP["DR"] == HazardType.DROUGHT
    assert GDACS_HAZARD_MAP["TC"] == HazardType.CYCLONE


def test_gdacs_severity_map_complete():
    assert GDACS_SEVERITY_MAP["Red"] == Severity.RED
    assert GDACS_SEVERITY_MAP["Orange"] == Severity.ORANGE
    assert GDACS_SEVERITY_MAP["Green"] == Severity.GREEN
