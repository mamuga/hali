"""PostGIS spatial analysis queries backing /api/spatial/*."""
from __future__ import annotations

import json
from typing import Any

import asyncpg

# Severity → numeric weight used by the compound risk score.
SEVERITY_WEIGHT_SQL = "CASE a.severity WHEN 'red' THEN 3 WHEN 'orange' THEN 2 ELSE 1 END"

# No generalised boundary dataset contains every coastal point: Mombasa Island
# lies ~1 km outside Natural Earth's Kenya polygon even at full 1:10m detail.
# Resolving to the nearest country within this distance beats telling someone in
# Mombasa that they are in no country at all.
COASTAL_TOLERANCE_METRES = 5000


def _as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


class SpatialRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def compound_risk(self) -> dict[str, Any]:
        """Compound risk score per IGAD member state as a GeoJSON FeatureCollection.

        Combines alert severity, the land area each alert covers inside the
        country, and recent community report density.

        Deviates from the spec's draft SQL in one way that matters: that query
        grouped by alert, emitting one row per alert-country pair, so a country
        with three active alerts produced three overlapping choropleth features.
        This aggregates to exactly one feature per country and sums the
        per-alert contributions instead.
        """
        sql = f"""
        WITH active_alerts AS (
            SELECT id, hazard_type, severity, geom
            FROM alerts a
            WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
        ),
        alert_exposure AS (
            SELECT
                c.iso2,
                c.name AS country_name,
                a.hazard_type,
                {SEVERITY_WEIGHT_SQL} AS sev_weight,
                ST_Area(ST_Intersection(a.geom, c.geom)::geography) / 1e6 AS overlap_km2
            FROM active_alerts a
            JOIN countries c ON ST_Intersects(a.geom, c.geom)
        ),
        per_country AS (
            SELECT
                iso2,
                country_name,
                SUM(sev_weight * overlap_km2) AS weighted_exposure,
                SUM(overlap_km2) AS overlap_km2,
                COUNT(*) AS alert_count,
                MAX(sev_weight) AS max_sev_weight,
                (array_agg(hazard_type ORDER BY sev_weight DESC, overlap_km2 DESC))[1] AS dominant_hazard
            FROM alert_exposure
            GROUP BY iso2, country_name
        ),
        report_density AS (
            SELECT
                c.iso2,
                COUNT(cr.id)::float AS report_count,
                COUNT(cr.id)::float / NULLIF(ST_Area(c.geom::geography) / 1e10, 0) AS density
            FROM countries c
            LEFT JOIN community_reports cr
                ON ST_Intersects(cr.location, c.geom)
                AND cr.reported_at > NOW() - INTERVAL '14 days'
            GROUP BY c.iso2, c.geom
        )
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(feature ORDER BY score DESC), '[]'::jsonb)
        )
        FROM (
            SELECT
                ROUND((pc.weighted_exposure * (1 + COALESCE(rd.density, 0) * 100))::numeric, 2) AS score,
                jsonb_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(c.geom)::jsonb,
                    'properties', jsonb_build_object(
                        'iso2', pc.iso2,
                        'country', pc.country_name,
                        'compound_risk_score', ROUND((pc.weighted_exposure * (1 + COALESCE(rd.density, 0) * 100))::numeric, 2),
                        'dominant_hazard', pc.dominant_hazard,
                        'alert_count', pc.alert_count,
                        'max_severity', CASE pc.max_sev_weight WHEN 3 THEN 'red' WHEN 2 THEN 'orange' ELSE 'green' END,
                        'overlap_km2', ROUND(pc.overlap_km2::numeric, 1),
                        'community_reports_14d', COALESCE(rd.report_count, 0)
                    )
                ) AS feature
            FROM per_country pc
            JOIN countries c ON c.iso2 = pc.iso2
            LEFT JOIN report_density rd ON rd.iso2 = pc.iso2
        ) ranked
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql)
        return _as_dict(value)

    async def emerging_hotspots(self) -> dict[str, Any]:
        """Latest stored DBSCAN hotspots as a GeoJSON FeatureCollection."""
        sql = """
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(location)::jsonb,
                'properties', jsonb_build_object(
                    'id', id::text,
                    'report_count', report_count,
                    'dominant_hazard', dominant_hazard,
                    'confidence', confidence,
                    'status', 'UNCONFIRMED — no official alert',
                    'first_reported', first_reported,
                    'detected_at', detected_at
                )
            ) ORDER BY report_count DESC), '[]'::jsonb)
        )
        FROM emerging_hotspots
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql)
        return _as_dict(value)

    async def analyse(self, lat: float, lng: float, lang: str) -> dict[str, Any]:
        """Location intelligence report for a single map click.

        Three queries on one connection rather than the spec's single joined
        statement: that version inner-joined `countries`, so clicking anywhere
        outside an IGAD member state (the sea, or a neighbouring country)
        returned nothing at all instead of the nearby-alert context.
        """
        alerts_sql = """
        SELECT
            a.id::text,
            a.hazard_type,
            a.severity,
            COALESCE(t.headline, en.headline, initcap(a.hazard_type) || ' alert') AS headline,
            ROUND((ST_Distance(a.geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography) / 1000)::numeric, 1) AS dist_km,
            a.valid_to,
            a.population_exposed
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $3
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
          AND ST_DWithin(a.geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 500000)
        ORDER BY dist_km ASC
        LIMIT 5
        """
        context_sql = f"""
        SELECT
            (
                SELECT c.name FROM countries c
                WHERE ST_DWithin(c.geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, {COASTAL_TOLERANCE_METRES})
                ORDER BY c.geom <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)
                LIMIT 1
            ) AS country,
            (
                SELECT COUNT(*) FROM community_reports cr
                WHERE ST_DWithin(cr.location::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 100000)
                  AND cr.reported_at > NOW() - INTERVAL '7 days'
            ) AS nearby_reports_7d,
            (
                SELECT COUNT(*) FROM emerging_hotspots eh
                WHERE ST_DWithin(eh.location::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 100000)
            ) AS emerging_hotspots_nearby
        """
        # Powers the "3x flood, 2x road blocked" breakdown in the side panel.
        labels_sql = """
        SELECT label, COUNT(*) AS count
        FROM community_reports cr, unnest(
            CASE WHEN cardinality(cr.labels) > 0 THEN cr.labels ELSE ARRAY[cr.hazard_type] END
        ) AS label
        WHERE ST_DWithin(cr.location::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 100000)
          AND cr.reported_at > NOW() - INTERVAL '7 days'
        GROUP BY label
        ORDER BY count DESC, label
        LIMIT 10
        """
        async with self.pool.acquire() as conn:
            alert_rows = await conn.fetch(alerts_sql, lat, lng, lang)
            context = await conn.fetchrow(context_sql, lat, lng)
            label_rows = await conn.fetch(labels_sql, lat, lng)

        return {
            "location": {"lat": lat, "lng": lng},
            "country": context["country"],
            "nearest_alerts": [
                {
                    "id": row["id"],
                    "hazard_type": row["hazard_type"],
                    "severity": row["severity"],
                    "headline": row["headline"],
                    "dist_km": float(row["dist_km"]),
                    "valid_to": row["valid_to"],
                    "population_exposed": row["population_exposed"],
                }
                for row in alert_rows
            ],
            "nearby_reports_7d": context["nearby_reports_7d"],
            "report_breakdown": [{"label": row["label"], "count": row["count"]} for row in label_rows],
            "emerging_hotspots_nearby": context["emerging_hotspots_nearby"],
        }
