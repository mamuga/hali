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

HALI is intended to run on macOS and Linux. Windows is not a target for the local scripts because the backend Nx targets use POSIX-style environment variables such as `PYTHONPATH=src`.

Prerequisites:

- Node.js 22 LTS and npm
- Python 3.12 or 3.13
- Poetry 2.x available as `poetry` on your shell `PATH`
- Docker Desktop on macOS, or Docker Engine with the Compose plugin on Linux

Install prerequisites on macOS with Homebrew:

```bash
brew install node@22 python@3.12 poetry
brew link node@22
```

Install prerequisites on Ubuntu/Linux:

```bash
# Install Node 22 with your preferred Node manager, for example nvm:
nvm install 22
nvm use 22

# Install Poetry after Python is available:
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

Clone the private repository. Use SSH if your GitHub key is configured, otherwise use HTTPS:

```bash
git clone git@github.com:mamuga/hali.git
# or: git clone https://github.com/mamuga/hali.git
cd hali
```

Install dependencies:

```bash
npm install
cd apps/backend
poetry env use python3.12 || poetry env use python3
poetry install
cd ../..
```

Create your local environment file:

```bash
cp .env.example .env
```

For local Docker, the default database URLs in `.env.example` work as-is. For Railway, replace the three database URLs with the public TCP proxy URL from the Railway `PostGIS` service variables. Keep `DATABASE_URL` on the `postgresql+asyncpg://` scheme and use raw `postgresql://` for `DATABASE_URL_RAW` and `MIGRATION_DATABASE_URL`.

Start PostGIS:

```bash
docker compose up -d postgres
docker compose ps
```

The checked-in compose file maps PostGIS to host port `5433` to avoid collisions with a local Postgres on `5432`. The matching local URLs are already in `.env.example`:

```env
DATABASE_URL=postgresql+asyncpg://hali:hali@localhost:5433/hali
DATABASE_URL_RAW=postgresql://hali:hali@localhost:5433/hali
MIGRATION_DATABASE_URL=postgresql://hali:hali@localhost:5433/hali
```

Run migrations:

```bash
npm run backend:migrate
```

Run the backend and frontend in separate terminals:

```bash
npm run backend:serve
```

```bash
npm run frontend:serve
```

Open the frontend at `http://localhost:5173`. The API runs at `http://localhost:8000`; quick checks are:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/api/alerts
```

When the backend is connected to PostGIS, `/health` returns `status`, `db`, `postgres_version`, and `postgis_version`. In test mode or before the database pool is initialized, it remains a shallow liveness response with `{"status":"ok"}`.

Run verification checks:

```bash
npm run verify
```

Troubleshooting:

- If `poetry` is not found, add Poetry to your shell PATH and reopen the terminal. On Linux this is usually `export PATH="$HOME/.local/bin:$PATH"`.
- If Docker says port `5433` is already in use, change the host side in `docker-compose.yml`, then update `DATABASE_URL` and `MIGRATION_DATABASE_URL` in `.env` to match.
- If `poetry env use python3.12` fails on macOS, install Python 3.12 with Homebrew or pyenv, then rerun `poetry install`.

## Ingestion and AI

GDACS is enabled by default and ingests the East Africa bounding box. CHIRPS, GFS, GloFAS, and ICPAC adapters are disabled by default and fail clearly if enabled without source-specific endpoint or credential configuration. Claude translation, action-card generation, and report labels run only when `ANTHROPIC_API_KEY` is configured; otherwise reports store empty labels and adapters/tests still pass.

## USSD

Configure Africa's Talking to POST to `/ussd`. The flow uses `CON` for continuing menus and `END` for terminal responses.

## Data Boundaries

`sql/migrations/003_seed_igad_countries.sql` uses bounding-box polygons for Kenya, Ethiopia, Somalia, Uganda, Djibouti, Eritrea, Sudan, and South Sudan. Countries are keyed by ISO2 codes: `KE`, `ET`, `SO`, `UG`, `DJ`, `ER`, `SD`, and `SS`. Replace the bounding boxes with Natural Earth boundaries using `ogr2ogr` as documented in that migration.

## Database Contract

The SQL mirrors in `sql/migrations` are the Railway bootstrap contract. `alerts.geom`, `community_reports.location`, and `countries.geom` are PostGIS geometry columns in EPSG:4326. Spatial indexes are named `alerts_geom_idx`, `community_reports_geom_idx`, and `countries_geom_idx`.

`DATABASE_URL` uses the `postgresql+asyncpg://` prefix for application configuration. `DATABASE_URL_RAW` and `MIGRATION_DATABASE_URL` use the raw `postgresql://` prefix for `psql`, Alembic, and other CLI tools.

## Railway

See `infra/railway.md`. Use Railway's `PostGIS` template, not the default plain `Postgres` template. Railway's default PostgreSQL image does not include the PostGIS system extension files, so `CREATE EXTENSION postgis` fails there.

The current Railway database layer is configured in workspace `Ronza`, project `chic-exploration`, service `PostGIS`. Run SQL mirrors or Alembic, set required env vars, and deploy backend with `uvicorn hali.main:app --host 0.0.0.0 --port $PORT`. Build frontend with `VITE_API_URL` pointing to the backend.

## Database Setup Status

The Railway database layer has been provisioned and verified against the `PostGIS` service. Migrations `001_enable_postgis.sql`, `002_create_tables.sql`, and `003_seed_igad_countries.sql` have run successfully. The database contains the six HALI tables, the three expected GiST spatial indexes, eight IGAD country seed rows, and one manual flood test alert used to verify `/api/alerts/geojson`.

Next layer: data ingestion, starting with the GDACS fetcher.

## Known Limitations

External live ingestion quality depends on GDACS RSS content. Claude, Africa's Talking, and disabled climate/hydrology adapters require real credentials or source details before production use.
