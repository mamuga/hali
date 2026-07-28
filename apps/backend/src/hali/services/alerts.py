from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from hali.config import settings
from hali.repositories.alerts import AlertRepository

# Cap per request: generating a translation is an LLM round trip, and a feed of
# 25 uncached alerts would otherwise block the response for minutes.
MAX_ON_DEMAND_TRANSLATIONS = 3


class AlertService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.repo = AlertRepository(pool)

    async def list_alerts(self, lang: str, lat: float | None, lng: float | None, limit: int) -> list[dict]:
        alerts = await self.repo.list_alerts(lang, lat, lng, min(limit, 50))
        await self._backfill_missing_translations(alerts, lang)
        return alerts

    async def _backfill_missing_translations(self, alerts: list[dict], lang: str) -> None:
        """Generate translations on demand for alerts that lack the requested one.

        Action cards already worked this way; translations did not, so a feed in
        a language the backlog had not reached silently served English or a bare
        hazard name. Bounded to a few alerts per request so one cold language
        cannot stall the response.
        """
        if lang == "en" or not settings.ai_enabled:
            return

        missing = [a for a in alerts if not a.get("has_translation")][:MAX_ON_DEMAND_TRANSLATIONS]
        if not missing:
            return

        from hali.ai.processor import get_processor

        processor = get_processor(self.pool)
        for alert in missing:
            try:
                output = await processor.translate_on_demand(alert["id"], lang)
            except Exception:
                continue
            if output and output.headline:
                alert["headline"] = output.headline
                alert["body"] = output.body

    async def geojson(
        self,
        bbox: str,
        lang: str,
        severity: str | None,
        hazard: str | None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict:
        try:
            parts = tuple(float(part) for part in bbox.split(","))
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat") from None
        if len(parts) != 4:
            raise HTTPException(status_code=400, detail="bbox must be minLng,minLat,maxLng,maxLat")
        if from_date and to_date and from_date > to_date:
            raise HTTPException(status_code=400, detail="from_date must not be after to_date")
        return await self.repo.geojson(parts, lang, severity, hazard, from_date, to_date)

    async def action_card(self, alert_id: UUID, livelihood: str, lang: str) -> dict:
        # 1. Fast path - exact livelihood/language match already stored.
        card = await self.repo.action_card(alert_id, livelihood, lang)
        if card is not None:
            return card

        # 2. Not backfilled yet - generate on demand and cache it for next time.
        # No language gate: an alert missing its English card used to 404 rather
        # than generate, because English was assumed to always exist.
        if settings.ai_enabled:
            from hali.ai.processor import get_processor

            try:
                generated = await get_processor(self.pool).generate_action_card_on_demand(alert_id, livelihood, lang)
            except Exception:
                generated = None
            if generated is not None:
                return generated.model_dump()

        # 3. Fall back to English rather than a bare 404 if it exists.
        card = await self.repo.action_card(alert_id, livelihood, "en")
        if card is not None:
            return card

        raise HTTPException(status_code=404, detail="action card not found")
