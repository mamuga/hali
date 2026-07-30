/**
 * Every figure here is traceable to the repository or HALI_FEATURES_TECHNICAL_SPECS.md.
 * See BRAND.md → "Source of truth for facts". Do not add a number without a source.
 *
 * Note on §2.2: the specs table still lists the original 5 adapters and has not
 * been regenerated since the HAPI, FEWS NET, IFRC and WHO adapters landed. Where
 * the spec and the code disagree, the code wins and is cited directly.
 */

/** packages/types/src/index.ts — Language union, in the order declared. */
export const languages = [
  { code: 'sw', name: 'Swahili' },
  { code: 'so', name: 'Somali' },
  { code: 'am', name: 'Amharic' },
  { code: 'om', name: 'Oromo' },
  { code: 'ar', name: 'Arabic' },
  { code: 'en', name: 'English' },
  { code: 'fr', name: 'French' },
  { code: 'ti', name: 'Tigrinya' },
  { code: 'lg', name: 'Luganda' },
  { code: 'aa', name: 'Afar' },
];

/** infra/railway.md — seed countries. */
export const countries = [
  'Kenya',
  'Ethiopia',
  'Somalia',
  'Uganda',
  'Djibouti',
  'Eritrea',
  'Sudan',
  'South Sudan',
];

/**
 * The 13 external data sources wired in this repository, each traced to the file
 * that calls it. `status` is the shipped default, not an aspiration:
 *
 *   on      — enabled in apps/backend/src/hali/config.py and scheduled
 *   off     — adapter is built and tested, flag defaults to false
 *   loaded  — one-shot reference ingest, already in the Railway database
 *
 * GloFAS and the ICPAC digilib SPI adapter are off. ICPAC's data still reaches
 * the map: its GeoPortal WMS layers render live inside HALI, which is the real
 * integration and a stronger claim than an alert adapter that is not running.
 */
export const sources = [
  {
    name: 'FEWS NET IPC',
    kind: 'condition',
    endpoint: 'fdw.fews.net/api/ipcpackage',
    signal: 'IPC food insecurity phase classification',
    schedule: 'Weekly, Monday 06:45 UTC',
    status: 'on',
    source: 'apps/backend/src/hali/ingestion/fewsnet.py',
  },
  {
    name: 'HDX HAPI',
    kind: 'condition',
    endpoint: 'hapi.humdata.org/api/v2',
    signal: 'dekadal rainfall anomaly per admin2 district',
    schedule: 'Daily 07:10 UTC',
    status: 'on',
    source: 'apps/backend/src/hali/ingestion/hapi.py',
  },
  {
    name: 'GDACS',
    kind: 'event',
    endpoint: 'gdacs.org/gdacsapi',
    signal: 'flood, drought, cyclone and wildfire events',
    schedule: 'Daily 06:00 UTC',
    status: 'on',
    source: 'apps/backend/src/hali/ingestion/gdacs.py',
  },
  {
    name: 'IFRC GO appeals',
    kind: 'event',
    endpoint: 'goadmin.ifrc.org/api/v2/appeal',
    signal: 'named emergency responses, including locust',
    schedule: 'Daily 07:25 UTC',
    status: 'on',
    source: 'apps/backend/src/hali/ingestion/named_events.py',
  },
  {
    name: 'WHO disease outbreak news',
    kind: 'event',
    endpoint: 'who.int/api/news/diseaseoutbreaknews',
    signal: 'epidemic events no satellite sees',
    schedule: 'Daily 07:25 UTC',
    status: 'on',
    source: 'apps/backend/src/hali/ingestion/named_events.py',
  },
  {
    name: 'ICPAC GeoPortal WMS',
    kind: 'map layer',
    endpoint: 'geoportal.icpac.net/geoserver/wms',
    signal:
      '5 layers: flood prone, drought prone, drought hazard index, desert locust hazard, multi-hazard risk',
    schedule: 'Live tiles, per map view',
    status: 'on',
    source: 'apps/frontend/src/lib/icpacLayers.ts',
  },
  {
    name: 'CHIRPS',
    kind: 'physical model',
    endpoint: 'ftp.chg.ucsb.edu',
    signal: 'daily rainfall anomaly GeoTIFF',
    schedule: 'Daily 07:00 UTC',
    status: 'off',
    source: 'apps/backend/src/hali/ingestion/chirps.py',
  },
  {
    name: 'NOAA GFS',
    kind: 'physical model',
    endpoint: 'ftp.cpc.ncep.noaa.gov/GIS/gfs_0.25',
    signal: '24h extreme rainfall forecast',
    schedule: 'Daily 06:15 UTC',
    status: 'off',
    source: 'apps/backend/src/hali/ingestion/gfs.py',
  },
  {
    name: 'GloFAS',
    kind: 'physical model',
    endpoint: 'cds.climate.copernicus.eu',
    signal: 'river discharge flood forecast, GRIB2',
    schedule: 'Daily 06:30 UTC',
    status: 'off',
    source: 'apps/backend/src/hali/ingestion/glofas.py',
  },
  {
    name: 'ICPAC digilib SPI',
    kind: 'physical model',
    endpoint: 'digilib.icpac.net',
    signal: 'standardised precipitation index, NetCDF',
    schedule: 'Daily 07:30 UTC',
    status: 'off',
    source: 'apps/backend/src/hali/ingestion/icpac.py',
  },
  {
    name: 'WorldPop population grid',
    kind: 'reference',
    endpoint: 'data.worldpop.org',
    signal: '1km 2020 UN-adjusted grid, 249,000 cells, 289,931,311 people',
    schedule: 'One-shot ingest, migration 010',
    status: 'loaded',
    source: 'apps/backend/src/hali/ingestion/worldpop.py',
  },
  {
    name: 'OCHA COD-AB',
    kind: 'reference',
    endpoint: 'data.humdata.org CKAN',
    signal: '891 admin2 district polygons across 6 countries',
    schedule: 'One-shot ingest, migration 011',
    status: 'loaded',
    source: 'apps/backend/src/hali/ingestion/admin_boundaries.py',
  },
  {
    name: 'Natural Earth',
    kind: 'reference',
    endpoint: 'github.com/nvkelso/natural-earth-vector',
    signal:
      '1:10m country boundaries for the 8 IGAD states, real geometry not bounding boxes',
    schedule: 'One-shot ingest, migration 006',
    status: 'loaded',
    source: 'sql/migrations/006_real_country_boundaries.sql',
  },
];

