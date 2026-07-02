import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import structlog

from hali.config import Settings
from hali.ingestion.base import AdapterStatus, NormalizedAlert
from hali.ingestion.normaliser import dedup_hash, hazard, severity

log = structlog.get_logger()
EAST_AFRICA_BBOX_POLYGON = {"type":"MultiPolygon","coordinates":[[[[21,-12],[52,-12],[52,24],[21,24],[21,-12]]]]}


class GdacsAdapter:
    source = "gdacs"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def status(self) -> AdapterStatus:
        return AdapterStatus(self.source, self.settings.enable_gdacs, "enabled" if self.settings.enable_gdacs else "disabled", "GDACS RSS East Africa bbox")

    async def fetch(self) -> list[NormalizedAlert]:
        if not self.settings.enable_gdacs:
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(self.settings.gdacs_url)
            response.raise_for_status()
        root = ET.fromstring(response.text)
        alerts: list[NormalizedAlert] = []
        for item in root.findall(".//item"):
            title = item.findtext("title") or "GDACS alert"
            link = item.findtext("link") or ""
            category = item.findtext("category") or title
            pub_date = datetime.now(UTC).isoformat()
            payload = {"title": title, "link": link, "category": category}
            alerts.append(NormalizedAlert(self.source, link or title, hazard(category), severity(title), ["Kenya","Ethiopia","Somalia","Uganda","Djibouti","Eritrea","Sudan","South Sudan"], EAST_AFRICA_BBOX_POLYGON, pub_date, (datetime.now(UTC)+timedelta(days=7)).isoformat(), payload))
        return alerts

    async def ingest(self, pool: asyncpg.Pool) -> int:
        count = 0
        for alert in await self.fetch():
            raw_id = None
            async with pool.acquire() as conn:
                raw_id = await conn.fetchval("INSERT INTO raw_ingestion (source, external_id, payload) VALUES ($1,$2,$3::jsonb) RETURNING id", alert.source, alert.external_id, json.dumps(alert.payload))
                try:
                    await conn.execute(
                        """
                        INSERT INTO alerts (raw_ingestion_id, hazard_type, severity, affected_countries, geometry, valid_from, valid_to, dedup_hash, source, source_url)
                        VALUES ($1,$2,$3,$4,ST_Multi(ST_GeomFromGeoJSON($5)), $6::timestamptz, $7::timestamptz, $8, $9, $10)
                        ON CONFLICT (dedup_hash) DO NOTHING
                        """,
                        raw_id, alert.hazard_type, alert.severity, alert.affected_countries, json.dumps(alert.geometry_geojson), alert.valid_from, alert.valid_to, dedup_hash(alert.payload), alert.source, alert.payload.get("link"),
                    )
                    await conn.execute("UPDATE raw_ingestion SET status='processed', processed_at=NOW() WHERE id=$1", raw_id)
                    count += 1
                except Exception as exc:
                    await conn.execute("UPDATE raw_ingestion SET status='failed', error=$2 WHERE id=$1", raw_id, str(exc))
                    log.exception("gdacs_ingest_failed", raw_id=str(raw_id))
        return count
