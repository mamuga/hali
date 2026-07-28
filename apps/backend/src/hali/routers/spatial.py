"""Spatial analysis endpoints — compound risk, click-to-analyse, emerging hotspots."""
from fastapi import APIRouter, Query

from hali.database import db
from hali.schemas.alert import Language
from hali.services.spatial import SpatialService

router = APIRouter(prefix="/api/spatial", tags=["spatial"])

EMPTY_COLLECTION = {"type": "FeatureCollection", "features": []}


@router.get("/compound-risk")
async def compound_risk() -> dict:
    """Compound risk score per IGAD member state, for the map choropleth."""
    if db.pool is None:
        return EMPTY_COLLECTION
    return await SpatialService(db.pool).compound_risk()


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
