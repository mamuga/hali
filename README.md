# HALI

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![CI](https://github.com/mamuga/hali/actions/workflows/deploy.yml/badge.svg)

**Hyper-local early warning for East Africa.** HALI ingests 13 external hazard
and reference sources, translates every alert into 10 languages at a Grade 5
reading level with a multi-model AI ensemble, and delivers it over three
channels — USSD, WhatsApp, and an offline-capable PWA — so reaching a herder
with no smartphone and no data bundle costs nothing extra.

Built for the IGAD Hackathon 2026.

| | |
|---|---|
| **Live app (PWA)** | https://frontend-production-ba31.up.railway.app |
| **Landing page** | https://landing-production-d6be4.up.railway.app |
| **API** | https://backend-production-a6cf.up.railway.app |
| **Demo video** | https://youtu.be/PvYecG0rPMk |

### Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — features and technical specifications
- [docs/SPATIAL_INTELLIGENCE.md](docs/SPATIAL_INTELLIGENCE.md) — spatial capability audit, run against the live production system
- [docs/BRAND.md](docs/BRAND.md) — voice, and the rule that every published figure must cite a source
- [docs/engineering-log/](docs/engineering-log/) — the as-run plans and agent prompts used to build this
- [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)

`apps/landing/src/data/site.ts` is the single source of truth for every count in
this README and on the landing page. Each entry there cites the file it came
from, and the totals are computed from the arrays rather than typed in.

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

**10 languages** — `sw` Swahili, `so` Somali, `am` Amharic, `om` Oromo, `ar` Arabic, `en` English, `fr` French, `ti` Tigrinya, `lg` Luganda, `aa` Afar. Tigrinya, Luganda, and Afar are marked low-resource; the backend may serve English where model quality is weak rather than publish a bad translation.

**7 livelihoods** — `farmer`, `pastoralist`, `agropastoralist`, `fisherfolk`, `urban`, `trader`, `displaced`.

**10 hazard types** — `flood`, `drought`, `locust`, `cyclone`, `heatwave`, `landslide`, `wildfire`, `epidemic`, `health`, `other`. Severities: `green`, `orange`, `red`.

**8 IGAD countries**, resolved to **891 admin2 district polygons** across the 6 with authoritative OCHA COD-AB geometry, with population exposure from an ingested 249,000-cell WorldPop grid.

Backend routers: `health`, `alerts`, `reports`, `spatial`, `subscriptions`, `admin`, `ussd`, `whatsapp` — see `apps/backend/src/hali/routers/`.

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

Clone the repository. Use SSH if your GitHub key is configured, otherwise use HTTPS:

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

## Ingestion pipeline

HALI uses a typed ETL pipeline across **13 external sources** — 10 live and 3 one-shot reference datasets. Each adapter implements `BaseAdapter` (extract → validate → transform → load) and runs in an isolated APScheduler cron job so one failure never blocks others.

`status` below is the shipped default, not an aspiration: **on** is enabled in `config.py` and scheduled, **off** means the adapter is built and tested but its flag defaults to false, **loaded** means a one-shot reference ingest already present in the database.

### Sources

| Source | Kind | Auth | Schedule | Status | Signal |
|---|---|---|---|---|---|
| FEWS NET IPC | condition | None | Weekly, Mon 06:45 UTC | ✅ on | IPC food insecurity phase classification |
| HDX HAPI | condition | Email in `HAPI_EMAIL` | Daily 07:10 UTC | ✅ on | Dekadal rainfall anomaly per admin2 district |
| GDACS | event | None — public | Daily 06:00 UTC | ✅ on | Flood, drought, cyclone, wildfire events |
| IFRC GO appeals | event | None | Daily 07:25 UTC | ✅ on | Named emergency responses, including locust |
| WHO disease outbreak news | event | None | Daily 07:25 UTC | ✅ on | Epidemic events no satellite sees |
| ICPAC GeoPortal WMS | map layer | None | Live tiles, per map view | ✅ on | 5 hazard layers rendered over HALI alert zones |
| CHIRPS | physical model | None — anonymous FTP | Daily 07:00 UTC | ⚫ `ENABLE_CHIRPS=true` | Daily rainfall anomaly GeoTIFF |
| NOAA GFS | physical model | None — public NOAA | Daily 06:15 UTC | ⚫ `ENABLE_GFS=true` | 24h extreme rainfall forecast |
| GloFAS | physical model | Free CDS key required | Daily 06:30 UTC | ⚫ `ENABLE_GLOFAS=true` | River discharge flood forecast, GRIB2 |
| ICPAC digilib SPI | physical model | None — open data | Daily 07:30 UTC | ⚫ `ENABLE_ICPAC=true` | Standardised precipitation index, NetCDF |
| WorldPop population grid | reference | None | One-shot, migration 010 | 📦 loaded | 1 km 2020 UN-adjusted grid, 249,000 cells, 289,931,311 people |
| OCHA COD-AB | reference | None | One-shot, migration 011 | 📦 loaded | 891 admin2 district polygons across 6 countries |
| Natural Earth | reference | None | One-shot, migration 006 | 📦 loaded | 1:10m country boundaries for the 8 IGAD states |

GloFAS and the ICPAC digilib SPI adapter are off by default. ICPAC data still reaches the map regardless: its GeoPortal WMS layers render live inside HALI, which is the stronger integration.

To enable CHIRPS, GFS, and ICPAC SPI (no credentials needed):

```env
ENABLE_CHIRPS=true
ENABLE_GFS=true
ENABLE_ICPAC=true
```

GloFAS requires a free account at https://cds.climate.copernicus.eu. Set `ENABLE_GLOFAS=true` and `GLOFAS_CDS_API_KEY=your-key`.

### ETL design principles

- **Idempotent**: `dedup_hash` unique constraint — safe to re-run anytime
- **Dead-letter tracking**: every raw record has `status` (pending → processed | failed)
- **Source isolation**: one adapter failure never blocks others
- **Boundary validation**: Pydantic models at the extract→transform edge
- **Retry with backoff**: `tenacity` on all HTTP/FTP calls
- **Structured logging**: `structlog` JSON on every pipeline step
- **Replay**: `raw_ingestion` stores full raw payload for reprocessing

### Trigger ingestion manually

```bash
# All enabled sources
curl -X POST http://localhost:8000/api/admin/trigger-ingest

# Single source
curl -X POST "http://localhost:8000/api/admin/trigger-ingest?source=gdacs"

# Check pipeline status
curl http://localhost:8000/api/admin/pipeline-status
```

### Pipeline module structure

```
apps/backend/src/hali/ingestion/
├── __init__.py           get_enabled_adapters() factory
├── registry.py           Adapter registry
├── base.py               BaseAdapter ABC — shared ETL orchestration
├── models.py             RawPayload, ValidatedAlert, NormalisedAlert, IngestionResult
├── loader.py             PostGIS upsert, dead-letter tracking, country spatial join
├── normaliser.py         Geometry helpers, hazard maps, threshold functions
├── spatial_join.py       Alert-to-district P-code joins
├── fewsnet.py            FEWS NET IPC adapter (enabled)
├── hapi.py               HDX HAPI rainfall-anomaly adapter (enabled)
├── gdacs.py              GDACS REST adapter (enabled)
├── named_events.py       IFRC GO + WHO disease outbreak adapters (enabled)
├── chirps.py             CHIRPS FTP adapter (disabled by default)
├── gfs.py                GFS NOAA adapter (disabled by default)
├── glofas.py             GloFAS CDS adapter (disabled, needs key)
├── icpac.py              ICPAC SPI adapter (disabled by default)
├── worldpop.py           WorldPop population grid (one-shot reference)
└── admin_boundaries.py   OCHA COD-AB admin2 polygons (one-shot reference)
```

### Ingestion environment variables

```env
# Ingestion source toggles
ENABLE_SCHEDULER=true
ENABLE_GDACS=true
ENABLE_CHIRPS=false
ENABLE_GFS=false
ENABLE_GLOFAS=false
ENABLE_ICPAC=false

# Source credentials (only GloFAS needs one)
GLOFAS_CDS_API_KEY=
GLOFAS_CDS_URL=https://cds.climate.copernicus.eu/api
ICPAC_DIGILIB_BASE=http://digilib.icpac.net
CHIRPS_FTP_HOST=ftp.chg.ucsb.edu
```

### AI layer

Claude, Gemini, and Groq generate in parallel; a clarity scorer picks the winner against a Grade 5 reading-level floor. That covers alert translation into 10 languages, action-card generation for 7 livelihoods, and community-report labelling.

The ensemble runs only when the relevant API keys are configured. Without `ANTHROPIC_API_KEY`, reports store empty labels and adapters and tests still pass, so the repository is runnable with no AI credentials at all.

## USSD

Configure Africa's Talking to POST to `/ussd`. The flow uses `CON` for continuing menus and `END` for terminal responses.

## Data Boundaries

Countries are keyed by ISO2 codes: `KE`, `ET`, `SO`, `UG`, `DJ`, `ER`, `SD`, and `SS`. `sql/migrations/003_seed_igad_countries.sql` originally seeded these as bounding-box polygons; `sql/migrations/006_real_country_boundaries.sql` replaced them with 1:10m Natural Earth geometry, so the shipped database holds real boundaries rather than boxes.

District-level resolution comes from OCHA COD-AB admin2 polygons (migration 011), 891 districts across the 6 countries with authoritative geometry. Alerts join to districts by P-code, not by country outline.

## Database Contract

The SQL mirrors in `sql/migrations` are the Railway bootstrap contract. `alerts.geom`, `community_reports.location`, `countries.geom`, `user_subscriptions.location`, and `emerging_hotspots.location` are PostGIS geometry columns in EPSG:4326. Spatial indexes are named `alerts_geom_idx`, `community_reports_geom_idx`, `countries_geom_idx`, `user_subscriptions_loc_idx`, and `emerging_hotspots_geom_idx`.

On Railway the backend container applies `alembic upgrade head` on start-up (see `apps/backend/docker-entrypoint.sh`), so a deploy carries its own schema. Migrations are fail-closed — a broken migration aborts the boot and Railway keeps the previous deployment serving.

`DATABASE_URL` uses the `postgresql+asyncpg://` prefix for application configuration. `DATABASE_URL_RAW` and `MIGRATION_DATABASE_URL` use the raw `postgresql://` prefix for `psql`, Alembic, and other CLI tools.

## Railway

See `infra/railway.md`. Use Railway's `PostGIS` template, not the default plain `Postgres` template. Railway's default PostgreSQL image does not include the PostGIS system extension files, so `CREATE EXTENSION postgis` fails there.

The current Railway database layer is configured in workspace `Ronza`, project `chic-exploration`, service `PostGIS`. Run SQL mirrors or Alembic, set required env vars, and deploy backend with `uvicorn hali.main:app --host 0.0.0.0 --port $PORT`. Build frontend with `VITE_API_URL` pointing to the backend.

## Layer completion status

| Layer | Status | Detail |
|---|---|---|
| Database | ✅ Complete | PostgreSQL 16.14 + PostGIS 3.7 on Railway, GiST indexes in EPSG:4326 |
| Data ingestion | ✅ Complete | 13 sources, typed ETL, dead-letter tracking, live alerts in DB |
| AI ensemble | ✅ Complete | Claude, Gemini and Groq in parallel, clarity-scored; 10 languages, 7 livelihood action cards |
| Spatial intelligence | ✅ Complete | 891 admin2 polygons, population exposure, compound risk, draw-polygon AOI, DBSCAN hotspots |
| USSD / SMS | ✅ Complete | Africa's Talking, live PostGIS queries per menu step, not static text |
| WhatsApp | ✅ Complete | Meta Cloud API, interactive messages |
| Frontend PWA | ✅ Complete | React 19, Leaflet map, ICPAC WMS layers, Workbox offline cache and queued reports |
| Submission | ✅ Complete | Demo video and Devpost write-up |

## Known Limitations

- Live ingestion quality depends on what upstream providers publish; HALI cannot be better than its sources on a given day.
- Djibouti and Eritrea are excluded from district-level resolution, as no authoritative COD-AB geometry or rainfall series exists for them.
- Tigrinya, Luganda, and Afar are marked low-resource; the backend may serve English instead where model quality is weak.
- GloFAS, CHIRPS, GFS, and the ICPAC digilib SPI adapters are built and tested but ship disabled. GloFAS additionally needs a free CDS key.
- The AI layer runs only when `ANTHROPIC_API_KEY` is configured; without it, reports store empty labels and adapters and tests still pass.
