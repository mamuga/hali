# HALI — Final Sprint: Reporting E2E + Domain Expansion + GIS Overhaul

You are a senior full-stack + GIS engineering team finishing HALI for the
IGAD Hackathon 2026. **Deadline: July 31, 2026 @ 17:00 EAT. Today is July 28.
Three days remain.** Work in the priority order given. Do not gold-plate.
Every phase ends with a verification gate — run it, show output, fix failures
before moving on.

Repo: `/home/muga/hali` · Backend: `apps/backend/src/hali/` ·
Frontend: `apps/frontend/src/` · DB: Railway PostGIS (live) ·
Live app: https://frontend-production-ba31.up.railway.app/

Research context driving these changes (from ICPAC's own platforms):
- East Africa Hazards Watch overlays hazards with **population/vulnerability**
  data and offers multiple basemaps → we ingest WorldPop for real.
- ICPAC Thresholds Watch does **subnational spatially-variable triggers** →
  our DBSCAN hotspots + severity escalation is the community-driven analogue;
  frame it as "community-triggered anticipatory action."
- ICPAC's own website language switcher includes **French** — Husika's
  Djibouti broadcasts are in French — HALI currently has no French. Fix.

---

## PRIORITY ORDER (3 days)

| Phase | What | Priority | Est. |
|---|---|---|---|
| 1 | Reporting service E2E verification + fixes | P0 | 0.5 day |
| 2 | Languages, livelihoods, hazards expansion | P0 | 0.5 day |
| 3 | Map overhaul: IGAD-only, no-fill boundaries, basemaps | P0 | 0.5 day |
| 4 | Draw-polygon spatial query | P1 | 0.5 day |
| 5 | WorldPop real ingestion (pop_grid table) | P1 | 0.5 day |
| 6 | Commit, deploy, Notion update | P0 | 0.25 day |

---

# PHASE 1 — Reporting Service: End-to-End Verification & Fixes

The reporting loop is HALI's core moat (community ground truth → intelligence).
Verify every link in the chain actually works, then fix what doesn't.

## 1.1 Map the current state first

```bash
cd /home/muga/hali
cat apps/backend/src/hali/routers/reports.py
cat apps/backend/src/hali/services/reports.py 2>/dev/null
grep -rn "community_reports" apps/backend/src/hali --include="*.py" | grep -v test | head -30
grep -rn "classify_report\|labels" apps/backend/src/hali/ai/processor.py | head -10
cat apps/frontend/src/pages/ReportForm.tsx | head -60
```

## 1.2 The full chain to verify

```
CHANNEL          → STORE                → CLASSIFY        → AGGREGATE           → ESCALATE
PWA form (GPS)   → community_reports   → Claude labels[] → heatmap endpoint    → DBSCAN hotspot
USSD (no GPS)    → community_reports   → Claude labels[] → report count        → severity upgrade
WhatsApp (text)  → community_reports   → Claude labels[] → click-to-analyse    → alert is_new=TRUE
Offline queue    → localStorage → retry → same as PWA
```

## 1.3 Live verification script — run against local backend + Railway DB

```bash
cd /home/muga/hali && npx nx run backend:serve & sleep 8
API=http://localhost:8000
ADMIN_KEY=$(grep '^ADMIN_API_KEY=' .env | cut -d= -f2-)

echo "── 1. PWA-channel report (with GPS, inside an alert zone) ──"
# Use Lodwar, Turkana coordinates (Husika pilot region — good demo data)
REPORT_ID=$(curl -s -X POST "$API/api/reports" -H "Content-Type: application/json" \
  -d '{"lat":3.1191,"lng":35.5973,"hazard_type":"flood","description":"Maji yamejaa barabara kuu ya Lodwar, magari hayawezi kupita"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))")
echo "Report ID: $REPORT_ID"
[ -n "$REPORT_ID" ] && echo "✅ PWA report stored" || echo "❌ FAILED"

echo "── 2. NLP classification fired (async — wait then check) ──"
sleep 8
psql $(grep '^DATABASE_URL_RAW=' .env | cut -d= -f2-) -c \
  "SELECT id, hazard_type, labels, channel FROM community_reports WHERE id='$REPORT_ID';"
# EXPECT: labels != '{}' (e.g. {flood,road_blocked}). If labels empty and
# AI keys are set → the background task is broken. Fix: check BackgroundTasks
# wiring in routers/reports.py and settings.ai_enabled gate.

echo "── 3. USSD-channel report ──"
curl -s -X POST "$API/ussd" \
  -d "sessionId=t1&serviceCode=*384#&phoneNumber=%2B254711000111&text=2*1" | head -c 200
# EXPECT: END confirmation. Then verify row exists with channel='ussd':
psql $(grep '^DATABASE_URL_RAW=' .env | cut -d= -f2-) -c \
  "SELECT channel, count(*) FROM community_reports GROUP BY channel;"

echo "── 4. WhatsApp-channel report ──"
# Simulate Meta webhook POST (signature check passes in dev mode w/o secret)
curl -s -X POST "$API/whatsapp" -H "Content-Type: application/json" -d '{
  "entry":[{"changes":[{"value":{"messages":[{
    "from":"254722000222","type":"text",
    "text":{"body":"report mafuriko kwenye daraja la Kalokol"}}]}}]}]}'
# EXPECT: {"status":"ok"} and a new community_reports row, channel='whatsapp'

echo "── 5. Heatmap aggregation ──"
curl -s "$API/api/reports/heatmap?days=7" | python3 -c \
  "import json,sys; print('points:', len(json.load(sys.stdin)['features']))"
# EXPECT: >= number of reports just submitted

echo "── 6. DBSCAN pickup (submit 3 clustered reports, run detection) ──"
for i in 1 2 3; do
  curl -s -X POST "$API/api/reports" -H "Content-Type: application/json" \
    -d "{\"lat\":3.1$i,\"lng\":35.6$i,\"hazard_type\":\"flood\",\"description\":\"flooding near Lodwar site $i\"}" > /dev/null
done
curl -s -X POST "$API/api/admin/run-hotspot-detection" -H "X-Admin-Key: $ADMIN_KEY" \
  | python3 -m json.tool
curl -s "$API/api/spatial/emerging-hotspots" | python3 -c \
  "import json,sys; print('hotspots:', len(json.load(sys.stdin)['features']))"
# EXPECT: >=1 hotspot IF no official alert covers Lodwar; 0 if covered (also valid — say which)

echo "── 7. Severity escalation path ──"
# Find an active alert, submit GROUND_TRUTH_UPGRADE_THRESHOLD reports inside its geom,
# re-process the alert, verify Claude assessment ran (check logs for
# 'processor.severity_upgraded' or the reasoning in response)
kill %1
```

## 1.4 Fix list (apply whichever fail)

- **Labels never populate:** `BackgroundTasks` not wired, or gated on
  `ANTHROPIC_API_KEY` instead of `settings.ai_enabled`. Fix gate.
- **USSD report has no location:** store country centroid from the user's
  menu-selected country instead of `POINT(0 0)` — `POINT(0 0)` is in the
  Atlantic and poisons DBSCAN + heatmap. Add `channel` + centroid lookup.
- **WhatsApp report same issue:** if no location shared, use the subscriber's
  `preferred_iso2` centroid; tag `location_precision='country'` column
  (add TEXT column, default `'gps'`) and **exclude non-gps reports from DBSCAN**.
- **Missing endpoints:** if `/api/admin/run-hotspot-detection` or
  `/api/spatial/emerging-hotspots` don't exist yet, implement them now from
  HALI_FEATURES_TECHNICAL_SPECS.md §4.5 (DBSCAN code is there in full).
- **Offline queue:** build frontend, open devtools → Network offline →
  submit report → verify localStorage `hali:report_queue` → go online →
  verify auto-retry + sonner toast.

**Gate:** all 7 checks pass (or documented-valid), pytest still green.

---

# PHASE 2 — Domain Expansion: Languages, Livelihoods, Hazards

## 2.1 Languages — add 4 (national languages we missed)

| Code | Language | Why |
|---|---|---|
| `fr` | French | Djibouti official language; ICPAC's own site has it; Husika's Djibouti broadcasts are French |
| `ti` | Tigrinya | Eritrea + northern Ethiopia (~9M speakers) |
| `lg` | Luganda | Uganda's largest local language |
| `aa` | Afar | Djibouti + Afar region Ethiopia (drought epicentre) |

Final set: `sw, so, am, om, ar, en, fr, ti, lg, aa` (10).

**Low-resource caveat (handle explicitly):** LLM quality for `ti`, `lg`, `aa`
is weaker. The ensemble clarity scorer already guards this — additionally:
in `ai/router.py`, if the winning output for these languages scores below
`AI_MIN_CLARITY_SCORE`, fall back to storing the Swahili (`lg`→`sw`,
`aa`/`ti`→`am` script-adjacent? No — fall back to `en`) version with a
`fallback_language` marker. Never serve empty.

**Changes:**
1. `ai/prompts.py` → `LANGUAGE_NAMES` add: `"fr": "French (Français)",
   "ti": "Tigrinya (ትግርኛ)", "lg": "Luganda", "aa": "Afar (Qafar af)"`.
   For `ti` enforce Ge'ez script in prompt (same rule as Amharic).
2. `ai/processor.py` → `LANGUAGES` list = all 10 minus `en` for translations;
   action cards keep 10-language on-demand (do NOT pre-generate 10×7=70
   cards per alert — pre-generate only `sw, en, fr`; rest on-demand).
3. `packages/types/src/index.ts` → `Language` union add 4 codes.
4. `LanguageSelector.tsx` → add entries (native labels above).
5. USSD menu language step → add French option (Djibouti demo!).
6. Backfill: do NOT reprocess all 57 alerts × 10 langs (rate limits).
   The on-demand endpoints cover it. Only regenerate `fr` for the 5 most
   recent red/orange alerts: loop `POST /api/admin/process-alert/{id}`.

## 2.2 Livelihoods — add 3

| Value | Who | Why |
|---|---|---|
| `agropastoralist` | Mixed crop-livestock | The dominant livelihood in the IGAD borderlands — its advice genuinely differs from both farmer and pastoralist |
| `trader` | Market vendors, transporters | Roads/markets closures hit them first |
| `displaced` | Refugees/IDPs (Kakuma, Dadaab, camps) | 4M+ displaced in IGAD region; camp-specific guidance (no land, no livestock, aid-dependent) |

Final: `farmer, pastoralist, agropastoralist, fisherfolk, urban, trader, displaced` (7).

**Changes:** `ai/prompts.py` `LIVELIHOOD_CONTEXT` (write real context strings —
e.g. displaced: "people living in displacement camps or informal settlements,
dependent on aid distribution, without land or livestock, with limited freedom
of movement"), `ai/context.py` country map (SS→displaced-heavy note stays
pastoralist), types union, ActionCard page buttons, USSD livelihood menu
(7 options fits: 182-char pages — verify, else split to 2 pages).
Pre-generation stays 4 core livelihoods; new 3 are on-demand only.

## 2.3 Hazards — add 4

| Value | Why | Source signal |
|---|---|---|
| `heatwave` | Djibouti/Sudan killer; Husika's own broadcasts were heatwaves | GFS temp threshold (later); manual/community now |
| `landslide` | Mt Elgon Uganda, Ethiopian highlands — recurring mass-casualty | GDACS has no code; community reports + CHIRPS extreme rain proxy |
| `wildfire` | GDACS `WF` currently mapped to `other` — remap | GDACS WF |
| `epidemic` | Cholera outbreaks post-flood; distinct from generic `health` | Community reports; keep `health` for general |

Final: `flood, drought, locust, cyclone, heatwave, landslide, wildfire, epidemic, health, other` (10).

**Changes:** `ingestion/normaliser.py` → `GDACS_HAZARD_MAP["WF"] = HazardType.WILDFIRE`,
add enum values in `ingestion/models.py`, types union, ReportForm hazard chips
(10 chips wraps fine), AlertCard/HaliMap icon maps (Lucide: `Thermometer`
heatwave, `Mountain` landslide, `Flame` wildfire, `Biohazard` epidemic),
prompt hazard vocab in scorer `HAZARD_KEYWORDS` (add: joto/heat/chaleur,
maporomoko/landslide, moto/fire/incendie, kipindupindu/cholera/épidémie).
No DB migration needed (hazard_type is TEXT).

**Gate:**
```bash
poetry run pytest tests/ -v 2>&1 | tail -5
poetry run python -c "
from hali.ai.prompts import LANGUAGE_NAMES, LIVELIHOOD_CONTEXT
assert len(LANGUAGE_NAMES)==10 and 'fr' in LANGUAGE_NAMES
assert len(LIVELIHOOD_CONTEXT)==7 and 'displaced' in LIVELIHOOD_CONTEXT
print('domain expansion OK')"
# Live: French action card on-demand
curl -s "$API/api/alerts/{first_alert_id}/action-card?livelihood=displaced&lang=fr" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['steps'][:80])"
```

---

# PHASE 3 — Map Overhaul (P0 — this is what GIS judges see first)

## 3.1 Fix the root cause: bbox country geometries

The seeded countries are **bounding boxes**, which is why (a) filled rectangles
block every layer underneath, (b) the map looks amateur to GIS professionals,
(c) choropleth/mask can't work. Replace with real Natural Earth boundaries.

Create `sql/migrations/004_real_country_boundaries.sql` workflow:

```bash
cd /home/muga/hali
mkdir -p tmp && cd tmp
curl -sL -o ne_admin0.zip \
  "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"
unzip -o ne_admin0.zip
# Load ONLY the 8 IGAD countries, reprojected 4326, into a staging table
ogr2ogr -f PostgreSQL PG:"$(grep '^DATABASE_URL_RAW=' ../.env | cut -d= -f2-)" \
  ne_50m_admin_0_countries.shp -nln ne_staging -overwrite -t_srs EPSG:4326 \
  -where "ISO_A2 IN ('KE','ET','SO','UG','DJ','ER','SD','SS') OR ISO_A2_EH IN ('KE','ET','SO','UG','DJ','ER','SD','SS')"
# Swap geometries in place (keeps our iso2/name/ids stable)
psql "$(grep '^DATABASE_URL_RAW=' ../.env | cut -d= -f2-)" <<'SQL'
UPDATE countries c SET geom = ST_Multi(ST_MakeValid(s.wkb_geometry))
FROM ne_staging s
WHERE c.iso2 = COALESCE(NULLIF(s.iso_a2,'-99'), s.iso_a2_eh);
DROP TABLE ne_staging;
-- Verify: areas must differ wildly from bboxes now
SELECT iso2, ROUND((ST_Area(geom::geography)/1e6)::numeric) AS km2 FROM countries ORDER BY iso2;
SQL
```
Somalia note: Natural Earth may split Somaliland — if `SO` area looks small,
also merge `SOL` geometry into SO with `ST_Union`. Check and handle.
Save the psql part as migration 004 (documented as "run via ogr2ogr workflow").

## 3.2 New endpoint: `GET /api/countries/geojson`

```python
# routers/spatial.py — simplified boundaries for frontend (mask + outlines)
@router.get("/countries/geojson")
async def countries_geojson(db=Depends(get_db)):
    rows = await db.fetch("""
        SELECT iso2, name,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.02)) AS gj
        FROM countries""")
    return {"type":"FeatureCollection","features":[
        {"type":"Feature","geometry":json.loads(r["gj"]),
         "properties":{"iso2":r["iso2"],"name":r["name"]}} for r in rows]}
```

## 3.3 Frontend map: IGAD-only view + hollow boundaries + basemaps

Update `HaliMap.tsx`:

```tsx
// ── A. Basemap switcher ──────────────────────────────────────────
const baseMaps = {
  'Streets (OSM)': L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    { attribution: '© OpenStreetMap', maxZoom: 18 }),
  'Satellite': L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Esri, Maxar, Earthstar Geographics', maxZoom: 18 }),
  'Topographic': L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    { attribution: '© OpenTopoMap (CC-BY-SA)', maxZoom: 17 }),
  'Terrain / Elevation': L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}',
    { attribution: 'Esri', maxZoom: 13 }),
};
baseMaps['Streets (OSM)'].addTo(map);

// ── B. Lock the viewport to IGAD ─────────────────────────────────
const IGAD_BOUNDS = L.latLngBounds([-5, 20], [25, 52]);
map.setMaxBounds(IGAD_BOUNDS.pad(0.15));
map.options.minZoom = 4;
map.fitBounds(IGAD_BOUNDS);

// ── C. Grey-out mask outside IGAD + hollow country outlines ─────
const cg = await fetch(`${env.apiUrl}/api/spatial/countries/geojson`).then(r=>r.json());
// world ring with IGAD holes → everything outside IGAD dimmed
const world = [[-90,-180],[-90,180],[90,180],[90,-180]];
const holes = cg.features.flatMap((f:any) =>
  (f.geometry.type==='MultiPolygon'? f.geometry.coordinates : [f.geometry.coordinates])
    .map((poly:any)=> poly[0].map(([lng,lat]:number[])=>[lat,lng])));
L.polygon([world, ...holes] as any, {
  stroke:false, fillColor:'#0e1824', fillOpacity:0.55, interactive:false
}).addTo(map);
// HOLLOW boundaries — the fix for "bbox fill blocks layers"
const boundaries = L.geoJSON(cg, {
  style: { fill:false, color:'#38bdf8', weight:1.5, opacity:0.9, dashArray:'0' },
  interactive:false,
}).addTo(map);

// ── D. Overlay control (alert zones, heatmap, hotspots, ICPAC WMS) ─
L.control.layers(baseMaps, {
  'IGAD Boundaries': boundaries,
  'Alert Zones': alertLayerRef.current,      // existing
  'Community Heatmap': heatLayerRef.current, // existing
  'Emerging Hotspots': hotspotLayer,         // existing/new
  // ICPAC WMS layers from spec §4.2 go here too
}, { collapsed:false, position:'topright' }).addTo(map);
```

Also: the compound-risk choropleth should now use the **real** country
shapes (it reads from `countries.geom` — no change needed, it just gets
better automatically after 3.1).

**Gate:** open `/map` — outside-IGAD dimmed, real country outlines with NO
fill, 4 switchable basemaps, all overlays visible above boundaries.
Screenshot for the demo.

---

# PHASE 4 — Draw-Polygon Spatial Query (the interactive wow feature)

User draws any polygon → HALI returns every disaster, report, hotspot, and
(after Phase 5) population inside it. This is an AOI (area-of-interest)
analysis — exactly what GIS professionals do daily in QGIS, live in a PWA.

## 4.1 Backend: `POST /api/spatial/query-polygon`

```python
class PolygonQuery(BaseModel):
    geometry: dict  # GeoJSON Polygon from the drawn shape

@router.post("/query-polygon")
async def query_polygon(q: PolygonQuery, db=Depends(get_db)):
    gj = json.dumps(q.geometry)
    alerts = await db.fetch("""
        SELECT a.id, a.hazard_type, a.severity, a.valid_to, a.population_exposed,
               COALESCE(t.headline, a.hazard_type||' alert') AS headline,
               ROUND((ST_Area(ST_Intersection(a.geom,
                 ST_SetSRID(ST_GeomFromGeoJSON($1),4326))::geography)/1e6)::numeric,1) AS overlap_km2
        FROM alerts a
        LEFT JOIN alert_translations t ON t.alert_id=a.id AND t.language='sw'
        WHERE a.valid_to > NOW()
          AND ST_Intersects(a.geom, ST_SetSRID(ST_GeomFromGeoJSON($1),4326))
        ORDER BY CASE a.severity WHEN 'red' THEN 0 WHEN 'orange' THEN 1 ELSE 2 END""", gj)
    reports = await db.fetchrow("""
        SELECT count(*) AS n,
               array_agg(DISTINCT hazard_type) AS hazards
        FROM community_reports
        WHERE reported_at > NOW()-INTERVAL '14 days'
          AND ST_Within(location, ST_SetSRID(ST_GeomFromGeoJSON($1),4326))""", gj)
    hotspots = await db.fetchval("""
        SELECT count(*) FROM emerging_hotspots
        WHERE ST_Within(location, ST_SetSRID(ST_GeomFromGeoJSON($1),4326))""", gj)
    pop = await db.fetchval("""
        SELECT COALESCE(SUM(pop),0)::bigint FROM pop_grid
        WHERE ST_Within(geom, ST_SetSRID(ST_GeomFromGeoJSON($1),4326))""", gj) \
        if await _table_exists(db,'pop_grid') else None
    area = await db.fetchval(
        "SELECT ROUND((ST_Area(ST_SetSRID(ST_GeomFromGeoJSON($1),4326)::geography)/1e6)::numeric,1)", gj)
    return {"area_km2": float(area), "alerts":[dict(r) for r in alerts],
            "report_count": reports["n"], "report_hazards": reports["hazards"] or [],
            "emerging_hotspots": hotspots, "population_estimate": pop}
```

## 4.2 Frontend: leaflet-geoman draw control + results panel

```bash
npm install @geoman-io/leaflet-geoman-free
```

```tsx
import '@geoman-io/leaflet-geoman-free';
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css';

map.pm.addControls({ position:'topleft', drawPolygon:true, drawRectangle:true,
  drawMarker:false, drawCircle:false, drawPolyline:false, drawText:false,
  drawCircleMarker:false, editMode:true, removalMode:true, rotateMode:false });

map.on('pm:create', async (e:any) => {
  const gj = e.layer.toGeoJSON();
  const res = await fetch(`${env.apiUrl}/api/spatial/query-polygon`, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ geometry: gj.geometry }),
  }).then(r=>r.json());
  setAoiResult(res);         // opens the results Sheet (shadcn)
  setAoiLayer(e.layer);      // keep for removal
});
```

Results panel (shadcn `Sheet`, right side): area, alert list with severity
badges + overlap km², report count with hazard tags, hotspot count,
population estimate ("~1.2M people in this area" when Phase 5 lands),
and a "Clear selection" button (`layer.remove()`).

**Gate:** draw a rectangle over northern Kenya → panel lists the live flood
alerts, report counts, and area. Draw over an ocean → clean empty state.

---

# PHASE 5 — WorldPop: Real Ingestion (no placeholder, no per-query API)

Current design calls WorldPop's REST API per alert — that IS a placeholder
pattern. Replace with genuine ingestion: WorldPop 1km UN-adjusted population
rasters for the 8 IGAD countries → sampled into a PostGIS `pop_grid` table →
all exposure computed locally with zonal statistics. This matches Hazards
Watch's "overlay hazards with socio-economic data" approach and makes
population work offline, in polygon queries, and in compound risk.

## 5.1 New ETL adapter (fits the existing BaseAdapter pattern)

`ingestion/worldpop.py` — `ENABLE_WORLDPOP=false` default; it is a
**one-shot/quarterly** adapter (static data), triggered manually:
`POST /api/admin/trigger-ingest?source=worldpop`.

```python
# Download URLs (verify listing first with a HEAD request):
# https://data.worldpop.org/GIS/Population/Global_2000_2020_1km_UNadj/2020/{ISO3}/{iso3}_ppp_2020_1km_Aggregated_UNadj.tif
ISO2_TO_ISO3 = {"KE":"KEN","ET":"ETH","SO":"SOM","UG":"UGA",
                "DJ":"DJI","ER":"ERI","SD":"SDN","SS":"SSD"}

# transform(): read GeoTIFF with rasterio, iterate pixels where pop > 1,
# batch-insert (lng,lat,pop) — at 1km that's ~2-4M points for the region.
# TOO MANY for 3 days. Aggregate 5x5 pixel blocks (≈5km cells) instead:
import numpy as np, rasterio
with rasterio.open(tif_path) as src:
    data = src.read(1); data[data < 0] = 0
    B = 5
    h, w = (data.shape[0]//B)*B, (data.shape[1]//B)*B
    blocks = data[:h,:w].reshape(h//B, B, w//B, B).sum(axis=(1,3))
    # centre coords per block via src.transform * (col*B+B/2, row*B+B/2)
# → ~100-160k rows total for 8 countries. Manageable.
```

```sql
-- migration 005
CREATE TABLE IF NOT EXISTS pop_grid (
    id      BIGSERIAL PRIMARY KEY,
    iso2    TEXT NOT NULL,
    geom    GEOMETRY(Point, 4326) NOT NULL,
    pop     INTEGER NOT NULL,           -- people in ~5km cell
    year    INTEGER NOT NULL DEFAULT 2020,
    source  TEXT NOT NULL DEFAULT 'worldpop_1km_unadj'
);
CREATE INDEX pop_grid_geom_idx ON pop_grid USING GIST(geom);
```

Loader: `COPY`-style batch insert via `conn.copy_records_to_table` (asyncpg),
per-country delete-then-insert for idempotency (dedup via `(iso2, year)`).

## 5.2 Rewire population_exposed to local zonal stats

```python
# ai/processor.py or a post-load hook in ingestion/loader.py:
pop = await conn.fetchval("""
    SELECT COALESCE(SUM(pop),0)::bigint FROM pop_grid
    WHERE ST_Intersects(geom, (SELECT geom FROM alerts WHERE id=$1))""", alert_id)
await conn.execute("UPDATE alerts SET population_exposed=$1 WHERE id=$2", pop, alert_id)
```
Backfill all active alerts with one admin call:
`POST /api/admin/recompute-population` (add it — 10-line loop).
Compound-risk query: multiply score by `log(1+pop_exposed)` for a
population-weighted risk index (subnational-flavour, Thresholds-Watch-style).

**Fallback if downloads are slow on Railway:** run the adapter locally
against the Railway DB (it's a one-shot load), commit nothing but the code.

**Gate:**
```bash
psql $DB -c "SELECT iso2, count(*), SUM(pop) FROM pop_grid GROUP BY iso2 ORDER BY iso2;"
# Sanity: KE ≈ 50-55M, ET ≈ 115-120M, SO ≈ 15-17M (2020 UN-adjusted)
curl -s "$API/api/alerts/geojson?lang=sw" | python3 -c "
import json,sys; f=json.load(sys.stdin)['features']
print([p['properties'].get('population_exposed') for p in f][:5])"
# EXPECT: real non-zero numbers on alerts intersecting land
```

---

# PHASE 6 — Ship It

```bash
cd /home/muga/hali/apps/backend && poetry run pytest tests/ -v 2>&1 | tail -5 \
  && poetry run ruff check src/
cd /home/muga/hali && npx nx run frontend:build 2>&1 | tail -3

git add -A && git commit -m "feat(final): reporting E2E fixes, 10 languages, 7 livelihoods, 10 hazards, IGAD-only map with real NE boundaries + 4 basemaps, draw-polygon AOI analysis, WorldPop pop_grid ingestion + local zonal stats

- Reporting: channel column, country-centroid fallback for USSD/WhatsApp,
  location_precision guard for DBSCAN, verified 7-step E2E chain
- Languages: +fr +ti +lg +aa with low-resource clarity fallback
- Livelihoods: +agropastoralist +trader +displaced
- Hazards: +heatwave +landslide +wildfire +epidemic; GDACS WF remapped
- Map: Natural Earth admin-0 (migration 004), hollow boundaries,
  outside-IGAD mask, maxBounds, basemap switcher (OSM/Satellite/Topo/Terrain)
- AOI: POST /api/spatial/query-polygon + leaflet-geoman draw controls
- WorldPop: ingestion adapter (5km aggregated pop_grid, migration 005),
  population_exposed now local PostGIS zonal stats, pop-weighted compound risk"
git push origin main
# CI deploys both services. Then verify live:
curl -s https://<backend>.railway.app/health | python3 -m json.tool
```

Update Notion tracker: mark Phase 1-5 tasks done, add any deferred items
(e.g. GFS heatwave thresholds) to a "post-hackathon" section.

---

## Borrowed-from-ICPAC framing for the demo (write into Devpost too)

1. **Hazards Watch** overlays hazards with population vulnerability → HALI
   ingests WorldPop into PostGIS and computes exposure live, even for
   user-drawn polygons.
2. **Thresholds Watch** does subnational forecast-based triggers → HALI adds
   the missing layer: **community-triggered anticipatory action** — DBSCAN
   clusters of ground reports escalate severity before official thresholds trip.
3. **ICPAC's own language list** includes French → HALI speaks all of it,
   AI-generated, plus Tigrinya, Luganda, and Afar that nobody serves.
4. Their basemap/boundary UX → matched (4 basemaps, real admin-0, layer
   control) and exceeded (draw-your-own AOI analysis in a PWA).
