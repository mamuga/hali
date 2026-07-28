import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


class AlertRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_alerts(self, lang: str, lat: float | None, lng: float | None, limit: int) -> list[dict[str, Any]]:
        sql = """
        SELECT a.id, a.hazard_type, a.severity, a.affected_countries, a.valid_from, a.valid_to,
               a.population_exposed,
               a.processed_at, a.processed_at > NOW() - INTERVAL '24 hours' AS is_new,
               (t.headline IS NOT NULL) AS has_translation,
               COALESCE(t.headline, en.headline, initcap(a.hazard_type)) AS headline,
               COALESCE(t.body, en.body, 'Alert for ' || array_to_string(a.affected_countries, ', ')) AS body,
               COALESCE(t.audio_url, en.audio_url) AS audio_url
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $1
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
          AND ($2::float8 IS NULL OR $3::float8 IS NULL OR ST_Contains(a.geom, ST_SetSRID(ST_MakePoint($3, $2), 4326)))
        ORDER BY a.severity DESC, a.processed_at DESC
        LIMIT $4
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, lang, lat, lng, limit)
        return [dict(row) for row in rows]

    async def geojson(
        self,
        bbox: tuple[float, float, float, float],
        lang: str,
        severity: str | None,
        hazard: str | None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict[str, Any]:
        # With no date range this serves the live map, so expired alerts are
        # excluded. With a range it serves temporal playback, where past alerts
        # are exactly what is being asked for — hence the CASE rather than an
        # unconditional valid_to filter.
        sql = """
        SELECT jsonb_build_object(
          'type', 'FeatureCollection',
          'features', COALESCE(jsonb_agg(jsonb_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(a.geom)::jsonb,
            'properties', jsonb_build_object(
              'id', a.id::text,
              'hazard_type', a.hazard_type,
              'severity', a.severity,
              'headline', COALESCE(t.headline, en.headline, initcap(a.hazard_type)),
              'body', COALESCE(t.body, en.body, ''),
              'affected_countries', a.affected_countries,
              'population_exposed', a.population_exposed,
              'valid_from', a.valid_from,
              'valid_to', a.valid_to
            )
          )), '[]'::jsonb)
        ) AS geojson
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $5
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE ST_Intersects(a.geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))
          AND ($6::text IS NULL OR a.severity = $6)
          AND ($7::text IS NULL OR a.hazard_type = $7)
          AND CASE
                WHEN $8::timestamptz IS NULL AND $9::timestamptz IS NULL
                  THEN (a.valid_to > NOW() OR a.valid_to IS NULL)
                ELSE (a.valid_from IS NULL OR $9::timestamptz IS NULL OR a.valid_from <= $9::timestamptz)
                     AND (a.valid_to IS NULL OR $8::timestamptz IS NULL OR a.valid_to >= $8::timestamptz)
              END
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql, *bbox, lang, severity, hazard, from_date, to_date)
        return json.loads(value) if isinstance(value, str) else value

    async def latest_for_country(self, iso2: str | None, lang: str) -> dict[str, Any] | None:
        """Most severe active alert, optionally narrowed to one country.

        Severity sorts correctly as plain text here: 'red' > 'orange' > 'green'.
        """
        sql = """
        SELECT a.id, a.hazard_type, a.severity, a.affected_countries, a.valid_to,
               COALESCE(t.headline, en.headline, initcap(a.hazard_type) || ' alert') AS headline,
               COALESCE(t.body, en.body, '') AS body
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $1
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
          AND ($2::text IS NULL OR $2 = ANY(a.affected_countries))
        ORDER BY a.severity DESC, a.processed_at DESC
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, lang, iso2)
        return dict(row) if row else None

    async def translation(self, alert_id: UUID, lang: str) -> dict[str, Any]:
        """Headline/body for one alert, falling back to English then the hazard name."""
        sql = """
        SELECT COALESCE(t.headline, en.headline, initcap(a.hazard_type) || ' alert') AS headline,
               COALESCE(t.body, en.body, '') AS body
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $2
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE a.id = $1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, alert_id, lang)
        return dict(row) if row else {"headline": "Alert", "body": ""}

    async def ussd_alert_view(self, phone_number: str, livelihood: str | None) -> dict[str, Any] | None:
        """Subscriber, their most relevant active alert, and optionally the
        matching action card — in a single round trip.

        USSD sessions die at 3 seconds. Doing this as three sequential queries
        spent the whole budget on network latency alone, so the caller got a
        generic fallback instead of real content.
        """
        sql = """
        WITH sub AS (
            SELECT language, preferred_iso2
            FROM user_subscriptions
            WHERE phone_number = $1
        ),
        pref AS (
            SELECT COALESCE((SELECT language FROM sub), 'en') AS lang,
                   (SELECT preferred_iso2 FROM sub) AS iso2
        )
        SELECT a.id, a.hazard_type, a.severity, a.valid_to,
               p.lang,
               COALESCE(t.headline, en.headline, initcap(a.hazard_type) || ' alert') AS headline,
               COALESCE(
                   (SELECT steps FROM action_cards c WHERE c.alert_id = a.id AND c.livelihood = $2 AND c.language = p.lang),
                   (SELECT steps FROM action_cards c WHERE c.alert_id = a.id AND c.livelihood = $2 AND c.language = 'en')
               ) AS steps
        FROM alerts a
        CROSS JOIN pref p
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = p.lang
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
          AND (p.iso2 IS NULL OR p.iso2 = ANY(a.affected_countries))
        ORDER BY a.severity DESC, a.processed_at DESC
        LIMIT 1
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, phone_number, livelihood)
        return dict(row) if row else None

    async def country_point(self, iso2: str) -> tuple[float, float] | None:
        """A representative interior point for a country, for channels with no GPS."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT ST_Y(ST_PointOnSurface(geom)) AS lat, ST_X(ST_PointOnSurface(geom)) AS lng FROM countries WHERE iso2 = $1",
                iso2,
            )
        return (row["lat"], row["lng"]) if row else None

    async def action_card(self, alert_id: UUID, livelihood: str, lang: str) -> dict[str, Any] | None:
        """Exact livelihood/language match only - no silent language fallback.

        Callers that want a fallback (e.g. to 'en') should query again
        explicitly, so it's visible when a requested language is missing.
        """
        sql = """
        SELECT alert_id, livelihood, language, steps
        FROM action_cards
        WHERE alert_id = $1 AND livelihood = $2 AND language = $3
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, alert_id, livelihood, lang)
        return dict(row) if row else None
