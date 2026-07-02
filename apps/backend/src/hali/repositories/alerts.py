import json
from typing import Any
from uuid import UUID

import asyncpg


class AlertRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_alerts(self, lang: str, lat: float | None, lng: float | None, limit: int) -> list[dict[str, Any]]:
        sql = """
        SELECT a.id, a.hazard_type, a.severity, a.affected_countries, a.valid_from, a.valid_to,
               a.processed_at, a.processed_at > NOW() - INTERVAL '24 hours' AS is_new,
               COALESCE(t.headline, en.headline, initcap(a.hazard_type)) AS headline,
               COALESCE(t.body, en.body, 'Alert for ' || array_to_string(a.affected_countries, ', ')) AS body,
               COALESCE(t.audio_url, en.audio_url) AS audio_url
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $1
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
          AND ($2::float8 IS NULL OR $3::float8 IS NULL OR ST_Contains(a.geometry, ST_SetSRID(ST_MakePoint($3, $2), 4326)))
        ORDER BY a.severity DESC, a.processed_at DESC
        LIMIT $4
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, lang, lat, lng, limit)
        return [dict(row) for row in rows]

    async def geojson(self, bbox: tuple[float, float, float, float], lang: str, severity: str | None, hazard: str | None) -> dict[str, Any]:
        sql = """
        SELECT jsonb_build_object(
          'type', 'FeatureCollection',
          'features', COALESCE(jsonb_agg(jsonb_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(a.geometry)::jsonb,
            'properties', jsonb_build_object(
              'id', a.id::text,
              'hazard_type', a.hazard_type,
              'severity', a.severity,
              'headline', COALESCE(t.headline, en.headline, initcap(a.hazard_type)),
              'body', COALESCE(t.body, en.body, ''),
              'affected_countries', a.affected_countries,
              'valid_from', a.valid_from,
              'valid_to', a.valid_to
            )
          )), '[]'::jsonb)
        ) AS geojson
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $5
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE ST_Intersects(a.geometry, ST_MakeEnvelope($1, $2, $3, $4, 4326))
          AND ($6::text IS NULL OR a.severity = $6)
          AND ($7::text IS NULL OR a.hazard_type = $7)
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql, *bbox, lang, severity, hazard)
        return json.loads(value) if isinstance(value, str) else value

    async def action_card(self, alert_id: UUID, livelihood: str, lang: str) -> dict[str, Any] | None:
        sql = """
        SELECT alert_id, livelihood, language, steps
        FROM action_cards
        WHERE alert_id = $1 AND livelihood = $2 AND language IN ($3, 'en')
        ORDER BY CASE WHEN language = $3 THEN 0 ELSE 1 END
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, alert_id, livelihood, lang)
        return dict(row) if row else None
