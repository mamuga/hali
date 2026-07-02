import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from hali.config import Settings
from hali.ingestion.chirps import ChirpsAdapter
from hali.ingestion.gdacs import GdacsAdapter
from hali.ingestion.gfs import GfsAdapter
from hali.ingestion.glofas import GlofasAdapter
from hali.ingestion.icpac import IcpacAdapter

log = structlog.get_logger()


def build_scheduler(settings: Settings, pool) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(lambda: GdacsAdapter(settings).ingest(pool), CronTrigger(hour=6, minute=0), id="gdacs-daily")
    for adapter, hour, minute, flag in [
        (ChirpsAdapter, 6, 15, settings.enable_chirps),
        (GfsAdapter, 6, 30, settings.enable_gfs),
        (GlofasAdapter, 6, 45, settings.enable_glofas),
        (IcpacAdapter, 7, 0, settings.enable_icpac),
    ]:
        if flag:
            scheduler.add_job(lambda a=adapter: a(settings).fetch(), CronTrigger(hour=hour, minute=minute), id=f"{adapter.source}-daily")
    return scheduler
