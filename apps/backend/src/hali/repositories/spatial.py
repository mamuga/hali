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

# Douglas-Peucker tolerance for the choropleth outlines, in degrees (~2 km).
# Matches the boundary layer so the two overlay without visible seams.
CHOROPLETH_TOLERANCE = 0.02


def _as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


def _as_list(value: Any) -> list[dict[str, Any]]:
    return json.loads(value) if isinstance(value, str) else (value or [])


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
        This aggregates to exactly one feature per country.

        AREA IS UNIONED, NOT SUMMED. The previous version summed each alert's
        intersection with the country, which double-counts every place covered by
        more than one alert. At 537 active alerts that stopped being a rounding
        error: Kenya reported 2,708,468 km² of "overlap" against a true national
        area of 585,764 km² — 4.6x the country. The score built on it ran to
        51,688,807, a number with no unit and no ceiling, so the choropleth was
        ranking countries by how many overlapping polygons a publisher happened
        to draw rather than by how much ground is actually at risk.

        Alerts are unioned into disjoint severity bands instead — red first, then
        the orange that is not already red, then green that is neither — so every
        square kilometre is counted exactly once, at its worst severity. That
        makes the score a bounded 0-100: the severity-weighted share of national
        land under alert, where 100 means the entire country is under a red one.
        """
        sql = f"""
        WITH active_alerts AS (
            SELECT hazard_type, severity, geom,
                   {SEVERITY_WEIGHT_SQL} AS sev_weight
            FROM alerts a
            WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
              -- IFRC appeals and WHO outbreak notices carry the whole national
              -- outline, so counting their area makes every country 100% covered
              -- and the choropleth a flat colour. They are advisories about a
              -- country, not a measured hazard footprint within it. Their alert
              -- count is still reported below.
              AND a.source NOT IN ('ifrc', 'who')
        ),
        -- One clipped, unioned footprint per country and severity. ST_Union here
        -- is the whole point: it dissolves the stack of overlapping district
        -- polygons into the actual ground they cover.
        by_severity AS (
            SELECT
                c.iso2,
                a.sev_weight,
                ST_Union(ST_Intersection(a.geom, c.geom)) AS geom
            FROM active_alerts a
            JOIN countries c ON ST_Intersects(a.geom, c.geom)
            GROUP BY c.iso2, a.sev_weight
        ),
        -- Subtract the higher bands so the three areas are disjoint.
        bands AS (
            SELECT
                iso2,
                sev_weight,
                ST_Area(
                    COALESCE(
                        ST_Difference(
                            geom,
                            (SELECT ST_Union(h.geom) FROM by_severity h
                             WHERE h.iso2 = by_severity.iso2 AND h.sev_weight > by_severity.sev_weight)
                        ),
                        geom
                    )::geography
                ) / 1e6 AS band_km2
            FROM by_severity
        ),
        per_country AS (
            SELECT
                b.iso2,
                SUM(b.band_km2) AS alert_area_km2,
                SUM(b.sev_weight * b.band_km2) AS weighted_area_km2,
                MAX(b.sev_weight) AS max_sev_weight
            FROM bands b
            GROUP BY b.iso2
        ),
        -- Counts and dominant hazard are per-alert facts, not areas, so they are
        -- unaffected by the union and stay on the raw join.
        alert_facts AS (
            SELECT
                c.iso2,
                COUNT(*) AS alert_count,
                COUNT(*) FILTER (WHERE a.source IN ('ifrc', 'who')) AS national_advisories,
                (array_agg(a.hazard_type ORDER BY
                           CASE a.severity WHEN 'red' THEN 3 WHEN 'orange' THEN 2 ELSE 1 END DESC,
                           ST_Area(ST_Intersection(a.geom, c.geom)) DESC))[1] AS dominant_hazard
            FROM alerts a
            JOIN countries c ON ST_Intersects(a.geom, c.geom)
            WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
            GROUP BY c.iso2
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
                LEAST(
                    100.0,
                    (100.0 * pc.weighted_area_km2
                        / NULLIF(3 * ST_Area(c.geom::geography) / 1e6, 0))
                    * (1 + COALESCE(rd.density, 0) * 0.1)
                ) AS score,
                jsonb_build_object(
                    'type', 'Feature',
                    -- Same simplification the boundary layer uses. The raw 1:10m
                    -- outlines made this response 123 KB for eight polygons; the
                    -- difference is invisible at the map's minimum zoom.
                    'geometry', ST_AsGeoJSON(
                        ST_SimplifyPreserveTopology(c.geom, {CHOROPLETH_TOLERANCE})
                    )::jsonb,
                    'properties', jsonb_build_object(
                        'iso2', pc.iso2,
                        'country', c.name,
                        'compound_risk_score', ROUND(LEAST(
                            100.0,
                            (100.0 * pc.weighted_area_km2
                                / NULLIF(3 * ST_Area(c.geom::geography) / 1e6, 0))
                            * (1 + COALESCE(rd.density, 0) * 0.1)
                        )::numeric, 1),
                        'dominant_hazard', af.dominant_hazard,
                        'alert_count', af.alert_count,
                        'national_advisories', af.national_advisories,
                        'max_severity', CASE pc.max_sev_weight WHEN 3 THEN 'red' WHEN 2 THEN 'orange' ELSE 'green' END,
                        'alert_area_km2', ROUND(pc.alert_area_km2::numeric, 1),
                        'country_area_km2', ROUND((ST_Area(c.geom::geography) / 1e6)::numeric, 1),
                        'alert_area_pct', ROUND((100.0 * pc.alert_area_km2
                            / NULLIF(ST_Area(c.geom::geography) / 1e6, 0))::numeric, 1),
                        'community_reports_14d', COALESCE(rd.report_count, 0)
                    )
                ) AS feature
            FROM per_country pc
            JOIN countries c ON c.iso2 = pc.iso2
            JOIN alert_facts af ON af.iso2 = pc.iso2
            LEFT JOIN report_density rd ON rd.iso2 = pc.iso2
        ) ranked
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql)
        return _as_dict(value)

    async def countries_geojson(self, tolerance: float) -> dict[str, Any]:
        """IGAD member state boundaries, simplified for the map.

        The stored geometry is Natural Earth 1:10m — 5,636 vertices and ~118 KB
        of GeoJSON, which is far more than a phone on 2G should download to draw
        an outline. At the default tolerance it is ~28 KB, and the difference is
        invisible at the zoom levels this map allows (min zoom 4).

        ST_SimplifyPreserveTopology rather than ST_Simplify: the latter can
        produce self-intersections and drop small rings, which would tear holes
        in the outside-IGAD mask that uses these polygons.
        """
        sql = """
        SELECT jsonb_build_object(
            'type', 'FeatureCollection',
            'features', COALESCE(jsonb_agg(jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, $1))::jsonb,
                'properties', jsonb_build_object('iso2', iso2, 'name', name)
            ) ORDER BY iso2), '[]'::jsonb)
        )
        FROM countries
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(sql, tolerance)
        return _as_dict(value)

    async def aoi_area_km2(self, geojson: str) -> float | None:
        """Area of a drawn shape, touching no other table.

        Deliberately separate from query_polygon so an oversized area can be
        rejected before any spatial join runs. Returns None if PostGIS cannot
        make sense of the geometry at all.
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT ROUND(
                    (ST_Area(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($1), 4326))::geography)
                     / 1e6)::numeric, 1)
                """,
                geojson,
            )
        return float(value) if value is not None else None

    async def query_polygon(self, geojson: str, lang: str) -> dict[str, Any]:
        """Everything HALI knows inside a user-drawn area of interest.

        The geometry is parsed once into a CTE rather than re-parsed in every
        subquery: ST_GeomFromGeoJSON on a hand-drawn ring is cheap, but the
        spec's draft repeated it five times in one statement, and PostgreSQL
        will not deduplicate the call for it.

        ST_MakeValid because a hand-drawn shape self-intersects easily — a
        bowtie polygon makes ST_Intersects raise rather than return false.
        """
        sql = """
        WITH aoi AS (
            SELECT ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($1), 4326)) AS geom
        ),
        aoi_area AS (
            SELECT ROUND((ST_Area(geom::geography) / 1e6)::numeric, 1) AS area_km2 FROM aoi
        ),
        matched_alerts AS (
            SELECT
                a.id::text AS id,
                a.hazard_type,
                a.severity,
                COALESCE(t.headline, en.headline, initcap(a.hazard_type) || ' alert') AS headline,
                a.valid_to,
                a.population_exposed,
                ROUND((ST_Area(ST_Intersection(a.geom, aoi.geom)::geography) / 1e6)::numeric, 1) AS overlap_km2
            FROM alerts a
            CROSS JOIN aoi
            LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $2
            LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
            WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
              AND ST_Intersects(a.geom, aoi.geom)
            ORDER BY CASE a.severity WHEN 'red' THEN 0 WHEN 'orange' THEN 1 ELSE 2 END,
                     overlap_km2 DESC
            LIMIT 50
        ),
        matched_reports AS (
            SELECT
                COUNT(*) AS report_count,
                COALESCE(ARRAY_AGG(DISTINCT cr.hazard_type), '{}') AS report_hazards
            FROM community_reports cr
            CROSS JOIN aoi
            WHERE cr.reported_at > NOW() - INTERVAL '14 days'
              AND ST_Intersects(cr.location, aoi.geom)
        ),
        matched_hotspots AS (
            SELECT COUNT(*) AS hotspot_count
            FROM emerging_hotspots eh
            CROSS JOIN aoi
            WHERE ST_Intersects(eh.location, aoi.geom)
        ),
        -- Counted separately from matched_alerts, which is capped at 50 for the
        -- panel. A user drawing an AOI over the Horn intersects several hundred
        -- FEWS NET districts; returning 50 with no total made the panel report
        -- "50 alerts" for an area holding 300, which understates the situation
        -- precisely where it is worst.
        alert_total AS (
            SELECT COUNT(*) AS alert_count
            FROM alerts a
            CROSS JOIN aoi
            WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
              AND ST_Intersects(a.geom, aoi.geom)
        )
        SELECT
            (SELECT area_km2 FROM aoi_area) AS area_km2,
            (SELECT alert_count FROM alert_total) AS alert_count,
            (SELECT report_count FROM matched_reports) AS report_count,
            (SELECT report_hazards FROM matched_reports) AS report_hazards,
            (SELECT hotspot_count FROM matched_hotspots) AS emerging_hotspots,
            COALESCE(
                (SELECT jsonb_agg(to_jsonb(matched_alerts)) FROM matched_alerts),
                '[]'::jsonb
            ) AS alerts
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(sql, geojson, lang)
            population = await self._population_in_aoi(conn, geojson)

        alerts = _as_list(row["alerts"])
        return {
            "area_km2": float(row["area_km2"] or 0.0),
            "alert_count": row["alert_count"] or 0,
            "alerts": [
                {
                    "id": a["id"],
                    "hazard_type": a["hazard_type"],
                    "severity": a["severity"],
                    "headline": a["headline"],
                    "valid_to": a["valid_to"],
                    "population_exposed": a["population_exposed"],
                    "overlap_km2": float(a["overlap_km2"] or 0.0),
                }
                for a in alerts
            ],
            "report_count": row["report_count"] or 0,
            "report_hazards": list(row["report_hazards"] or []),
            "emerging_hotspots": row["emerging_hotspots"] or 0,
            "population_estimate": population,
        }

    @staticmethod
    async def _population_in_aoi(conn: asyncpg.Connection, geojson: str) -> int | None:
        """Sum the population grid inside the area, if one has been ingested.

        Returns None rather than 0 when `pop_grid` does not exist yet (it lands
        in Phase 5) — "we have not measured this" and "nobody lives here" must
        not look the same to the caller.
        """
        exists = await conn.fetchval("SELECT to_regclass('public.pop_grid') IS NOT NULL")
        if not exists:
            return None
        return await conn.fetchval(
            """
            SELECT COALESCE(SUM(pop), 0)::bigint
            FROM pop_grid
            WHERE ST_Intersects(geom, ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON($1), 4326)))
            """,
            geojson,
        )

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
            a.population_exposed,
            CASE WHEN a.source IN ('ifrc', 'who') THEN 'national' ELSE 'local' END AS scope
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id = a.id AND t.language = $3
        LEFT JOIN alert_translations en ON en.alert_id = a.id AND en.language = 'en'
        WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
          AND ST_DWithin(a.geom::geography, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, 500000)
        -- Distance alone ranks badly here. A country-scoped advisory carries the
        -- whole national outline, so every click inside Kenya sits at 0.0 km from
        -- all of them and the tie is broken arbitrarily. Clicking Lodwar returned
        -- a Kenya-wide Ebola readiness appeal second and the Turkana drought that
        -- the click was actually about fifth. Subnational alerts are what a point
        -- query is for; national ones stay in the list, just below.
        ORDER BY (a.source IN ('ifrc', 'who')), dist_km ASC, a.severity = 'red' DESC
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
                    "scope": row["scope"],
                }
                for row in alert_rows
            ],
            "nearby_reports_7d": context["nearby_reports_7d"],
            "report_breakdown": [{"label": row["label"], "count": row["count"]} for row in label_rows],
            "emerging_hotspots_nearby": context["emerging_hotspots_nearby"],
        }
