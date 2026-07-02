import asyncio
from uuid import UUID

import asyncpg

from hali.ai.processor import classify_community_report
from hali.config import get_settings
from hali.repositories.reports import ReportRepository
from hali.schemas.alert import CommunityReportCreate


class ReportService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = ReportRepository(pool)

    async def create(self, report: CommunityReportCreate) -> dict:
        created = await self.repo.create(report)
        settings = get_settings()
        if settings.anthropic_api_key:
            asyncio.create_task(classify_community_report(UUID(str(created["id"])), report.description, report.hazard_type, self.pool))
        return created

    async def heatmap(self, days: int) -> dict:
        return await self.repo.heatmap(max(1, min(days, 30)))
