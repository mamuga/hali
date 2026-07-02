# HALI

HALI is a hackathon-speed production-shaped early warning system for East Africa. It combines FastAPI, PostGIS, Claude processing, USSD, and a React/Vite PWA for alert feeds, maps, action cards, and community reports.

## Resolved Tooling Versions

| Tool | Version |
| --- | --- |
| Node | 22.19.0 |
| npm | 11.6.2 |
| Python local | 3.12.3 |
| Python production target | 3.13.x |
| Poetry | 2.4.1 |
| Nx / @nx/react / @nx/vite / @nx/vitest | 23.0.1 |
| @nxlv/python | 22.2.1 |
| React | 19.2.7 |
| Vite | 8.1.3 |
| FastAPI | 0.139.0 |
| Uvicorn | 0.49.0 |
| asyncpg | 0.31.0 |
| anthropic | 0.116.0 |
| Alembic | 1.18.5 |

Python 3.13 was requested but is not installed on this machine, so local verification used Python 3.12.3 with code constrained to `>=3.12,<3.14`.

## Features

Languages: `sw`, `so`, `am`, `om`, `ar`, `en`. Livelihoods: `farmer`, `pastoralist`, `fisherfolk`, `urban`. Hazards: `flood`, `drought`, `locust`, `cyclone`, `health`, `other`. Severities: `green`, `orange`, `red`.

Backend endpoints: `/`, `/health`, `/ready`, `/api/alerts`, `/api/alerts/geojson`, `/api/alerts/{alert_id}/action-card`, `/api/reports`, `/api/reports/heatmap`, `/ussd`.

## Local Setup

Prerequisites:

- Node.js 22 LTS and npm
- Python 3.12 or 3.13
- Poetry 2.x
- Docker with Compose

Clone and install dependencies:

```bash
git clone git@github.com:mamuga/hali.git
cd hali
npm install
cd apps/backend
poetry install
cd ../..
```

Create your local environment file:

```bash
cp .env.example .env
```

Start PostGIS:

```bash
docker compose up -d postgres
docker compose ps
```

The checked-in compose file maps PostGIS to host port `5433` to avoid collisions with a local Postgres on `5432`. The matching local URLs are already in `.env.example`:

```env
DATABASE_URL=postgresql+asyncpg://hali:hali@localhost:5433/hali
MIGRATION_DATABASE_URL=postgresql://hali:hali@localhost:5433/hali
```

Run migrations:

```bash
cd apps/backend
poetry run alembic upgrade head
cd ../..
```

Run the backend and frontend in separate terminals:

```bash
npx nx run backend:serve
```

```bash
npx nx run frontend:serve
```

Open the frontend at `http://localhost:5173`. The API runs at `http://localhost:8000`; quick checks are:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/alerts
```

Run verification checks:

```bash
npx nx run backend:lint
npx nx run backend:typecheck
npx nx run backend:test
npx nx run frontend:build
npx nx run-many -t build --all
```

## Ingestion and AI

GDACS is enabled by default and ingests the East Africa bounding box. CHIRPS, GFS, GloFAS, and ICPAC adapters are disabled by default and fail clearly if enabled without source-specific endpoint or credential configuration. Claude translation, action-card generation, and report labels run only when `ANTHROPIC_API_KEY` is configured; otherwise reports store empty labels and adapters/tests still pass.

## USSD

Configure Africa's Talking to POST to `/ussd`. The flow uses `CON` for continuing menus and `END` for terminal responses.

## Data Boundaries

`sql/migrations/003_seed_igad_countries.sql` uses bounding-box polygons for Kenya, Ethiopia, Somalia, Uganda, Djibouti, Eritrea, Sudan, and South Sudan. Replace them with Natural Earth boundaries using `ogr2ogr` as documented in that migration.

## Railway

See `infra/railway.md`. Use Railway Postgres with PostGIS, run SQL mirrors or Alembic, set required env vars, and deploy backend with `uvicorn hali.main:app --host 0.0.0.0 --port $PORT`. Build frontend with `VITE_API_URL` pointing to the backend.

## Known Limitations

External live ingestion quality depends on GDACS RSS content. Claude, Africa's Talking, and disabled climate/hydrology adapters require real credentials or source details before production use.
