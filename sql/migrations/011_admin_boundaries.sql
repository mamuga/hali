-- OCHA Common Operational Dataset administrative boundaries.
--
-- HALI's alert geometries came from grid cells and point buffers, so a drought
-- covering Ethiopia, Kenya and Somalia rendered as a 0.25-degree square. The
-- hazards that actually matter here are reported per administrative unit —
-- "Kilifi is at 41% of normal rainfall while Bomet is at 142%" — and that only
-- reads as an alert if we can draw Kilifi.
--
-- P-codes are the join key. HDX HAPI publishes rainfall, food security and
-- conflict keyed on the same admin2 P-codes these boundaries carry, so an
-- indicator row becomes an alert polygon with a single lookup. Verified: all 73
-- Kenyan admin2 codes returned by HAPI match a COD-AB polygon exactly.

CREATE TABLE IF NOT EXISTS admin_boundaries (
    pcode       TEXT PRIMARY KEY,
    iso2        CHAR(2) NOT NULL,
    level       SMALLINT NOT NULL CHECK (level BETWEEN 0 AND 3),
    name        TEXT NOT NULL,
    parent_name TEXT,
    parent_pcode TEXT,
    geom        geometry(MultiPolygon, 4326) NOT NULL,
    source      TEXT NOT NULL DEFAULT 'cod_ab',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS admin_boundaries_geom_idx ON admin_boundaries USING GIST (geom);
CREATE INDEX IF NOT EXISTS admin_boundaries_iso2_level_idx ON admin_boundaries (iso2, level);
