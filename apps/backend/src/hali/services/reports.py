import asyncio
from uuid import UUID

import asyncpg
import structlog

from hali.ai.processor import get_processor
from hali.config import get_settings
from hali.repositories.reports import ReportRepository
from hali.schemas.alert import CommunityReportCreate

logger = structlog.get_logger(__name__)

# asyncio keeps only a weak reference to a running task, so a fire-and-forget
# classification could be garbage-collected mid-flight and silently never label
# the report. Holding a strong reference until it finishes prevents that.
_background_tasks: set[asyncio.Task] = set()


class ReportService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = ReportRepository(pool)

    async def create(self, report: CommunityReportCreate) -> dict:
        created = await self.repo.create(report)
        self.schedule_classification(UUID(str(created["id"])), report.description, report.hazard_type)
        return created

    def schedule_classification(self, report_id: UUID, description: str, hazard_type: str) -> None:
        """Classify in the background so the caller still gets an immediate 201."""
        if not get_settings().ai_enabled:
            return
        processor = get_processor(self.pool)
        task = asyncio.create_task(processor.classify_report(report_id, description, hazard_type))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        task.add_done_callback(_log_classification_failure)

    async def heatmap(self, days: int) -> dict:
        return await self.repo.heatmap(max(1, min(days, 30)))


def _log_classification_failure(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("reports.classification_failed", error=str(exc))