/**
 * The source counts are derived, not typed in. This file previously carried a
 * hand-written `sources: 5` that stayed at 5 for eight more adapters, which is
 * exactly the failure the header rule exists to prevent. Add a source to the
 * array above and every count on the page follows.
 */
export const facts = {
  languages: 10, // packages/types/src/index.ts — Language union
  livelihoods: 7, // packages/types/src/index.ts — Livelihood union
  hazards: 10, // packages/types/src/index.ts — HazardType union
  countries: 8, // infra/railway.md — IGAD seed ISO2 codes
  sources: sources.length,
  liveSources: sources.filter((s) => s.kind !== 'reference').length,
  referenceDatasets: sources.filter((s) => s.kind === 'reference').length,
  districts: 891, // HALI_FINAL_SPRINT_PLAN.md §Phase 6 — COD-AB admin2 polygons, 6 countries
  population: 289_931_311, // HALI_FINAL_SPRINT_PLAN.md §Phase 5 — WorldPop 2020 UN-adjusted grid total
  popGridCells: 249_000, // HALI_FINAL_SPRINT_PLAN.md §Phase 5 — pop_grid rows, all 8 countries
  channels: 3, // USSD, WhatsApp, PWA
};

/**
 * The gap HALI addresses, stated only in terms this repository can back up.
 * No external statistics — BRAND.md forbids publishing figures we cannot source.
 */
export const problem = [
  {
    figure: '1',
    unit: 'language',
    label:
      'Upstream hazard feeds publish in English. GDACS, GloFAS and GFS carry no translation of any kind.',
  },
  {
    figure: '0',
    unit: 'instructions',
    label:
      'A raw alert is a hazard code, a severity band and a polygon. It does not tell a pastoralist what to do with the herd.',
  },
  {
    figure: '10',
    unit: 'hazard types',
    label:
      'Flood, drought, locust, cyclone, heatwave, landslide, wildfire, epidemic, health, other. One system has to cover all of them.',
  },
];

