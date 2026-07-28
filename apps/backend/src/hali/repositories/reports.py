import json
from typing import Any
from uuid import UUID

import asyncpg

from hali.schemas.alert import CommunityReportCreate


class ReportRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def create(self, report: CommunityReportCreate) -> dict[str, Any]:
        sql = """
        INSERT INTO community_reports (hazard_type, description, location)
        VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326))
        RETURNING id, hazard_type, description, ST_Y(location) AS lat, ST_X(location) AS lng, labels, reported_at
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, report.hazard_type, report.description, report.lng, report.lat)
        return dict(row)

    async def create_from_channel(
        self,
        hazard_type: str,
        description: str,
        lat: float,
        lng: float,
        channel: str,
        phone_number: str | None = None,
    ) -> dict[str, Any]:
        """Insert a report arriving from USSD or WhatsApp.

        Those channels carry no GPS, so the caller resolves a country-level
        point before calling this.
        """
        sql = """
        INSERT INTO community_reports (hazard_type, description, location, channel, phone_number)
        VALUES ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326), $5, $6)
        RETURNING id, hazard_type, description, ST_Y(location) AS lat, ST_X(location) AS lng, labels, channel, reported_at
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, hazard_type, description, lng, lat, channel, phone_number)
        return dict(row)

    async def update_labels(self, report_id: UUID, labels: list[str]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE community_reports SET labels = $2 WHERE id = $1", report_id, labels)

    async def heatmap(self, days: int) -> dict[str, Any]:
        sql = """
        -- Intensity was hardcoded to 1, which made leaflet.heat render every
        -- report identically. It now decays with age across the requested
        -- window, so a cluster reported in the last hours burns hotter than one
        -- from the edge of the window.
        SELECT jsonb_build_object(
          'type', 'FeatureCollection',
          'features', COALESCE(jsonb_agg(jsonb_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(location)::jsonb,
            'properties', jsonb_build_object(
              'hazard_type', hazard_type,
              'reported_at', reported_at,
              'intensity', ROUND(GREATEST(
                0.2,
                1.0 - (EXTRACT(EPOCH FROM (NOW() - reported_at)) / NULLIF(EXTRACT(EPOCH FROM make_interval(days => $1)), 0))
              )::numeric, 2)
            )
          )), '[]'::jsonb)
        )
        FROM community_reports
        WHERE reported_at >= NOW() - make_interval(days => $1)
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql, days)
        return json.loads(value) if isinstance(value, str) else value
