"""Spatial analysis endpoints — compound risk, click-to-analyse, emerging hotspots, AOI query."""
import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Query

from hali.database import db
from hali.schemas.alert import Language
from hali.schemas.spatial import PolygonQuery
from hali.services.spatial import SpatialService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/spatial", tags=["spatial"])

EMPTY_COLLECTION = {"type": "FeatureCollection", "features": []}


@router.get("/compound-risk")
async def compound_risk() -> dict:
    """Compound risk score per IGAD member state, for the map choropleth."""
    if db.pool is None:
        return EMPTY_COLLECTION
    return await SpatialService(db.pool).compound_risk()


# ~2 km at the equator. Invisible at this map's minimum zoom, and a quarter the
# bytes of the raw 1:10m geometry.
DEFAULT_BOUNDARY_TOLERANCE = 0.02


@router.get("/countries/geojson")
async def countries_geojson(
    tolerance: float = Query(
        DEFAULT_BOUNDARY_TOLERANCE,
        ge=0.0,
        le=0.5,
        description="Douglas-Peucker tolerance in degrees. 0 returns full 1:10m detail.",
    ),
) -> dict:
    """IGAD boundaries for the map's outlines and outside-IGAD mask."""
    if db.pool is None:
        return EMPTY_COLLECTION
    return await SpatialService(db.pool).countries_geojson(tolerance)


@router.get("/emerging-hotspots")
async def emerging_hotspots() -> dict:
    """DBSCAN report clusters with no official alert covering them."""
    if db.pool is None:
        return EMPTY_COLLECTION
    return await SpatialService(db.pool).emerging_hotspots()


@router.get("/analyse")
async def analyse(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    lang: Language = "en",
) -> dict:
    """Location intelligence for a point: nearest alerts, reports, hotspots."""
    if db.pool is None:
        return {"location": {"lat": lat, "lng": lng}, "country": None, "nearest_alerts": [], "nearby_reports_7d": 0, "report_breakdown": [], "emerging_hotspots_nearby": 0}
    return await SpatialService(db.pool).analyse(lat, lng, lang)


@router.post("/query-polygon")
async def query_polygon(query: PolygonQuery, lang: Language = "en") -> dict:
    """Every alert, report and hotspot inside a user-drawn area of interest.

    Unauthenticated and accepts arbitrary GeoJSON, so the geometry is bounded by
    the schema (rings, vertices, coordinate ranges) and the area is measured
    before any spatial join runs.
    """
    if db.pool is None:
        raise HTTPException(status_code=503, detail="database unavailable")

    try:
        return await SpatialService(db.pool).query_polygon(query.geometry, lang)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except asyncpg.PostgresError as exc:
        # A shape PostGIS cannot repair is the caller's problem, not a 500.
        logger.warning("spatial.query_polygon_failed", error=str(exc))
        raise HTTPException(status_code=422, detail="geometry could not be processed") from exc
