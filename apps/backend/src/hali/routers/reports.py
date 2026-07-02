from fastapi import APIRouter, Query

from hali.database import db
from hali.schemas.alert import CommunityReportCreate
from hali.services.reports import ReportService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("")
async def create_report(report: CommunityReportCreate) -> dict:
    if db.pool is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="database unavailable")
    return await ReportService(db.pool).create(report)


@router.get("/heatmap")
async def heatmap(days: int = Query(7, ge=1, le=30)) -> dict:
    if db.pool is None:
        return {"type": "FeatureCollection", "features": []}
    return await ReportService(db.pool).heatmap(days)
