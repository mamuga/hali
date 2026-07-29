-- WorldPop population grid, aggregated to ~5 km cells.
--
-- Replaces the per-alert call to WorldPop's REST API. That pattern cost one
-- network round trip per alert, could not answer a user-drawn polygon at all,
-- and returned nothing when the service was slow — so exposure figures silently
-- went missing exactly when the system was busiest.
--
-- Source rasters are the 1 km UN-adjusted constrained products. At native
-- resolution the eight IGAD countries are several million pixels; aggregating
-- 5x5 blocks brings that to ~100-160k rows, which fits comfortably in Postgres
-- and is far finer than the admin-2 units exposure is usually reported at.

CREATE TABLE IF NOT EXISTS pop_grid (
    id      BIGSERIAL PRIMARY KEY,
    iso2    CHAR(2) NOT NULL,
    geom    geometry(Point, 4326) NOT NULL,
    pop     INTEGER NOT NULL CHECK (pop >= 0),
    year    INTEGER NOT NULL DEFAULT 2020,
    source  TEXT NOT NULL DEFAULT 'worldpop_1km_unadj'
);

CREATE INDEX IF NOT EXISTS pop_grid_geom_idx ON pop_grid USING GIST (geom);

-- Reloads are per country-year: the loader deletes that slice before inserting,
-- so re-running the adapter is idempotent rather than doubling every figure.
CREATE INDEX IF NOT EXISTS pop_grid_iso2_year_idx ON pop_grid (iso2, year);
