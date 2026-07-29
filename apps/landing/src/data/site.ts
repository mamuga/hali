/**
 * Every figure here is traceable to the repository or HALI_FEATURES_TECHNICAL_SPECS.md.
 * See BRAND.md → "Source of truth for facts". Do not add a number without a source.
 */

export const facts = {
  languages: 10, // packages/types/src/index.ts — Language union
  livelihoods: 7, // packages/types/src/index.ts — Livelihood union
  hazards: 10, // packages/types/src/index.ts — HazardType union
  countries: 8, // infra/railway.md — IGAD seed ISO2 codes
  sources: 5, // specs §2.2
  channels: 3, // USSD, WhatsApp, PWA
};

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

/** specs §2.2 and §3.1 — the real pipeline, stage by stage. */
export const pipeline = [
  {
    stage: '5 satellite sources',
    detail:
      'GDACS REST, CHIRPS FTP, GFS NOAA, GloFAS CDS, ICPAC digilib. Fetched on a daily schedule from 06:00 UTC.',
  },
  {
    stage: 'Automated ETL',
    detail:
      'Extract, validate, transform, load. Pydantic boundary checks, MD5 dedup_hash with ON CONFLICT DO NOTHING, dead-letter tracking on every raw record.',
  },
  {
    stage: 'AI ensemble',
    detail:
      'Claude, Gemini and Groq generate in parallel. A clarity scorer picks the winner against a Grade 5 reading-level floor.',
  },
  {
    stage: 'PostGIS',
    detail:
      'PostgreSQL 16 with PostGIS 3.7. GiST indexes on alert zones, community reports and country geometry in EPSG:4326.',
  },
  {
    stage: 'USSD / WhatsApp / PWA',
    detail:
      'USSD runs live PostGIS queries, not static menus. WhatsApp uses the Meta Cloud API. The PWA caches alerts and queues reports offline.',
  },
];

/**
 * specs §13.1, filtered to what is built and verifiable. Wording follows the
 * spec table; nothing new is claimed here.
 */
export const capabilities = [
  {
    name: 'Zero-registration access',
    detail: 'Any phone, any user, no account needed.',
  },
  {
    name: 'Automated multi-source ingestion',
    detail: 'GDACS, CHIRPS, GFS, GloFAS and ICPAC, with no human in the loop.',
  },
  {
    name: 'Multi-model AI ensemble',
    detail: 'Claude, Gemini and Groq outputs scored for clarity before publication.',
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
    name: 'Community ground truth to severity',
    detail: 'Claude reads inbound reports and upgrades an alert when they agree.',
  },
  {
    name: 'DBSCAN emerging hotspot detection',
    detail: 'Clusters community reports to surface events before official alerts.',
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
  'React 19',
  'Vite',
  'Tailwind v4',
  'Leaflet',
  "Africa's Talking",
  'WhatsApp Cloud API',
  'Railway',
];

export const team = [
  { name: 'Martin Muga', email: 'martinmuga04@gmail.com' },
  { name: "Mary Ndung'u", email: 'maryndungu267@gmail.com' },
];
