from uuid import UUID

import asyncpg
from fastapi import HTTPException

from hali.repositories.alerts import AlertRepository


class AlertService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.repo = AlertRepository(pool)

    async def list_alerts(self, lang: str, lat: float | None, lng: float | None, limit: int) -> list[dict]:
        return await self.repo.list_alerts(lang, lat, lng, min(limit, 50))

    async def geojson(self, bbox: str, lang: str, severity: str | None, hazard: str | None) -> dict:
        parts = tuple(float(part) for part in bbox.split(","))
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat")
        return await self.repo.geojson(parts, lang, severity, hazard)

    async def action_card(self, alert_id: UUID, livelihood: str, lang: str) -> dict:
        card = await self.repo.action_card(alert_id, livelihood, lang)
        if card is None:
            raise HTTPException(status_code=404, detail="action card not found")
        return card
