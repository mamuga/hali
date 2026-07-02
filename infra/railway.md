# Railway Deployment Notes

Provision Railway Postgres, enable PostGIS with `CREATE EXTENSION IF NOT EXISTS postgis;`, then run either SQL mirrors from `sql/migrations` in order or Alembic from `apps/backend` with `poetry run alembic upgrade head`.

Required backend variables: `ENVIRONMENT=production`, `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `CORS_ORIGINS`, `ANTHROPIC_API_KEY` when AI is enabled, Africa's Talking credentials for USSD, and ingestion flags. Backend start command: `uvicorn hali.main:app --host 0.0.0.0 --port $PORT`.

Frontend deploys as a static build from `npx nx run frontend:build`; set `VITE_API_URL` to the Railway backend URL before building.
