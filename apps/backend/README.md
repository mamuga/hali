# HALI Backend

FastAPI service for HALI alerts, community reports, health checks, USSD, ingestion adapters, and AI-assisted translations/action cards.

## Database

Application configuration reads `DATABASE_URL` with the `postgresql+asyncpg://` prefix. The database layer normalizes that value to `postgresql://` before opening the asyncpg pool.

Use `DATABASE_URL_RAW` or `MIGRATION_DATABASE_URL` for CLI tools such as `psql` and Alembic.

The Railway/local bootstrap SQL lives in `../../sql/migrations`:

- `001_enable_postgis.sql`: enables `postgis` and `uuid-ossp`
- `002_create_tables.sql`: creates HALI tables and spatial indexes
- `003_seed_igad_countries.sql`: seeds ISO2 IGAD country bounding boxes
- `004_spatial_and_subscribers.sql`: adds `alerts.population_exposed`,
  `community_reports.channel`, and the `emerging_hotspots` + `user_subscriptions`
  tables with their GiST indexes

Each Alembic revision executes its SQL mirror, locating it by walking up from the
revision file — so the same revision resolves both in a source checkout
(`apps/backend/alembic/versions/`) and inside the Docker image (`/app/alembic/versions/`).
The image therefore must ship `sql/`; the Dockerfile copies it.

Migrations run automatically on container start via `docker-entrypoint.sh`, before
uvicorn binds. They are fail-closed: a failed migration exits non-zero so the
previous deployment keeps serving rather than an API booting against a schema it
does not match. Set `RUN_MIGRATIONS=false` to skip.
