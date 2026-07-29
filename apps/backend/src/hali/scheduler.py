"""HALI ingestion scheduler."""
from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

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

    # Condition and named-event feeds. These are the ones that actually produce
    # East Africa alerts day to day: the physical models describe rainfall,
    # while HAPI reports which districts are anomalous and IFRC/WHO report the
    # epidemics and locust responses no satellite sees. Scheduled before the
    # population backfill so new alerts carry exposure the same morning.
    if settings.enable_hapi and "hapi-daily" not in existing_ids:
        scheduler.add_job(
            _run_hapi, CronTrigger(hour=7, minute=10), id="hapi-daily", replace_existing=True
        )
    # IPC is republished roughly three times a year, so a weekly refresh is
    # ample — a daily download of ~60 MB of shapefiles for data that has not
    # changed would be pure waste.
    if settings.enable_fewsnet and "fewsnet-weekly" not in existing_ids:
        scheduler.add_job(
            _run_fewsnet,
            CronTrigger(day_of_week="mon", hour=6, minute=45),
            id="fewsnet-weekly",
            replace_existing=True,
        )
    if (settings.enable_ifrc or settings.enable_who) and "named-events-daily" not in existing_ids:
        scheduler.add_job(
            _run_named_events,
            CronTrigger(hour=7, minute=25),
            id="named-events-daily",
            replace_existing=True,
        )

    # Runs after every ingestion job above so newly inserted alerts get real
    # translations the same day, instead of only once at process startup.
    if settings.ai_enabled and "ai-backlog-daily" not in existing_ids:
        scheduler.add_job(_run_ai_backlog, CronTrigger(hour=8, minute=0), id="ai-backlog-daily", replace_existing=True)

    # Community reports arrive continuously, so hotspot detection is the one job
    # that cannot be daily — an emerging crisis has to surface within the hour.
    if "hotspot-detection" not in existing_ids:
        scheduler.add_job(_run_hotspot_detection, IntervalTrigger(minutes=30), id="hotspot-detection", replace_existing=True)

    # Sits between the last ingestion job and the AI backlog so new alerts carry
    # a population figure by the time their translations are written.
    if "population-backfill" not in existing_ids:
        scheduler.add_job(_run_population_backfill, CronTrigger(hour=7, minute=45), id="population-backfill", replace_existing=True)

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


async def _run_hotspot_detection() -> None:
    try:
        from hali.ai.spatial_clustering import run_hotspot_detection

        result = await run_hotspot_detection(get_pool())
        logger.info("scheduler.hotspot_job_ok", **result)
    except Exception as exc:
        logger.error("scheduler.hotspot_job_failed", error=str(exc))


async def _run_hapi() -> None:
    try:
        from hali.ingestion.hapi import run_ingest

        result = await run_ingest(get_pool())
        logger.info(
            "scheduler.hapi_ok",
            alerts=result["alerts_upserted"],
            skipped_no_geometry=result["skipped_no_geometry"],
        )
    except Exception as exc:
        logger.error("scheduler.hapi_failed", error=str(exc))


async def _run_fewsnet() -> None:
    try:
        from hali.ingestion.fewsnet import run_ingest

        result = await run_ingest(get_pool())
        logger.info(
            "scheduler.fewsnet_ok",
            alerts=result["alerts_upserted"],
            collection_date=result["collection_date"],
        )
    except Exception as exc:
        logger.error("scheduler.fewsnet_failed", error=str(exc))


async def _run_named_events() -> None:
    from hali.ingestion.named_events import ingest_ifrc, ingest_who

    pool = get_pool()
    # Independent feeds: one being down must not cost us the other.
    if settings.enable_ifrc:
        try:
            logger.info("scheduler.ifrc_ok", **await ingest_ifrc(pool))
        except Exception as exc:
            logger.error("scheduler.ifrc_failed", error=str(exc))
    if settings.enable_who:
        try:
            logger.info("scheduler.who_ok", **await ingest_who(pool))
        except Exception as exc:
            logger.error("scheduler.who_failed", error=str(exc))


async def _run_population_backfill() -> None:
    try:
        from hali.services.population import backfill_population_exposure

        result = await backfill_population_exposure(get_pool())
        logger.info("scheduler.population_backfill_ok", **result)
    except Exception as exc:
        logger.error("scheduler.population_backfill_failed", error=str(exc))
