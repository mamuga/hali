"""Admin endpoints for operational ingestion and AI processing controls."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hali.config import settings
from hali.dependencies import require_admin
from hali.scheduler import run_all_ingestion, run_single_source

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])
VALID_SOURCES = {"gdacs", "chirps", "gfs", "glofas", "icpac"}


class TriggerResponse(BaseModel):
    triggered: str
    results: list[dict]


@router.post("/trigger-ingest", response_model=TriggerResponse)
async def trigger_ingest(source: str | None = None):
    if source:
        if source not in VALID_SOURCES:
            raise HTTPException(status_code=400, detail=f"Unknown source {source!r}. Valid: {sorted(VALID_SOURCES)}")
        result = await run_single_source(source)
        return TriggerResponse(triggered=source, results=[result.model_dump(mode="json")] if result else [])
    results = await run_all_ingestion()
    return TriggerResponse(triggered="all", results=[result.model_dump(mode="json") for result in results])


@router.get("/pipeline-status")
async def pipeline_status():
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


@router.post("/process-backlog")
async def trigger_backlog():
    """Process all alerts missing AI translations through the AI pipeline."""
    from hali.ai.processor import process_backlog
    from hali.database import get_pool

    return await process_backlog(get_pool())


@router.post("/process-alert/{alert_id}")
async def process_single_alert(alert_id: UUID):
    """Process one specific alert through the AI pipeline. Good for demos."""
    from hali.ai.processor import get_processor
    from hali.database import get_pool

    processor = get_processor(get_pool())
    result = await processor.process_alert(alert_id)
    return result.model_dump(mode="json")


@router.post("/run-hotspot-detection")
async def run_hotspots():
    """Run DBSCAN emerging-hotspot detection now instead of waiting for the 30-minute job."""
    from hali.ai.spatial_clustering import run_hotspot_detection
    from hali.database import get_pool

    return await run_hotspot_detection(get_pool())


@router.get("/subscriber-stats")
async def subscriber_stats():
    """Subscription counts by channel, language, livelihood, country and opt-in source."""
    from hali.database import get_pool
    from hali.repositories.subscriptions import SubscriptionRepository

    return await SubscriptionRepository(get_pool()).stats()


@router.post("/broadcast-alert/{alert_id}")
async def trigger_broadcast(alert_id: UUID, force: bool = False):
    """Fan an alert out to matching subscribers.

    `force=true` re-sends an alert that was already broadcast — real messages to
    real phones, so it is opt-in rather than the default.
    """
    from hali.database import get_pool
    from hali.services.broadcast import broadcast_alert

    return await broadcast_alert(alert_id, get_pool(), force=force)


@router.post("/backfill-population")
async def backfill_population(limit: int = 25):
    """Fetch WorldPop population exposure for alerts still missing it."""
    from hali.database import get_pool
    from hali.services.population import backfill_population_exposure

    return await backfill_population_exposure(get_pool(), limit)


@router.get("/ai-stats")
async def ai_stats():
    """Return AI router request counts per provider."""
    from hali.ai import processor as processor_module

    if processor_module._processor is None:
        return {"status": "not_initialised"}
    return {
        "status": "active",
        "router_stats": processor_module._processor.router.stats(),
        "ensemble_enabled": settings.ai_ensemble_enabled,
        "primary_model": settings.ai_primary_model,
        "fallback_1": settings.ai_gemini_model,
        "fallback_2": settings.ai_groq_model,
    }
