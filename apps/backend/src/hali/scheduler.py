"""HALI ingestion scheduler."""
from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from hali.config import settings
from hali.database import get_pool
from hali.ingestion import get_enabled_adapters
from hali.ingestion.models import IngestionResult

logger = structlog.get_logger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def run_all_ingestion() -> list[IngestionResult]:
    pool = get_pool()
    adapters = get_enabled_adapters(pool)
    results: list[IngestionResult] = []
    for adapter in adapters:
        try:
            result = await adapter.run()
            results.append(result)
            logger.info(
                "scheduler.adapter_complete",
                source=adapter.source.value,
                inserted=result.inserted_count,
                failed=result.failed_count,
                duration_ms=result.duration_ms,
            )
        except Exception as exc:
            logger.error("scheduler.adapter_crashed", source=adapter.source.value, error=str(exc))
    logger.info("scheduler.run_complete", adapter_count=len(adapters), total_inserted=sum(r.inserted_count for r in results))
    return results


async def run_single_source(source_name: str) -> IngestionResult | None:
    pool = get_pool()
    adapters = get_enabled_adapters(pool)
    for adapter in adapters:
        if adapter.source.value == source_name:
            return await adapter.run()
    return None


def setup_scheduler() -> AsyncIOScheduler:
    if not settings.enable_scheduler:
        logger.info("scheduler.disabled")
        return scheduler

    if scheduler.running:
        return scheduler

    existing_ids = {job.id for job in scheduler.get_jobs()}
    jobs = [
        ("gdacs-daily", "gdacs", settings.enable_gdacs, 6, 0),
        ("gfs-daily", "gfs", settings.enable_gfs, 6, 15),
        ("glofas-daily", "glofas", settings.enable_glofas, 6, 30),
        ("chirps-daily", "chirps", settings.enable_chirps, 7, 0),
        ("icpac-daily", "icpac", settings.enable_icpac, 7, 30),
    ]
    for job_id, name, enabled, hour, minute in jobs:
        if enabled and job_id not in existing_ids:
            scheduler.add_job(_run_source, CronTrigger(hour=hour, minute=minute), args=[name], id=job_id, replace_existing=True)

    # Runs after every ingestion job above so newly inserted alerts get real
    # translations the same day, instead of only once at process startup.
    if settings.ai_enabled and "ai-backlog-daily" not in existing_ids:
        scheduler.add_job(_run_ai_backlog, CronTrigger(hour=8, minute=0), id="ai-backlog-daily", replace_existing=True)

    enabled_sources = [name for _, name, enabled, _, _ in jobs if enabled]
    logger.info("scheduler.configured", enabled_sources=enabled_sources, ai_backlog_scheduled=settings.ai_enabled)
    return scheduler


def build_scheduler(*_args: object, **_kwargs: object) -> AsyncIOScheduler:
    return setup_scheduler()


async def _run_source(name: str) -> None:
    try:
        result = await run_single_source(name)
        if result:
            logger.info(
                "scheduler.job_ok",
                source=name,
                inserted=result.inserted_count,
                skipped=result.skipped_count,
                failed=result.failed_count,
            )
    except Exception as exc:
        logger.error("scheduler.job_failed", source=name, error=str(exc))


async def _run_ai_backlog() -> None:
    try:
        from hali.ai.processor import process_backlog

        result = await process_backlog(get_pool())
        logger.info("scheduler.ai_backlog_job_ok", **result)
    except Exception as exc:
        logger.error("scheduler.ai_backlog_job_failed", error=str(exc))
