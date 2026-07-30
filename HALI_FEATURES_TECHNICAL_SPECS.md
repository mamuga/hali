# HALI — Features & Technical Specifications

> **Hyper-Local Early Warning System for East Africa**
> Version 1.0 · IGAD Hackathon 2026 Submission
> Stack: FastAPI · PostgreSQL + PostGIS · Claude AI · React PWA · Railway

---

## Table of Contents

1. [Core Architecture](#1-core-architecture)
2. [Data Ingestion Pipeline](#2-data-ingestion-pipeline)
3. [AI Intelligence Layer](#3-ai-intelligence-layer)
4. [GIS & Spatial Analysis](#4-gis--spatial-analysis)
5. [Delivery Channels](#5-delivery-channels)
6. [Community Intelligence Loop](#6-community-intelligence-loop)
7. [Subscriber Management](#7-subscriber-management)
8. [Frontend PWA](#8-frontend-pwa)
9. [Admin & Operations](#9-admin--operations)
10. [Database Schema](#10-database-schema)
11. [API Reference](#11-api-reference)
12. [Infrastructure](#12-infrastructure)
13. [HALI Moat — Differentiation Matrix](#13-hali-moat--differentiation-matrix)

---

## 1. Core Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HALI ARCHITECTURE                             │
│                                                                         │
│  DATA SOURCES          ETL PIPELINE         AI LAYER                   │
│  ───────────           ────────────         ────────                   │
│  GDACS REST    ──►     Async fetchers  ──►  Translation (5 langs)      │
│  CHIRPS FTP    ──►     Normaliser      ──►  Action cards (4 liveli.)   │
│  GFS NOAA      ──►     Dedup (hash)    ──►  NLP classification         │
│  GloFAS CDS    ──►     PostGIS load    ──►  Severity escalation        │
│  ICPAC digilib ──►     Dead-letter     ──►  Emerging hotspot ML        │
│                                                                         │
│  DATABASE              DELIVERY             FRONTEND                   │
│  ────────              ────────             ────────                   │
│  PostgreSQL 16         USSD (AT)            React PWA                  │
│  PostGIS 3.7           WhatsApp Cloud       Leaflet GIS map            │
│  6 tables              SMS (AT bulk)        Offline PWA                │
│  3 GiST indexes        Push notifications   shadcn/ui                  │
│                        PWA push                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Runtime:** Python 3.12 + FastAPI on Railway
**Database:** PostgreSQL 16.14 + PostGIS 3.7 (Railway, workspace: Ronza, project: chic-exploration)
**AI:** Claude API (`claude-sonnet-4-6`) + Gemini 2.5 Flash + Groq Llama-4
**Messaging:** Africa's Talking (USSD + SMS) + Meta WhatsApp Cloud API
**Frontend:** React 19 + Vite 8 + Tailwind v4 + shadcn/ui + Leaflet.js
**Deployment:** Railway (backend + frontend) · GitHub Actions CI/CD

---

## 2. Data Ingestion Pipeline

### 2.1 Architecture — Industry-standard ETL

Every source adapter follows the same four-stage pattern:

```
EXTRACT → VALIDATE → TRANSFORM → LOAD
   │           │           │         │
Raw payload  Pydantic   HALI model  PostGIS
to           schema     + dedup     upsert
raw_ingestion check      hash       ON CONFLICT
```

**Design principles enforced:**
- Extract is read-only — fetchers never write business logic
- Idempotent loads — `dedup_hash` MD5 unique constraint, `ON CONFLICT DO NOTHING`
- Dead-letter tracking — `raw_ingestion.status`: `pending → processing → processed | failed`
- Source isolation — one adapter failure never blocks others
- Replay capability — raw payload stored, failed records reprocessable without re-fetching
- Config-driven — `ENABLE_*` flags, disabled sources fail loudly at startup if keys missing

### 2.2 Sources

| Source | Auth | Schedule | Format | Signal | Status |
|---|---|---|---|---|---|
| GDACS REST | None | 06:00 UTC daily | GeoJSON | Flood, drought, cyclone, wildfire | ✅ Enabled |
| CHIRPS FTP | Anonymous | 07:00 UTC daily | GeoTIFF | Daily rainfall anomalies (>50mm flood, <2mm drought) | ⚫ Toggle |
| GFS NOAA | None | 06:15 UTC daily | GeoTIFF | 24h extreme rainfall forecast (>75mm) | ⚫ Toggle |
| GloFAS CDS | Free CDS key | 06:30 UTC daily | GRIB2 | River discharge flood forecast | ⚫ Toggle |
| ICPAC digilib | None | 07:30 UTC daily | NetCDF | SPI drought index (SPI<-1 orange, SPI<-2 red) | ⚫ Toggle |

### 2.3 Adapter interface

```python
class BaseAdapter(ABC):
    source: SourceName

    async def extract(self) -> list[RawPayload]: ...
    def validate(self, raw: RawPayload) -> ValidatedAlert | None: ...
    def transform(self, validated: ValidatedAlert) -> NormalisedAlert: ...
    async def run(self) -> IngestionResult: ...  # shared ETL orchestration
```

### 2.4 Pydantic models

```python
RawPayload        # raw wire data, source + fetched_at + raw_data dict
ValidatedAlert    # boundary-checked: HazardType enum, Severity enum, GeoJSONGeometry
NormalisedAlert   # HALI domain model: geojson_geometry, dedup_hash, affected_countries
IngestionResult   # pipeline summary: raw/validated/inserted/skipped/failed counts + duration_ms
```

### 2.5 Deduplication

```python
dedup_hash = MD5(f"{source}:{event_id}:{severity}")
# Stored as UNIQUE constraint on alerts.dedup_hash
# ON CONFLICT (dedup_hash) DO NOTHING
# Safe to re-run the pipeline at any time
```

### 2.6 Scheduler

```
06:00 UTC — GDACS
06:15 UTC — GFS
06:30 UTC — GloFAS
07:00 UTC — CHIRPS
07:30 UTC — ICPAC
```

APScheduler `AsyncIOScheduler`. Each job runs in isolated `try/except`. One failure
never blocks others. Logs structured JSON on every E/V/T/L step via `structlog`.

### 2.7 Required env vars

```env
ENABLE_SCHEDULER=true
ENABLE_GDACS=true
ENABLE_CHIRPS=false
ENABLE_GFS=false
ENABLE_GLOFAS=false
ENABLE_ICPAC=false
GLOFAS_CDS_API_KEY=          # free from cds.climate.copernicus.eu
CHIRPS_FTP_HOST=ftp.chg.ucsb.edu
ICPAC_DIGILIB_BASE=http://digilib.icpac.net
```

---

## 3. AI Intelligence Layer

### 3.1 Multi-model ensemble (Innovation)

All translation and content generation runs through a three-model ensemble.
Every provider runs in parallel. Outputs are scored against a humanitarian
clarity rubric. The highest-scoring output wins.

```
Claude claude-sonnet-4-6  ──►  score ──►  winner
Gemini 2.5 Flash          ──►  score ──►  (ensemble selects best)
Groq Llama-4-Scout        ──►  score ──►
         │
         ▼ if all fail
    cached last-known translation  (never fails silently)
```

**Fallback chain:** Claude → Gemini (free, 1500/day) → Groq (free, fast) → cached

### 3.2 Humanitarian clarity scorer

Five-dimension rubric scoring 0.0–1.0 per output:

| Dimension | Weight | What it measures |
|---|---|---|
| Length appropriateness | 20% | Headline ≤20 words, body ≤80 words |
| Actionability | 25% | Contains action verbs in target language |
| Specificity | 20% | Contains location or hazard-specific terms |
| Reading level | 20% | Short sentences (<15 words avg), short words |
| Completeness | 15% | Both headline and body non-empty |

**Why this matters:** Picks the translation that actually communicates to
a semi-literate community member, not just the grammatically correct one.

### 3.3 Translation — 5 languages per alert

```python
LANGUAGES = ["sw", "so", "am", "om", "ar"]
# Swahili, Somali, Amharic, Oromo, Arabic

# Per alert: 5 parallel API calls (asyncio.gather)
# Stored in: alert_translations(alert_id, language, headline, body)
# On-demand generation if language not yet in DB
```

**Prompt design:**
- Grade 5 reading level
- Action-first language (what will happen, where, when)
- No invented details — only what the alert data contains
- Culturally appropriate framing per language group
- For Amharic/Arabic: correct script output enforced in system prompt

### 3.4 Action cards — 6 languages × 4 livelihoods per alert

```python
LIVELIHOODS = ["farmer", "pastoralist", "fisherfolk", "urban"]
LANGUAGES   = ["sw", "so", "am", "om", "ar", "en"]
# = 24 action cards per alert, generated and stored
# Stored in: action_cards(alert_id, livelihood, language, steps)
# UNIQUE(alert_id, livelihood, language)
```

**Context enrichment per card:**
- Season derived from alert timestamp (long_rains Mar-May / short_rains Oct-Dec / dry)
- Dominant livelihood derived from affected country ISO2 codes
- Livelihood-specific vocabulary in prompt (pastoralist ≠ farmer ≠ fisherfolk)
- Season-aware framing ("even though it's the dry season, flash floods...")

**On-demand generation:** `/api/alerts/{id}/action-card?livelihood=X&lang=Y` checks
DB first, generates via Claude if not found, stores result for future requests.

### 3.5 Community report NLP classification

```python
# Async background task — does not block HTTP response
# Input: free-text description + hazard_type
# Output: labels[] → ["flood", "road_blocked", "livestock_at_risk"]
# Valid labels:
VALID_LABELS = [
    "flood", "drought", "locust", "cyclone", "health_emergency",
    "road_blocked", "bridge_damaged", "crop_loss", "livestock_at_risk",
    "displacement", "shelter_needed", "water_shortage", "food_shortage",
    "medical_needed", "communication_down", "power_outage", "other"
]
# Stored in: community_reports.labels[]
```

### 3.6 Severity escalation from ground truth (Innovation)

```python
GROUND_TRUTH_UPGRADE_THRESHOLD = 3  # reports needed to trigger assessment

# Trigger: when N community reports land inside an existing alert zone (PostGIS)
# Claude reads descriptions, assesses whether severity should upgrade
# Response: { should_upgrade, proposed_severity, confidence, reasoning }
# If confidence > 0.6 and proposed_severity > current:
#   UPDATE alerts SET severity = proposed_severity, is_new = TRUE
# Alert re-enters the processing queue → new translations + action cards generated
```

**Why this is novel:** No national early warning system currently allows
community ground truth to upgrade official alert severity automatically.
This closes the loop between field observations and alert intelligence.

### 3.7 AI layer env vars

```env
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...           # free: aistudio.google.com/apikey
GROQ_API_KEY=gsk_...             # free: console.groq.com/keys
AI_PRIMARY_MODEL=claude-sonnet-4-6
AI_GEMINI_MODEL=gemini-2.5-flash
AI_GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
AI_ENSEMBLE_ENABLED=true
AI_MIN_CLARITY_SCORE=0.6
AI_BACKLOG_BATCH_SIZE=5
AI_MAX_CONCURRENT_ALERTS=2       # tuned for free-tier rate limits
GROUND_TRUTH_UPGRADE_THRESHOLD=3
```

---

## 4. GIS & Spatial Analysis

### 4.1 PostGIS spatial foundation

All geometry stored in EPSG:4326. Three geometry columns:

```sql
alerts.geom              GEOMETRY(MultiPolygon, 4326)  -- alert coverage zones
community_reports.location  GEOMETRY(Point, 4326)      -- report coordinates
countries.geom           GEOMETRY(MultiPolygon, 4326)  -- IGAD member states

-- GiST indexes on all three for fast spatial queries
CREATE INDEX alerts_geom_idx ON alerts USING GIST(geom);
CREATE INDEX community_reports_geom_idx ON community_reports USING GIST(location);
CREATE INDEX countries_geom_idx ON countries USING GIST(geom);
```

### 4.2 ICPAC WMS layer integration (Innovation)

Direct integration with ICPAC's own GeoServer — judges see their own data
inside HALI.

```javascript
// Leaflet WMS layers from ICPAC GeoPortal
const ICPAC_WMS = 'https://geoportal.icpac.net/geoserver/wms';

const icpacLayers = {
  'Rainfall Anomaly': L.tileLayer.wms(ICPAC_WMS, {
    layers: 'geonode:rainfall_anomaly',
    format: 'image/png',
    transparent: true,
    opacity: 0.65,
  }),
  'Flood Risk': L.tileLayer.wms(ICPAC_WMS, {
    layers: 'geonode:flood_risk',
    format: 'image/png',
    transparent: true,
    opacity: 0.70,
  }),
  'SPI Drought Index': L.tileLayer.wms(ICPAC_WMS, {
    layers: 'geonode:spi_3month',
    format: 'image/png',
    transparent: true,
    opacity: 0.60,
  }),
  'Hazard Watch': L.tileLayer.wms(ICPAC_WMS, {
    layers: 'geonode:ea_hazard_zones',
    format: 'image/png',
    transparent: true,
    opacity: 0.55,
  }),
};

// Layer switcher control — GIS dev adds to HaliMap.tsx
L.control.layers({}, icpacLayers).addTo(map);
```

**Frontend:** Floating layer switcher panel on map. Users toggle ICPAC
authoritative layers on top of HALI alert zones. Visual correlation between
ICPAC's rainfall anomaly and HALI's flood alerts is immediately visible.

### 4.3 Compound risk index (Innovation)

PostGIS spatial analysis combining 4 signals into a single risk score
per IGAD member state.

```sql
-- Endpoint: GET /api/spatial/compound-risk
-- Returns: GeoJSON FeatureCollection with risk_score property per country

WITH alert_exposure AS (
  SELECT
    a.id,
    a.hazard_type,
    a.severity,
    c.iso2,
    c.name AS country_name,
    ST_Area(ST_Intersection(a.geom, c.geom)::geography) / 1000000 AS overlap_km2,
    CASE a.severity
      WHEN 'red'    THEN 3
      WHEN 'orange' THEN 2
      ELSE 1
    END AS sev_weight
  FROM alerts a
  JOIN countries c ON ST_Intersects(a.geom, c.geom)
  WHERE a.valid_to > NOW()
),
report_density AS (
  SELECT
    c.iso2,
    COUNT(cr.id)::float AS report_count,
    COUNT(cr.id)::float / NULLIF(ST_Area(c.geom::geography) / 1e10, 0) AS density
  FROM countries c
  LEFT JOIN community_reports cr
    ON ST_Intersects(cr.location, c.geom)
    AND cr.reported_at > NOW() - INTERVAL '14 days'
  GROUP BY c.iso2, c.geom
)
SELECT
  ae.iso2,
  ae.country_name,
  ae.hazard_type,
  ROUND((
    ae.sev_weight
    * ae.overlap_km2
    * (1 + COALESCE(rd.density, 0) * 100)
  )::numeric, 2) AS compound_risk_score,
  ae.overlap_km2,
  COALESCE(rd.report_count, 0) AS community_reports,
  ST_AsGeoJSON(c.geom)         AS geojson
FROM alert_exposure ae
JOIN countries c ON c.iso2 = ae.iso2
LEFT JOIN report_density rd ON rd.iso2 = ae.iso2
ORDER BY compound_risk_score DESC;
```

**Map rendering:** Choropleth layer on IGAD countries. Colour scale from
light blue (low) to deep red (high). Ranked list panel: "Top 5 at-risk
districts right now" with scores and contributing factors.

### 4.4 Population exposure via WorldPop (Innovation)

Every alert shows estimated people affected. Called once on alert creation,
result cached in `alerts.population_exposed`.

```python
# WorldPop REST API — free, no key, 1000 calls/day
async def compute_population_exposure(geojson_dict: dict) -> int:
    url = "https://api.worldpop.org/v1/services/stats"
    params = {
        "dataset": "wpgppop",
        "year": 2020,
        "geojson": json.dumps(geojson_dict),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        data = resp.json()
    return int(data.get("data", {}).get("total_population", 0))

# Stored: alerts.population_exposed INTEGER
# Returned in: /api/alerts/geojson properties
# Displayed: "~340,000 people in affected zone"
```

**Database addition:**
```sql
ALTER TABLE alerts ADD COLUMN population_exposed INTEGER DEFAULT 0;
```

### 4.5 DBSCAN emerging hotspot detection (Own ML model)

Spatial clustering of community reports to detect emerging events before
any official alert has been issued.

```python
# ai/spatial_clustering.py
from sklearn.cluster import DBSCAN
import numpy as np

async def detect_emerging_hotspots(pool: asyncpg.Pool) -> list[dict]:
    """
    DBSCAN on community report coordinates.
    Clusters not covered by any active official alert = emerging hotspot.

    Algorithm:
      epsilon = 50km radius (in radians for haversine metric)
      min_samples = 3 reports to form a cluster
      metric = haversine (accurate great-circle distance)

    A cluster is 'emerging' if its centroid is NOT within 100km
    of any active alert zone (PostGIS ST_DWithin check).
    """
    rows = await pool.fetch("""
        SELECT id, ST_Y(location) AS lat, ST_X(location) AS lng,
               hazard_type, reported_at
        FROM community_reports
        WHERE reported_at > NOW() - INTERVAL '7 days'
    """)

    if len(rows) < 3:
        return []

    coords = np.array([[r['lat'], r['lng']] for r in rows])
    coords_rad = np.radians(coords)

    db = DBSCAN(
        eps=50 / 6371,         # 50km in radians
        min_samples=3,
        algorithm='ball_tree',
        metric='haversine'
    ).fit(coords_rad)

    hotspots = []
    for label in set(db.labels_) - {-1}:
        mask = db.labels_ == label
        cluster = coords[mask]
        cluster_rows = [rows[i] for i, m in enumerate(mask) if m]

        centroid_lat = float(cluster[:, 0].mean())
        centroid_lng = float(cluster[:, 1].mean())
        dominant_hazard = max(
            set(r['hazard_type'] for r in cluster_rows),
            key=lambda h: sum(1 for r in cluster_rows if r['hazard_type'] == h)
        )

        # PostGIS check: is this already covered by an official alert?
        async with pool.acquire() as conn:
            covered = await conn.fetchval("""
                SELECT EXISTS(
                    SELECT 1 FROM alerts
                    WHERE valid_to > NOW()
                    AND ST_DWithin(
                        geom::geography,
                        ST_Point($1, $2)::geography,
                        100000
                    )
                )
            """, centroid_lng, centroid_lat)

        if not covered:
            report_count = int(mask.sum())
            hotspots.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [centroid_lng, centroid_lat]
                },
                "properties": {
                    "report_count": report_count,
                    "dominant_hazard": dominant_hazard,
                    "confidence": min(report_count / 10, 1.0),
                    "status": "UNCONFIRMED — no official alert",
                    "first_reported": min(
                        r['reported_at'] for r in cluster_rows
                    ).isoformat(),
                }
            })

    return sorted(hotspots, key=lambda h: h['properties']['report_count'], reverse=True)
```

**Scheduler:** Runs every 30 minutes via APScheduler.
**API endpoint:** `GET /api/spatial/emerging-hotspots`
**Map layer:** Pulsing amber dots. Click popup: "7 reports in this area.
No official alert issued. Dominant hazard: flood. First reported: 3 hours ago."
**Significance:** The system detects crises before official channels.

```python
# APScheduler job
@scheduler.scheduled_job(CronTrigger(minute='*/30'))
async def run_hotspot_detection():
    pool = get_pool()
    hotspots = await detect_emerging_hotspots(pool)
    # Store results in emerging_hotspots table for map serving
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM emerging_hotspots")
        for h in hotspots:
            await conn.execute("""
                INSERT INTO emerging_hotspots
                  (location, report_count, dominant_hazard, confidence, first_reported)
                VALUES (ST_Point($1,$2), $3, $4, $5, $6)
            """,
            h['geometry']['coordinates'][0],
            h['geometry']['coordinates'][1],
            h['properties']['report_count'],
            h['properties']['dominant_hazard'],
            h['properties']['confidence'],
            h['properties']['first_reported'],
        )
```

**New table:**
```sql
CREATE TABLE emerging_hotspots (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    location       GEOMETRY(Point, 4326) NOT NULL,
    report_count   INTEGER NOT NULL,
    dominant_hazard TEXT NOT NULL,
    confidence     FLOAT NOT NULL,
    first_reported TIMESTAMPTZ NOT NULL,
    detected_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX emerging_hotspots_geom_idx ON emerging_hotspots USING GIST(location);
```

### 4.6 Click-to-analyse spatial intelligence

Clicking anywhere on the map fires a live PostGIS spatial analysis query
and opens a side panel with a location intelligence report.

```sql
-- GET /api/spatial/analyse?lat=X&lng=Y
SELECT
    a.hazard_type,
    a.severity,
    COALESCE(at.headline, a.hazard_type || ' alert') AS headline,
    ROUND(ST_Distance(
        a.geom::geography,
        ST_Point($lng, $lat)::geography
    )::numeric / 1000, 1) AS dist_km,
    a.valid_to,
    a.population_exposed,
    c.name AS country,
    (
        SELECT COUNT(*) FROM community_reports cr
        WHERE ST_DWithin(
            cr.location::geography,
            ST_Point($lng, $lat)::geography,
            100000
        )
        AND cr.reported_at > NOW() - INTERVAL '7 days'
    ) AS nearby_reports_7d,
    (
        SELECT COUNT(*) FROM emerging_hotspots eh
        WHERE ST_DWithin(
            eh.location::geography,
            ST_Point($lng, $lat)::geography,
            100000
        )
    ) AS emerging_hotspots_nearby
FROM alerts a
JOIN countries c ON ST_Intersects(c.geom, ST_Point($lng, $lat))
LEFT JOIN alert_translations at ON at.alert_id = a.id AND at.language = 'sw'
WHERE ST_DWithin(a.geom::geography, ST_Point($lng, $lat)::geography, 500000)
  AND a.valid_to > NOW()
ORDER BY dist_km ASC
LIMIT 5;
```

**Frontend panel output (example):**
```
Analysis for this location
────────────────────────────────────
Nearest alert:   FLOOD · RED · 23km
Population:      ~340,000 people
Valid until:     Jul 16, 2026
Headline:        Mafuriko makubwa yanatarajiwa...

Community reports (7 days):   8
  • 3× flood
  • 2× road blocked
  • 3× livestock at risk

Emerging hotspot:   DETECTED
  7 reports clustered here
  No official alert issued yet
────────────────────────────────────
```

### 4.7 Temporal animation — 30-day playback

Time slider on the map replays how the alert and report situation evolved.

**Backend:** `/api/alerts/geojson` accepts `?from_date=X&to_date=Y`:
```sql
WHERE a.valid_from <= $to_date::timestamptz
  AND a.valid_to >= $from_date::timestamptz
```

**Frontend:** Date range slider (Day 1 to Day 30). On slider move:
- Re-fetch GeoJSON for that date range
- Re-render alert zones
- Filter community report heatmap to reports in that window
- Animate dots appearing at their `reported_at` timestamp

**Impact:** Shows the narrative of a hazard evolving — alert appears,
community reports cluster inside it, severity upgrades to red. Judges
see the full early warning system lifecycle in 30 seconds.

### 4.8 GeoJSON endpoints

```
GET /api/alerts/geojson
    ?bbox=21,-12,52,24    (East Africa default)
    &lang=sw
    &severity=red
    &hazard=flood
    &from_date=2026-07-01
    &to_date=2026-07-14
    → FeatureCollection with population_exposed in properties

GET /api/spatial/compound-risk
    → FeatureCollection: IGAD countries with compound_risk_score

GET /api/spatial/analyse?lat=X&lng=Y
    → Location intelligence report (5 nearest alerts, reports, hotspots)

GET /api/spatial/emerging-hotspots
    → FeatureCollection of DBSCAN-detected clusters with no official alert

GET /api/reports/heatmap?days=7
    → FeatureCollection of Point features for Leaflet.heat
```

---

## 5. Delivery Channels

### 5.1 USSD — Africa's Talking

**Philosophy:** Pull channel. Zero registration. Any phone. Any network.
No internet. Works on a 2010 Nokia.

**Technical setup:**
```
Africa's Talking dashboard (sandbox, live):
  Service code: *384*97980#
  Callback URL: https://backend-production-a6cf.up.railway.app/ussd
  Method: POST
  Sandbox: dial the code in the AT web simulator

FastAPI endpoint: POST /ussd
Response format:
  CON <text>   = continue session (show menu)
  END <text>   = terminate session (final message)
Response timeout: < 3 seconds (AT kills session at 3s)
Max chars per page: 182 in GSM-7, 80 once the page holds any character
  outside that alphabet — which every non-Latin translation does. The page
  helper derives the limit from the content; see routers/ussd.py.
```

**Menu tree:**
```
Dial *XXX#
  → [empty] = main menu
  "1" → Latest alert for user's area + action steps menu
    "1*1" → Farmer action steps (END)
    "1*2" → Pastoralist action steps (END)
    "1*3" → Fisherfolk action steps (END)
    "1*4" → Urban action steps (END)
  "2" → Report a hazard
    "2*1" → Flood (END: confirmed + phone stored if opted in)
    "2*2" → Drought
    "2*3" → Locusts
    "2*4" → Other
  "3" → Get SMS alerts (opt-in)
    → Phone number captured from USSD session metadata
    → Stored in user_subscriptions with language=sw, preferred_iso2 from menu
  "4" → About HALI (END)
```

**USSD opt-in for SMS alerts:**
```python
# Africa's Talking provides phone number in USSD session
# No form — user presses one button
# POST body contains: phoneNumber=+254700000000

await db.execute("""
    INSERT INTO user_subscriptions
      (phone_number, channel, language, livelihood,
       preferred_iso2, opted_in_via)
    VALUES ($1, 'sms', $2, $3, $4, 'ussd')
    ON CONFLICT (phone_number) DO UPDATE
      SET opted_in = TRUE, last_active = NOW()
""", phone_number, selected_language, selected_livelihood, selected_iso2)
```

**Env vars:**
```env
AFRICASTALKING_USERNAME=sandbox
AFRICASTALKING_API_KEY=atsk_...
```

### 5.2 WhatsApp — Meta Cloud API

**Philosophy:** Conversational. Rich text. Works over WiFi.
Zero cost on data bundles. Urban and connected users.

**Technical setup:**
```
Meta Developer Console:
  App type: Business
  Product: WhatsApp
  Webhook URL: https://backend.railway.app/whatsapp
  Verify token: WHATSAPP_VERIFY_TOKEN (env var)
  Webhook fields: messages

Phone Number ID: from Meta → stored as WHATSAPP_PHONE_NUMBER_ID
Access Token:    permanent system user token → WHATSAPP_TOKEN
API version:     v21.0
```

**Endpoints:**
```
GET  /whatsapp  — Meta webhook verification (hub.challenge echo)
POST /whatsapp  — Incoming message handler
```

**Message signature verification:**
```python
# X-Hub-Signature-256 header verification
# Prevents spoofed webhook calls
import hmac, hashlib
expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
received = header.removeprefix("sha256=")
valid = hmac.compare_digest(expected, received)
```

**Intent routing:**
```
"alerts" / "tahadhari"  → latest alert for user's region
"help" / "habari"       → onboarding menu
"subscribe"             → conversational opt-in flow (region → livelihood → confirm)
"report <text>"         → submit community report
"stop"                  → opt out of proactive messages
anything else           → gentle redirect to commands
```

**WhatsApp opt-in conversation:**
```
User: "subscribe"
HALI: "Asante! Niambie eneo lako: 1.Kenya 2.Ethiopia 3.Somalia..."
User: "1"
HALI: "Maisha yako: 1.Mkulima 2.Mfugaji 3.Mvuvi 4.Mjini"
User: "2"
HALI: "✅ Umesajiliwa! Utapokea tahadhari za Orange na Red kwa Kiswahili."
      "Tuma STOP kuacha wakati wowote."
→ phone_number stored in user_subscriptions, channel='whatsapp'
```

**Outbound template messages (proactive alerts):**
```python
# Requires Meta pre-approved template for proactive messaging
# Template name: hali_alert_v1
# Variables: {{hazard_type}}, {{severity}}, {{headline}}, {{action_1}}

payload = {
    "messaging_product": "whatsapp",
    "to": subscriber.phone_number,
    "type": "template",
    "template": {
        "name": "hali_alert_v1",
        "language": {"code": "sw"},
        "components": [{
            "type": "body",
            "parameters": [
                {"type": "text", "text": alert.hazard_type},
                {"type": "text", "text": alert.severity.upper()},
                {"type": "text", "text": translation.headline},
                {"type": "text", "text": action_card.steps.split("\n")[0]},
            ]
        }]
    }
}
```

**Env vars:**
```env
WHATSAPP_TOKEN=EAAx...
WHATSAPP_PHONE_NUMBER_ID=123456789
WHATSAPP_VERIFY_TOKEN=hali_webhook_2026
WHATSAPP_API_VERSION=v21.0
```

### 5.3 Outbound alert broadcast (when a new high-severity alert fires)

```python
# Triggered by scheduler after AI processing completes
# Only fires for severity = orange or red

async def broadcast_alert(alert_id: UUID, pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        # Get alert details
        alert = await conn.fetchrow(
            "SELECT * FROM alerts WHERE id = $1", alert_id
        )

        # Get all opted-in subscribers whose location intersects alert zone
        subscribers = await conn.fetch("""
            SELECT phone_number, channel, language, livelihood
            FROM user_subscriptions
            WHERE opted_in = TRUE
              AND min_severity_rank <= $1
              AND (
                ST_Intersects(location, (SELECT geom FROM alerts WHERE id = $2))
                OR preferred_iso2 = ANY((SELECT affected_countries FROM alerts WHERE id = $2))
              )
        """, SEVERITY_RANK[alert['severity']], alert_id)

    for sub in subscribers:
        # Get translation in subscriber's language
        translation = await get_translation(alert_id, sub['language'], pool)
        action_card = await get_action_card(alert_id, sub['livelihood'], sub['language'], pool)

        if sub['channel'] in ('sms', 'both'):
            await send_sms(sub['phone_number'], translation.headline[:160])

        if sub['channel'] in ('whatsapp', 'both'):
            await send_whatsapp_template(sub['phone_number'], alert, translation, action_card)
```

---

## 6. Community Intelligence Loop

### 6.1 Report submission — three channels

All three write to the same `community_reports` table:

```
PWA form     → POST /api/reports (JSON body with lat/lng)
USSD         → POST /ussd (phone number from session, no GPS)
WhatsApp     → POST /whatsapp (message parsed, phone = identity)
```

**Offline queue (PWA):** If user is offline, report stored in `localStorage`
with key `hali:report_queue`. `useReportQueue` hook retries automatically
on reconnect. Up to 3 attempts before abandoning.

### 6.2 Report processing pipeline

```
Report submitted
    ↓
INSERT community_reports (location, hazard_type, description, labels=[])
    ↓
HTTP 201 returned immediately (user sees success)
    ↓ (async background task)
Claude NLP classifies description → labels[]
UPDATE community_reports SET labels = $labels
    ↓ (every 30 minutes — APScheduler)
DBSCAN clustering runs on all reports last 7 days
→ clusters not covered by alerts = emerging_hotspots table updated
    ↓ (if cluster inside existing alert zone AND report_count >= threshold)
Claude severity assessment: should_upgrade? proposed_severity? confidence?
→ if yes: UPDATE alerts SET severity = proposed, is_new = TRUE
→ re-triggers AI processing: new translations + action cards generated
```

### 6.3 Report data model

```sql
CREATE TABLE community_reports (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    location     GEOMETRY(Point, 4326) NOT NULL,
    hazard_type  TEXT,
    description  TEXT,
    labels       TEXT[] DEFAULT '{}',
    channel      TEXT DEFAULT 'pwa',  -- 'pwa' | 'ussd' | 'whatsapp'
    phone_ref    TEXT,                -- hashed phone reference (privacy)
    reported_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 7. Subscriber Management

### 7.1 Database table

```sql
CREATE TABLE user_subscriptions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number    TEXT NOT NULL UNIQUE,
    channel         TEXT NOT NULL,        -- 'sms' | 'whatsapp' | 'both'
    language        TEXT NOT NULL DEFAULT 'sw',
    livelihood      TEXT NOT NULL DEFAULT 'farmer',
    location        GEOMETRY(Point, 4326),
    preferred_iso2  TEXT,                 -- country code preference
    opted_in        BOOLEAN DEFAULT TRUE,
    opted_in_at     TIMESTAMPTZ DEFAULT NOW(),
    opted_in_via    TEXT,                 -- 'ussd' | 'whatsapp' | 'pwa'
    min_severity    TEXT DEFAULT 'orange', -- only alert if >= this
    last_active     TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index for zone-intersection queries
CREATE INDEX user_subscriptions_location_idx
    ON user_subscriptions USING GIST(location);
```

### 7.2 Opt-in channels

| Channel | How | What's captured automatically |
|---|---|---|
| USSD | Press option in menu | Phone number (from AT session), language, livelihood, country |
| WhatsApp | Conversational flow | Phone number (from message), language, livelihood, country |
| PWA | Web form | Phone number (typed), language, livelihood, GPS location |

**Privacy:** Phone numbers stored hashed for community reports.
Subscription phone numbers stored in plaintext (required for SMS delivery)
but never exposed via any public API endpoint.

### 7.3 Spatial subscriber targeting

```sql
-- When a red alert fires over Kenya:
SELECT phone_number, channel, language, livelihood
FROM user_subscriptions
WHERE opted_in = TRUE
  AND (
    -- GPS-based: their location is inside the alert zone
    ST_Intersects(location, (SELECT geom FROM alerts WHERE id = $alert_id))
    OR
    -- Country-based: they selected Kenya as their region
    preferred_iso2 = ANY(
      SELECT affected_countries FROM alerts WHERE id = $alert_id
    )
  )
  AND CASE min_severity
    WHEN 'green'  THEN TRUE
    WHEN 'orange' THEN (SELECT severity FROM alerts WHERE id=$alert_id) IN ('orange','red')
    WHEN 'red'    THEN (SELECT severity FROM alerts WHERE id=$alert_id) = 'red'
    ELSE TRUE
  END;
```

This is real spatial subscriber targeting. Not list-based broadcast.
Users inside the alert polygon receive alerts. Users outside do not.

---

## 8. Frontend PWA

### 8.1 Tech stack

```
Framework:    React 19 + Vite 8
Styling:      Tailwind v4 CSS-first + shadcn/ui
Icons:        Lucide React (no emojis in UI)
Maps:         Leaflet.js + react-leaflet + leaflet.heat
Routing:      react-router-dom v7
Toast:        Sonner (toast.promise on async actions)
Offline:      Workbox + vite-plugin-pwa service worker
HTTP:         Axios with baseURL from env.apiUrl (src/lib/env.ts)
Types:        @hali/types (shared package, packages/types/)
Dark mode:    Class-based via @custom-variant dark, ThemeProvider
```

### 8.2 Pages

| Route | Page | Primary function |
|---|---|---|
| `/` | AlertFeed | Live alert list, language selector, 60s auto-refresh |
| `/map` | MapView | Leaflet map: alert zones, heatmap, ICPAC layers, emerging hotspots |
| `/actions` | ActionCard | Alert + livelihood + language → AI action steps |
| `/report` | ReportForm | Geolocated hazard report, offline queue |
| `/offline` | OfflinePage | Cached-data fallback |

### 8.3 Map layers (GIS dev owns HaliMap.tsx)

| Layer | Source | Rendering |
|---|---|---|
| Alert zones | `/api/alerts/geojson` | GeoJSON, coloured by severity (red/orange/green) |
| Community heatmap | `/api/reports/heatmap` | Leaflet.heat — orange hotspots |
| Emerging hotspots | `/api/spatial/emerging-hotspots` | Pulsing amber dots |
| Compound risk | `/api/spatial/compound-risk` | Choropleth on IGAD countries |
| ICPAC WMS layers | geoportal.icpac.net/geoserver/wms | Toggleable overlays via layer switcher |
| Temporal slider | `/api/alerts/geojson?from_date=X&to_date=Y` | 30-day playback |
| Click-to-analyse | `/api/spatial/analyse?lat=X&lng=Y` | Side panel intelligence report |

### 8.4 Design system

```css
/* Tailwind v4 @theme tokens */
Primary:    sky blue (#0ea5e9 / --color-primary-500)
Dark bg:    steel blue (#0e1824) — NOT black
Dark cards: deep navy (#162032)
Severity:   red #dc2626 / orange #ea580c / green #16a34a
Font:       Inter, ui-sans-serif

/* Dark mode: class-based */
@custom-variant dark (&:where(.dark, .dark *));
/* Toggle: document.documentElement.classList.toggle('dark') */
```

### 8.5 Offline strategy (Workbox)

| Cache | Strategy | TTL |
|---|---|---|
| Alert feed `/api/alerts` | StaleWhileRevalidate | 5 min |
| GeoJSON `/api/alerts/geojson` | StaleWhileRevalidate | 5 min |
| Action cards | CacheFirst | 24h |
| OSM map tiles | CacheFirst | 7 days |
| App shell | CacheFirst | Indefinite |

**Offline report queue:** `localStorage` key `hali:report_queue`.
Auto-retries on `online` event. Up to 3 attempts per report.

### 8.6 Environment config

```typescript
// src/lib/env.ts — single source of all env reads
export const env = {
    apiUrl:      import.meta.env.VITE_API_URL || 'http://localhost:8000',
    environment: import.meta.env.VITE_ENVIRONMENT || 'development',
} as const;

// No component ever reads import.meta.env directly
```

---

## 9. Admin & Operations

### 9.1 Admin API key auth

All `/api/admin/*` endpoints protected by `X-Admin-Key` header:

```python
# Constant-time comparison — prevents timing attacks
import hmac, hashlib

async def require_admin(key: str | None = Security(api_key_header)) -> None:
    if not settings.admin_auth_enabled:
        return  # dev mode: no key configured
    if not key:
        raise HTTPException(401, "X-Admin-Key required")
    expected = hashlib.sha256(settings.admin_api_key.encode()).digest()
    provided = hashlib.sha256(key.encode()).digest()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(403, "Invalid admin key")
```

```env
ADMIN_API_KEY=<generate: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
```

### 9.2 Admin endpoints

```
POST /api/admin/trigger-ingest              Run all enabled sources
POST /api/admin/trigger-ingest?source=gdacs Run single source
GET  /api/admin/pipeline-status             Config + enabled sources
POST /api/admin/process-backlog             Run AI processing on unprocessed alerts
POST /api/admin/process-alert/{id}          Process single alert through AI
GET  /api/admin/ai-stats                    Provider call counts + ensemble winners
POST /api/admin/run-hotspot-detection       Manual DBSCAN run
GET  /api/admin/subscriber-stats            Count by channel/language/country
```

### 9.3 Structured logging

All logs are JSON via `structlog`. Every ETL step emits:

```json
{
  "level": "info",
  "event": "ingestion.alert_inserted",
  "source": "gdacs",
  "event_id": "1001234",
  "hazard": "flood",
  "severity": "orange",
  "duration_ms": 145.2,
  "timestamp": "2026-07-14T06:01:23Z"
}
```

---

## 10. Database Schema

### 10.1 Core tables

```sql
-- Every external fetch lands here first (dead-letter safety)
raw_ingestion (
    id          UUID PK,
    source      TEXT,           -- 'gdacs'|'chirps'|'gfs'|'glofas'|'icpac'
    fetched_at  TIMESTAMPTZ,
    raw_payload JSONB,
    status      TEXT            -- 'pending'|'processing'|'processed'|'failed'
)

-- Normalised alerts with PostGIS geometry
alerts (
    id                   UUID PK,
    raw_id               UUID FK → raw_ingestion,
    hazard_type          TEXT,   -- 'flood'|'drought'|'locust'|'cyclone'|'health'
    severity             TEXT,   -- 'green'|'orange'|'red'
    geom                 GEOMETRY(MultiPolygon, 4326),
    affected_countries   TEXT[],
    population_exposed   INTEGER DEFAULT 0,
    is_new               BOOLEAN DEFAULT TRUE,
    valid_from           TIMESTAMPTZ,
    valid_to             TIMESTAMPTZ,
    dedup_hash           TEXT UNIQUE,
    processed_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ
)

-- AI-generated translations
alert_translations (
    id         UUID PK,
    alert_id   UUID FK → alerts,
    language   TEXT,   -- 'sw'|'so'|'am'|'om'|'ar'|'en'
    headline   TEXT,
    body       TEXT,
    audio_url  TEXT,
    UNIQUE(alert_id, language)
)

-- AI-generated action cards
action_cards (
    id         UUID PK,
    alert_id   UUID FK → alerts,
    livelihood TEXT,   -- 'farmer'|'pastoralist'|'fisherfolk'|'urban'
    language   TEXT,
    steps      TEXT,
    UNIQUE(alert_id, livelihood, language)
)

-- Community ground-truth reports
community_reports (
    id           UUID PK,
    location     GEOMETRY(Point, 4326),
    hazard_type  TEXT,
    description  TEXT,
    labels       TEXT[] DEFAULT '{}',
    channel      TEXT DEFAULT 'pwa',
    reported_at  TIMESTAMPTZ
)

-- IGAD member state boundaries
countries (
    id    SERIAL PK,
    name  TEXT,
    iso2  TEXT UNIQUE,
    geom  GEOMETRY(MultiPolygon, 4326)
)

-- Subscriber list for SMS/WhatsApp
user_subscriptions (
    id              UUID PK,
    phone_number    TEXT UNIQUE,
    channel         TEXT,   -- 'sms'|'whatsapp'|'both'
    language        TEXT DEFAULT 'sw',
    livelihood      TEXT DEFAULT 'farmer',
    location        GEOMETRY(Point, 4326),
    preferred_iso2  TEXT,
    opted_in        BOOLEAN DEFAULT TRUE,
    opted_in_at     TIMESTAMPTZ,
    opted_in_via    TEXT,   -- 'ussd'|'whatsapp'|'pwa'
    min_severity    TEXT DEFAULT 'orange',
    last_active     TIMESTAMPTZ
)

-- DBSCAN-detected emerging hotspots
emerging_hotspots (
    id              UUID PK,
    location        GEOMETRY(Point, 4326),
    report_count    INTEGER,
    dominant_hazard TEXT,
    confidence      FLOAT,
    first_reported  TIMESTAMPTZ,
    detected_at     TIMESTAMPTZ DEFAULT NOW()
)
```

### 10.2 Spatial indexes

```sql
CREATE INDEX alerts_geom_idx             ON alerts            USING GIST(geom);
CREATE INDEX alerts_hazard_severity_idx  ON alerts            (hazard_type, severity);
CREATE INDEX alerts_is_new_idx           ON alerts            (is_new) WHERE is_new = TRUE;
CREATE INDEX community_reports_geom_idx  ON community_reports USING GIST(location);
CREATE INDEX countries_geom_idx          ON countries         USING GIST(geom);
CREATE INDEX user_subscriptions_loc_idx  ON user_subscriptions USING GIST(location);
CREATE INDEX emerging_hotspots_geom_idx  ON emerging_hotspots USING GIST(location);
```

---

## 11. API Reference

### Public endpoints (no auth)

```
GET  /                                    Root + version
GET  /health                              DB + PostGIS status
GET  /ready                               Readiness check

GET  /api/alerts                          Alert feed
     ?lang=sw &lat=X &lng=Y &limit=20

GET  /api/alerts/geojson                  Leaflet map data
     ?bbox=21,-12,52,24 &lang=sw
     &severity=red &hazard=flood
     &from_date=X &to_date=Y

GET  /api/alerts/{id}/action-card         Action card (on-demand generation)
     ?livelihood=farmer &lang=sw

POST /api/reports                         Submit community report
     {lat, lng, hazard_type, description}

GET  /api/reports/heatmap?days=7          Heatmap GeoJSON points

GET  /api/spatial/compound-risk           Risk choropleth per country
GET  /api/spatial/analyse?lat=X&lng=Y    Click-to-analyse intelligence
GET  /api/spatial/emerging-hotspots       DBSCAN hotspot layer

GET  /whatsapp                            Meta webhook verification
POST /whatsapp                            Incoming WhatsApp messages
POST /ussd                                Africa's Talking USSD callback
```

### Admin endpoints (X-Admin-Key header required)

```
POST /api/admin/trigger-ingest[?source=X]  Manual ingestion trigger
GET  /api/admin/pipeline-status            Config + source status
POST /api/admin/process-backlog            AI process unprocessed alerts
POST /api/admin/process-alert/{id}         Process single alert
GET  /api/admin/ai-stats                   Provider call counts
POST /api/admin/run-hotspot-detection      Manual DBSCAN run
GET  /api/admin/subscriber-stats           Subscription analytics
```

---

## 12. Infrastructure

### 12.1 Railway services

```
Workspace: Ronza
Project:   chic-exploration

Services:
  backend   — FastAPI app (Dockerfile: apps/backend/Dockerfile)
              python:3.12-slim, multi-stage build
              CMD: uvicorn hali.main:app --host 0.0.0.0 --port $PORT
              Healthcheck: GET /health

  frontend  — Caddy serving React PWA (Dockerfile: apps/frontend/Dockerfile)
              node:22-slim build → caddy:2-alpine runtime
              Caddyfile: try_files {path} /index.html (SPA routing)
              Healthcheck: GET /

  PostGIS   — PostgreSQL 16.14 + PostGIS 3.7
              IMPORTANT: Use PostGIS template, NOT default Postgres template
```

### 12.2 CI/CD — GitHub Actions

```yaml
# .github/workflows/deploy.yml
# Trigger: push to main

jobs:
  test-backend:   # PostGIS service container + pytest + ruff
  test-frontend:  # nx run frontend:build
  deploy-backend: # needs: test-backend → railway up --service backend
  deploy-frontend:# needs: test-frontend → railway up --service frontend
                  # passes VITE_API_URL build arg
```

**GitHub Secrets required:**
```
RAILWAY_TOKEN          — railway token create --name github-actions-hali
RAILWAY_BACKEND_URL    — https://xxx.railway.app
```

### 12.3 Monorepo structure

```
hali/                              Nx 23 monorepo
├── apps/
│   ├── backend/                   FastAPI application
│   │   ├── src/hali/
│   │   │   ├── main.py            App + CORS + lifespan
│   │   │   ├── config.py          pydantic-settings (all env vars)
│   │   │   ├── database.py        asyncpg pool + get_db dependency
│   │   │   ├── dependencies/      admin_auth.py
│   │   │   ├── routers/           alerts, reports, ussd, whatsapp, admin, health
│   │   │   ├── ingestion/         base, models, loader, normaliser, gdacs,
│   │   │   │                      chirps, gfs, glofas, icpac, scheduler
│   │   │   └── ai/                processor, router, scorer, prompts,
│   │   │                          context, models, spatial_clustering
│   │   ├── tests/                 29+ tests (ingestion + AI + admin auth)
│   │   └── Dockerfile
│   └── frontend/                  React PWA
│       ├── src/
│       │   ├── lib/               env.ts, api.ts, offlineQueue.ts, theme.tsx
│       │   ├── hooks/             useAlerts, useLocation, useOnlineStatus,
│       │   │                      useReportQueue
│       │   ├── components/        HaliMap, AlertCard, SeverityBadge,
│       │   │                      LanguageSelector, BottomNav, OfflineBanner,
│       │   │                      ThemeToggle, ui/ (shadcn)
│       │   └── pages/             AlertFeed, MapView, ActionCard,
│       │                          ReportForm, Offline
│       ├── Caddyfile
│       └── Dockerfile
├── packages/types/src/index.ts    Shared TypeScript types (@hali/types)
├── sql/migrations/                001_enable_postgis, 002_create_tables,
│                                  003_seed_igad_countries
├── .github/workflows/deploy.yml
├── railway.toml
└── nx.json
```

### 12.4 Python dependencies (key packages)

```toml
fastapi = "^0.139.0"
uvicorn = {extras = ["standard"], version = "^0.49.0"}
asyncpg = "^0.31.0"
httpx = "^0.28.1"
anthropic = "^0.116.0"
apscheduler = "^3.11.3"
shapely = "^2.1.2"
rasterio = "^1.5.0"
pydantic-settings = "^2.14.2"
structlog = "^25.0"
tenacity = "^9.0"
scikit-learn = "^1.5"   # DBSCAN spatial clustering
numpy = "^2.0"
xarray = "^2025.1"      # NetCDF (ICPAC, GloFAS)
cfgrib = "^0.9"         # GRIB2 (GloFAS)
cdsapi = "^0.7"         # GloFAS CDS
google-generativeai = "^0.8"  # Gemini fallback
groq = "^0.12"          # Groq fallback
africastalking = "^2.0.2"
```

---

## 13. HALI Moat — Differentiation Matrix

> This section documents what HALI does that no existing system in the
> IGAD early warning ecosystem currently does.

### 13.1 Feature comparison

| Capability | HALI | Status |
|---|---|---|
| Zero-registration access | Any phone, any user, no account needed | ✅ Core design |
| Automated multi-source ingestion | GDACS + CHIRPS + GFS + GloFAS + ICPAC, no human | ✅ Built |
| AI multilingual translation (6 languages) | Claude ensemble, Grade 5 reading level | ✅ Built |
| Multi-model AI ensemble | Claude + Gemini + Groq, clarity-scored | ✅ Built |
| Livelihood-specific action cards | 4 livelihoods × 6 languages × per alert | ✅ Built |
| Seasonal context injection | Long rains / short rains / dry season framing | ✅ Built |
| USSD interactive intelligence | Live PostGIS queries, not static text | ✅ Scaffolded |
| WhatsApp conversational alerts | Meta Cloud API, opt-in conversation | ✅ Scaffolded |
| SMS spatial targeting | Subscribers inside alert zone geometry | ✅ Designed |
| Community ground truth → severity | Claude assesses reports, upgrades alert | ✅ Built |
| DBSCAN emerging hotspot detection | Detects events before official alerts | ✅ Built |
| Population exposure per alert | WorldPop API, cached per alert | ✅ Designed |
| Compound risk index | PostGIS spatial analysis per country | ✅ Designed |
| ICPAC WMS integration | Judges' own data inside HALI's map | ✅ Designed |
| Click-to-analyse spatial intelligence | Live PostGIS on map click | ✅ Designed |
| Temporal 30-day animation | Alert evolution playback | ✅ Designed |
| PostGIS spatial subscriber targeting | Zone intersection, not list broadcast | ✅ Designed |
| Dead-letter ETL tracking | Every raw record tracked, replayable | ✅ Built |
| Admin API key auth | Constant-time HMAC, not config flag | ✅ Built |
| Offline PWA | Workbox caching, report queue | ✅ Built |
| GitHub Actions CI/CD | Tests → Railway deploy on push | ✅ Built |

### 13.2 The moat in one sentence

> **HALI is the only system in the IGAD region that ingests satellite
> data automatically, translates it into 6 languages with AI, generates
> livelihood-specific action guidance, detects emerging events before
> official systems, and delivers all of it to any phone — with no
> registration, no subscription, no intermediary.**

### 13.3 What remains to build

| Feature | Owner | Priority |
|---|---|---|
| USSD opt-in → SMS subscription | Martin (backend) | Critical |
| WhatsApp conversational opt-in | Martin (backend) | Critical |
| Outbound alert broadcast (SMS + WA) | Martin (backend) | Critical |
| WorldPop population exposure | Martin (backend) | High |
| DBSCAN scheduler job (every 30min) | Martin (backend) | High |
| `/api/spatial/compound-risk` endpoint | Martin (backend) | High |
| `/api/spatial/analyse` endpoint | Martin (backend) | High |
| `/api/spatial/emerging-hotspots` endpoint | Martin (backend) | High |
| ICPAC WMS layer switcher | GIS dev (frontend) | High |
| Emerging hotspot layer (pulsing dots) | GIS dev (frontend) | High |
| Compound risk choropleth | GIS dev (frontend) | High |
| Click-to-analyse side panel | GIS dev (frontend) | High |
| Temporal animation slider | GIS dev (frontend) | Medium |
| WhatsApp template message setup | Martin (Meta console) | Critical |
| Africa's Talking USSD service code | Martin (AT console) | Critical |
| `emerging_hotspots` DB table | Martin (migration) | High |
| `user_subscriptions` DB table | Martin (migration) | Critical |
| `alerts.population_exposed` column | Martin (migration) | High |

---

*HALI — Transforming satellite intelligence into last-mile action.*
*Built for IGAD Hackathon 2026 · Deadline: July 31, 2026 @ 17:00 EAT*
