# Railway Deployment Notes

Provision Railway's `PostGIS` template, not the default plain `Postgres` template. The default PostgreSQL image does not include PostGIS extension files, so `CREATE EXTENSION postgis` fails there. After the `PostGIS` service is deployed, run either SQL mirrors from `sql/migrations` in order or Alembic from `apps/backend` with `poetry run alembic upgrade head`.

Required backend variables: `ENVIRONMENT=production`, `DATABASE_URL`, `DATABASE_URL_RAW`, `MIGRATION_DATABASE_URL`, `CORS_ORIGINS`, `ANTHROPIC_API_KEY` when AI is enabled, Africa's Talking credentials for USSD, and ingestion flags. `DATABASE_URL` must use `postgresql+asyncpg://`; `DATABASE_URL_RAW` and `MIGRATION_DATABASE_URL` must use `postgresql://`.

The database contract uses `alerts.geom`, `community_reports.location`, and `countries.geom` as PostGIS columns in EPSG:4326. IGAD seed countries use ISO2 codes: `KE`, `ET`, `SO`, `UG`, `DJ`, `ER`, `SD`, and `SS`.

Backend start command: `uvicorn hali.main:app --host 0.0.0.0 --port $PORT`.

Frontend deploys as a static build from `npx nx run frontend:build`; set `VITE_API_URL` to the Railway backend URL before building.


## Landing site (`landing` service)

The marketing site in `apps/landing` is a third Railway service, built from the
repository root with `apps/landing/Dockerfile` (Astro static build → Caddy),
mirroring the `frontend` service.

There is no root `railway.toml` in this repo — the backend and frontend services
are configured through the Railway dashboard, so `landing` follows the same
convention. The one setting it needs is supplied as a service variable rather
than dashboard config, so it is reproducible from the CLI:

```
RAILWAY_DOCKERFILE_PATH=apps/landing/Dockerfile
VITE_APP_URL=https://frontend-production-ba31.up.railway.app
VITE_GITHUB_URL=https://github.com/mamuga/hali
VITE_USSD_CODE=*789#
VITE_DEMO_VIDEO_URL=            # unset — the demo section is omitted until set
VITE_WHATSAPP_NUMBER=           # unset — the WhatsApp chip is omitted until set
```

All `VITE_*` values are read at build time by `apps/landing/src/config.ts` and
inlined into the static HTML, so changing one requires a redeploy, not a restart.

Deployed at `https://landing-production-d6be4.up.railway.app`. This is the URL
to submit to Devpost, not the app URL.

Current verified setup:

- Workspace: `Ronza`
- Project: `chic-exploration`
- Database service: `PostGIS`
- Database: `railway`
- Public TCP proxy host is stored in local `.env`, not committed
- Migrations `001`, `002`, and `003` have completed
- `/health` and `/api/alerts/geojson` have been verified against Railway PostGIS