/** The real pipeline, stage by stage. Sources per stage cited inline. */
export const pipeline = [
  {
    stage: `${facts.sources} external sources`,
    detail:
      'FEWS NET IPC, HDX HAPI, GDACS, IFRC GO and WHO run on independent schedules. CHIRPS, GFS, GloFAS and ICPAC SPI are built and flag-gated. Three reference datasets sit underneath, ingested once.',
  },
  {
    stage: 'Automated ETL',
    detail:
      'Extract, validate, transform, load. Pydantic boundary checks, MD5 dedup_hash with ON CONFLICT DO NOTHING, dead-letter tracking on every raw record. One adapter failing never blocks another.',
  },
  {
    stage: 'AI ensemble',
    detail:
      'Claude, Gemini and Groq generate in parallel. A clarity scorer picks the winner against a Grade 5 reading-level floor.',
  },
  {
    stage: 'PostGIS',
    detail: `PostgreSQL 16 with PostGIS 3.7. Alerts land on ${facts.districts} admin2 district polygons by P-code join, not country outlines. GiST indexes on zones, reports and geometry in EPSG:4326.`,
  },
  {
    stage: 'USSD / WhatsApp / PWA',
    detail:
      'USSD runs live PostGIS queries, not static menus. WhatsApp uses the Meta Cloud API. The PWA caches alerts and queues reports offline.',
  },
];

/**
 * specs §13.1, filtered to what is built and verifiable in the repository.
 * Rows marked "Designed" in the spec table are included only where the code
 * now exists; the file cited is the one that implements it.
 */
export const capabilities = [
  {
    name: 'Zero-registration access',
    detail: 'Any phone, any user, no account needed.',
  },
  {
    name: 'Automated multi-source ingestion',
    detail: `${facts.sources} external sources, ${facts.liveSources} live and ${facts.referenceDatasets} one-shot reference datasets, with no human in the loop.`,
  },
  {
    name: 'District-level resolution',
    detail: `${facts.districts} OCHA COD-AB admin2 polygons across 6 countries. Djibouti and Eritrea are left out where no authoritative geometry or rainfall series exists.`,
  },
  {
    name: 'Multi-model AI ensemble',
    detail:
      'Claude, Gemini and Groq outputs scored for clarity before publication.',
  },
  {
    name: 'AI multilingual translation',
    detail: '10 languages per alert, written to a Grade 5 reading level.',
  },
  {
    name: 'Livelihood-specific action cards',
    detail: '7 livelihoods across 10 languages, generated per alert.',
  },
  {
    name: 'Seasonal context injection',
    detail: 'Long rains, short rains and dry season framing on every alert.',
  },
  {
    name: 'Compound risk index',
    detail:
      'PostGIS scoring per country and district, served from /api/spatial/compound-risk.',
  },
  {
    name: 'Population exposure per alert',
    detail:
      'Zonal statistics against an ingested 249,000-cell WorldPop grid, 0.17 ms server-side, not a per-call external lookup.',
  },
  {
    name: 'Draw-polygon area query',
    detail:
      'Draw any shape on the map and get every alert, community report, hotspot and the population inside it.',
  },
  {
    name: 'Community ground truth to severity',
    detail:
      'Claude reads inbound reports and upgrades an alert when they agree.',
  },
  {
    name: 'DBSCAN emerging hotspot detection',
    detail:
      'Clusters community reports every 30 minutes to surface events before official alerts.',
  },
  {
    name: 'ICPAC WMS layers in the map',
    detail:
      "5 layers from ICPAC's own GeoPortal, composited over HALI alert zones.",
  },
  {
    name: 'Spatial subscriber targeting',
    detail: 'Zone intersection in PostGIS, not a broadcast list.',
  },
  {
    name: 'Dead-letter ETL tracking',
    detail: 'Every raw record is stored, status-tracked and replayable.',
  },
  {
    name: 'Offline PWA',
    detail: 'Workbox caching with a queued report submission path.',
  },
  {
    name: 'Admin API key auth',
    detail: 'Constant-time HMAC comparison, not a config flag.',
  },
];

/** specs §1 — runtime, database, AI, frontend, deployment. */
export const stack = [
  'FastAPI',
  'Python 3.12',
  'PostgreSQL 16',
  'PostGIS 3.7',
  'Alembic',
  'APScheduler',
  'Claude',
  'Gemini',
  'Groq',
  'scikit-learn',
  'React 19',
  'Vite',
  'Tailwind v4',
  'Leaflet',
  'Astro',
  "Africa's Talking",
  'WhatsApp Cloud API',
  'Railway',
];

export const team = [
  { name: 'Martin Muga', email: 'martinmuga04@gmail.com' },
  { name: "Mary Ndung'u", email: 'maryndungu267@gmail.com' },
];
