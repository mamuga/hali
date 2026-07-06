"""Admin endpoints for operational ingestion controls."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hali.config import settings
from hali.scheduler import run_all_ingestion, run_single_source

router = APIRouter(prefix="/api/admin", tags=["admin"])
VALID_SOURCES = {"gdacs", "chirps", "gfs", "glofas", "icpac"}


class TriggerResponse(BaseModel):
    triggered: str
    results: list[dict]


@router.post("/trigger-ingest", response_model=TriggerResponse)
async def trigger_ingest(source: str | None = None):
    if not settings.enable_admin_endpoints:
        raise HTTPException(status_code=403, detail="Admin endpoints disabled")
    if source:
        if source not in VALID_SOURCES:
            raise HTTPException(status_code=400, detail=f"Unknown source {source!r}. Valid: {sorted(VALID_SOURCES)}")
        result = await run_single_source(source)
        return TriggerResponse(triggered=source, results=[result.model_dump(mode="json")] if result else [])
    results = await run_all_ingestion()
    return TriggerResponse(triggered="all", results=[result.model_dump(mode="json") for result in results])


@router.get("/pipeline-status")
async def pipeline_status():
    if not settings.enable_admin_endpoints:
        raise HTTPException(status_code=403, detail="Admin endpoints disabled")
    return {
        "scheduler_enabled": settings.enable_scheduler,
        "sources": {
            "gdacs": {"enabled": settings.enable_gdacs, "credentials": True},
            "chirps": {"enabled": settings.enable_chirps, "credentials": True},
            "gfs": {"enabled": settings.enable_gfs, "credentials": True},
            "glofas": {"enabled": settings.enable_glofas, "credentials": bool(settings.glofas_cds_api_key)},
            "icpac": {"enabled": settings.enable_icpac, "credentials": True},
        },
        "schedule_utc": {"gdacs": "06:00", "gfs": "06:15", "glofas": "06:30", "chirps": "07:00", "icpac": "07:30"},
    }
