"""Shared load stage for all ingestion adapters."""
from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import structlog

from .models import NormalisedAlert, RawPayload

logger = structlog.get_logger(__name__)


class Loader:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def store_raw(self, raw: RawPayload) -> UUID:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO raw_ingestion (source, external_id, payload, status)
                VALUES ($1, $2, $3::jsonb, 'pending')
                RETURNING id
                """,
                raw.source.value,
                raw.source_event_id,
                json.dumps(raw.raw_data, default=str),
            )
        return row["id"]

    async def mark_raw_processed(self, raw_id: UUID) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE raw_ingestion SET status = 'processed', processed_at = NOW(), error = NULL WHERE id = $1", raw_id)

    async def mark_raw_failed(self, raw_id: UUID, error: str | None = None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE raw_ingestion SET status = 'failed', processed_at = NOW(), error = $2 WHERE id = $1", raw_id, error)

    async def upsert_alert(self, alert: NormalisedAlert) -> bool:
        geom_json = json.dumps(alert.geojson_geometry)
        async with self.pool.acquire() as conn:
            countries = alert.affected_countries or await self._get_affected_countries(conn, geom_json)
            row = await conn.fetchrow(
                """
                INSERT INTO alerts (
                    raw_ingestion_id,
                    hazard_type,
                    severity,
                    affected_countries,
                    geom,
                    valid_from,
                    valid_to,
                    dedup_hash,
                    source,
                    source_url
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($5), 4326)),
                    $6,
                    $7,
                    $8,
                    $9,
                    $10
                )
                ON CONFLICT (dedup_hash) DO NOTHING
                RETURNING id
                """,
                alert.raw_payload_id,
                alert.hazard_type.value,
                alert.severity.value,
                countries,
                geom_json,
                alert.valid_from,
                alert.valid_to,
                alert.dedup_hash,
                alert.source.value,
                alert.source_url,
            )
        return row is not None

    async def _get_affected_countries(self, conn: asyncpg.Connection, geom_json: str) -> list[str]:
        try:
            rows = await conn.fetch(
                """
                SELECT iso2
                FROM countries
                WHERE ST_Intersects(geom, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($1), 4326)))
                """,
                geom_json,
            )
            return [row["iso2"] for row in rows]
        except Exception as exc:
            logger.warning("loader.country_lookup_failed", error=str(exc))
            return []

    async def get_failed_raw_records(self, source: str, limit: int = 50) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, source, created_at, payload
                FROM raw_ingestion
                WHERE status = 'failed' AND source = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                source,
                limit,
            )
        return [dict(row) for row in rows]
