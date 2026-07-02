from uuid import UUID

from fastapi import APIRouter, Query

from hali.database import db
from hali.schemas.alert import Language, Livelihood
from hali.services.alerts import AlertService

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(lang: Language = "en", lat: float | None = None, lng: float | None = None, limit: int = Query(25, le=50)) -> list[dict]:
    if db.pool is None:
        return []
    return await AlertService(db.pool).list_alerts(lang, lat, lng, limit)


@router.get("/geojson")
async def geojson(bbox: str = "21,-12,52,24", severity: str | None = None, hazard: str | None = None, lang: Language = "sw") -> dict:
    if db.pool is None:
        return {"type": "FeatureCollection", "features": []}
    return await AlertService(db.pool).geojson(bbox, lang, severity, hazard)


@router.get("/{alert_id}/action-card")
async def action_card(alert_id: UUID, livelihood: Livelihood, lang: Language = "en") -> dict:
    if db.pool is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="database unavailable")
    return await AlertService(db.pool).action_card(alert_id, livelihood, lang)
