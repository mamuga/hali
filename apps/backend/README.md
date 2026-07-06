# HALI Backend

FastAPI service for HALI alerts, community reports, health checks, USSD, ingestion adapters, and AI-assisted translations/action cards.

## Database

Application configuration reads `DATABASE_URL` with the `postgresql+asyncpg://` prefix. The database layer normalizes that value to `postgresql://` before opening the asyncpg pool.

Use `DATABASE_URL_RAW` or `MIGRATION_DATABASE_URL` for CLI tools such as `psql` and Alembic.

The Railway/local bootstrap SQL lives in `../../sql/migrations`:

- `001_enable_postgis.sql`: enables `postgis` and `uuid-ossp`
- `002_create_tables.sql`: creates HALI tables and spatial indexes
- `003_seed_igad_countries.sql`: seeds ISO2 IGAD country bounding boxes
