# HALI — Gap Analysis & Implementation Plan

> Derived from a full codebase audit against `HALI_FEATURES_TECHNICAL_SPECS.md`.
> Audit date: **2026-07-28** · Submission deadline: **2026-07-31 @ 17:00 EAT** (~3.5 days)
> Branch: `main` · Backend `apps/backend/src/hali` · Frontend `apps/frontend/src`

## Progress

- **Phase 0 — DONE** (2026-07-28). D7 migration path fixed and verified inside the
  Docker image; migration 004 applied to Railway production (data intact: 24 alerts,
  351 action cards); `scikit-learn`/`numpy` added, `nltk`/`asyncio-throttle` dropped.
- **Phase 1 — DONE** (2026-07-28). S1–S11 complete. All three `/api/spatial/*`
  endpoints verified against live Railway data; DBSCAN detect+store round-trip
  verified against real PostGIS; WorldPop live-verified (808,874 people on the
  active flood alert).
- **Phase 2 — DONE** (2026-07-28). C1–C16 complete. USSD rewritten with live
  PostGIS queries, report writes and SMS opt-in; WhatsApp `subscribe`/`stop` +
  conversational state machine + report persistence + `hali_alert_v1` template;
  Africa's Talking SMS transport; `broadcast_alert()` with spatial targeting;
  PWA subscription endpoint; `subscriber-stats`. Verified end to end against
  Railway: USSD returns real Swahili action cards in ~800ms, and broadcast
  targeting matched one subscriber by country and one by GPS polygon
  intersection while excluding an opted-out subscriber.
- **Phase 3 — DONE** (2026-07-28). F1–F11 complete, verified in a real browser
  against Railway data: ICPAC WMS switcher, emerging-hotspot layer, compound-risk
  choropleth + "Most at risk now" panel, click-to-analyse side panel, 30-day
  temporal playback, `population_exposed` surfaced, PWA subscribe page, offline
  queue mounted, PWA icons generated, Workbox rule ordering fixed.
- **Phase 4 — DONE** (2026-07-28). A1–A10 and S11 complete (F9/F10/F11 landed
  with Phase 3, C15/C16 with Phase 2). 132 backend + 11 frontend tests pass.
- **Real country boundaries — DONE** (2026-07-28, migrations 006/007). Natural
  Earth 1:10m replaces the bounding boxes; alert country attribution recomputed,
  which corrected the active alert from {ET,ER,SD,SS} to {ET,SD}.

The spec's four ICPAC layer names (`geonode:rainfall_anomaly`, `flood_risk`,
`spi_3month`, `ea_hazard_zones`) do not exist on geoportal.icpac.net — all four
404 against its GetCapabilities. Phase 3 substitutes five real layers from
ICPAC's own catalogue, each confirmed to return a live tile; see
`apps/frontend/src/lib/icpacLayers.ts`.

Phase 2 added migration **005** (`alerts.broadcast_at`) which was not in the
original plan: without it, any re-run of the AI backlog would re-send SMS that
subscribers had already received.

Two schema decisions deviate from the spec and are recorded at their line items:
`alerts.population_exposed` is nullable (§Phase 0), and `compound-risk` aggregates
per country rather than per alert-country pair (§Phase 1).

---

## 0. Executive summary

The spec's "What remains to build" table (§13.3) is **directionally right but optimistic**. Several
rows marked `✅ Built` or `✅ Designed` in §13.1 have **no code at all**.

| Layer | Reality |
|---|---|
| Ingestion ETL (5 adapters, dedup, dead-letter, scheduler) | **Genuinely built.** No work needed. |
| AI ensemble (Claude + Gemini + Groq, scorer, translations, action cards, NLP labels) | **Genuinely built**, with 5 real correctness bugs. |
| Severity escalation from ground truth | **Half-built** — threshold + Claude assessment exist, the `confidence > 0.6` gate and AI-requeue do not. |
| Spatial analysis (§4.3–4.6) | **Does not exist.** No `routers/spatial.py`, no `ai/spatial_clustering.py`, no sklearn dep. |
| Subscriber layer (§7) | **Does not exist end-to-end.** No table, no opt-in, no SMS transport, no broadcast. |
| USSD (§5.1) | **22-line static string dict.** Zero DB access. |
| WhatsApp (§5.2) | Real webhook + real HMAC + real live alert lookup. Missing `subscribe`/`stop`, report persistence, template messages. |
| Frontend map (§8.3) | 2 of 7 layers built (alert zones, heatmap). 5 missing. |
| PWA offline | Workbox configured correctly; **offline queue never drains** (hook is dead code). |

**The three highest-leverage gaps, in order:** (1) the spatial layer — it is the entire GIS story and
four demo features hang off it; (2) the subscriber + broadcast layer — without it HALI receives but
never *reaches* anyone, which is the core claim; (3) USSD, which is the "any phone, no registration"
differentiator and is currently a hardcoded string.

---

## 1. Verified gap register

Status key: **MISSING** = no code · **PARTIAL** = exists, incomplete · **BUG** = built but wrong.

### 1.1 Database

| # | Item | Status | Evidence |
|---|---|---|---|
| D1 | `user_subscriptions` table + GIST index | MISSING | `sql/migrations/002_create_tables.sql` defines 6 tables; no 004 migration exists |
| D2 | `emerging_hotspots` table + GIST index | MISSING | no file |
| D3 | `alerts.population_exposed INTEGER DEFAULT 0` | MISSING | not in `002_create_tables.sql:12-26` |
| D4 | `community_reports.channel` | MISSING | not in `002_create_tables.sql:49-57` |
| D5 | `community_reports.phone_ref` | PARTIAL | column is named `phone_number` (`002_create_tables.sql:55`) — name drift from spec |
| D6 | `alerts.is_new` column | PARTIAL by design | derived at read time: `repositories/alerts.py:15` (`processed_at > NOW() - 24h`). Acceptable — but §3.6 severity upgrade relies on setting it explicitly |
| D7 | Migrations run in the Docker image | **BUG — deploy blocker** | `alembic/versions/002_create_tables.py:18` reads `parents[4]/sql/migrations/...`, but `apps/backend/Dockerfile:50-52` copies only `src`, `alembic`, `alembic.ini`. **`sql/` is not in the image** → `alembic upgrade head` fails with `FileNotFoundError` in the container |
| D8 | `countries.geom` real boundaries | PARTIAL | `003_seed_igad_countries.sql:4-13` seeds 8 IGAD states as **axis-aligned `ST_MakeEnvelope` bounding boxes**, not real polygons. Compound-risk `ST_Area(ST_Intersection(...))` will be visibly wrong on a map |
| D9 | `alert_translations.audio_url`, `community_reports.labels[]` | IMPLEMENTED | `002_create_tables.sql:34`, `:54` |

### 1.2 Backend — spatial (§4)

| # | Item | Status | Evidence |
|---|---|---|---|
| S1 | `ai/spatial_clustering.py` DBSCAN | MISSING | no file; no sklearn import anywhere |
| S2 | `GET /api/spatial/compound-risk` | MISSING | no `routers/spatial.py`; `main.py:48-53` registers 6 routers, none spatial |
| S3 | `GET /api/spatial/analyse?lat=&lng=` | MISSING | no file |
| S4 | `GET /api/spatial/emerging-hotspots` | MISSING | no file |
| S5 | WorldPop population exposure | MISSING | zero references to `api.worldpop.org` |
| S6 | `/api/alerts/geojson` `from_date`/`to_date` params | MISSING | `routers/alerts.py:20-24` supports `bbox`, `lang`, `severity`, `hazard` only |
| S7 | `population_exposed` in geojson properties | MISSING | `repositories/alerts.py:29-58` |
| S8 | `*/30min` hotspot scheduler job | MISSING | `scheduler.py:56-73` has 5 daily cron ingestion jobs + `ai-backlog-daily` 08:00. No interval trigger of any kind |
| S9 | `scikit-learn`, `numpy` deps | MISSING | not in `apps/backend/pyproject.toml` (numpy only transitively via rasterio) |
| S10 | `/api/alerts/geojson` returns expired alerts | BUG | no `valid_to > NOW()` filter, unlike `list_alerts` |
| S11 | `/api/reports/heatmap` intensity | PARTIAL | `repositories/reports.py:40` hardcodes `intensity = 1` instead of computed density |

### 1.3 Backend — delivery & subscribers (§5, §7)

| # | Item | Status | Evidence |
|---|---|---|---|
| C1 | USSD live PostGIS nearest-alert query | MISSING | `routers/ussd.py:11` returns a hardcoded string; the file has no DB import at all |
| C2 | USSD option 2 → `community_reports` INSERT | MISSING | `ussd.py:15-18` static ack only. Note `community_reports.location` is `NOT NULL` — needs a location source |
| C3 | USSD option 3 (SMS opt-in) | MISSING | main menu `ussd.py:10` has 3 options; "About" occupies `"3"`, no opt-in node |
| C4 | USSD livelihood submenu `1*3` fisherfolk, `1*4` urban | MISSING | `ussd.py:11` has farmer + pastoralist only |
| C5 | USSD 182-char / <3s guards | MISSING | no truncation helper, no timeout wrapper |
| C6 | WhatsApp `subscribe` + `stop` intents | MISSING | `whatsapp.py:109-130` routes `alerts`, `report `, `help` only |
| C7 | WhatsApp conversational opt-in state machine | MISSING | no state store exists (no Redis in `pyproject.toml`); Postgres is the only viable option |
| C8 | WhatsApp `report <text>` persistence | MISSING | `whatsapp.py:117-118` logs `"acknowledged (not persisted)"` |
| C9 | WhatsApp outbound **template** messages | PARTIAL | `_send_whatsapp_message` (`whatsapp.py:159-187`) sends `"type": "text"` only. No `hali_alert_v1`, no components/params |
| C10 | Africa's Talking SMS send | MISSING | `africastalking ^2.0.2` declared at `pyproject.toml:21` but **never imported in any source file** |
| C11 | `broadcast_alert()` | MISSING | no definition, no call site, no scheduler job, no hook in `ai/processor.py` |
| C12 | Any code touching `user_subscriptions` | MISSING | zero grep hits repo-wide |
| C13 | `GET /api/admin/subscriber-stats` | MISSING | `routers/admin.py` has 5 endpoints, not this one |
| C14 | `POST /api/admin/run-hotspot-detection` | MISSING | same |
| C15 | WhatsApp HMAC fails open | BUG | `whatsapp.py:196-197` returns `True` when `whatsapp_app_secret` is empty — and `config.py:26` defaults it to `""` |
| C16 | `GET /whatsapp` returns `int(hub_challenge)` | BUG | `whatsapp.py:52` → `ValueError` → HTTP 500 on a non-numeric challenge |

### 1.4 Backend — AI correctness bugs in shipped code

| # | Item | Status | Evidence |
|---|---|---|---|
| A1 | `AI_MIN_CLARITY_SCORE` is dead config | BUG | declared `config.py:34`, **never referenced**. Winner picked by bare `max()` at `router.py:252` with no floor |
| A2 | Severity upgrade ignores `confidence` | BUG | `processor.py:311` checks `should_upgrade` boolean + rank increase only. Spec §3.6 requires `confidence > 0.6`. Confidence is parsed and discarded |
| A3 | Severity upgrade does not requeue AI | BUG | translations + action cards are **not regenerated** after an upgrade, so stored text keeps the old severity |
| A4 | `_fallback_translate` never-awaited coroutines | BUG | `router.py:264-268` builds all 3 coroutines eagerly then awaits sequentially → `RuntimeWarning: coroutine was never awaited` when Claude succeeds |
| A5 | No on-demand translation generation | MISSING | `repositories/alerts.py:12-27` only `COALESCE`s to `en` then `initcap(hazard_type)`. Spec §3.3 requires generate-if-absent (the action-card path does this correctly) |
| A6 | 24 action cards generated **serially** | PARTIAL | `processor.py:128-144` nested for-loops, no `gather` → 24 sequential LLM calls per alert |
| A7 | Scorer is English/Swahili-biased | BUG | keyword sets at `scorer.py:25-42` mean `so`/`am`/`om`/`ar` outputs score ~0 on actionability + specificity → ensemble systematically prefers the wrong provider for 4 of 6 languages |
| A8 | Report classification task can be GC'd | BUG | `services/reports.py:22-24` uses bare `asyncio.create_task` with no reference held; no validation that returned labels are in the 17-label allow-list (`processor.py:392`) |
| A9 | On-demand action card gated `lang != "en"` | BUG | `services/alerts.py:33` — a missing English card 404s instead of generating |
| A10 | `ActionCard.generated_by` hardcoded | BUG | `processor.py:236` always writes `ModelProvider.CLAUDE` regardless of the actual provider → `/api/admin/ai-stats` under-reports |

### 1.5 Frontend (§8)

| # | Item | Status | Evidence |
|---|---|---|---|
| F1 | ICPAC WMS layer switcher | MISSING | zero hits for `icpac`/`geoserver`/`wms` in `apps/frontend/src`. No `L.control.layers` at all |
| F2 | Emerging hotspot layer (pulsing amber dots) | MISSING | no code |
| F3 | Compound-risk choropleth | MISSING | no code |
| F4 | Click-to-analyse side panel | MISSING | only `bindPopup` at `HaliMap.tsx:84`; no map `click` handler |
| F5 | Temporal 30-day slider | MISSING | heatmap window hardcoded to 7 days (`HaliMap.tsx:107`) |
| F6 | `population_exposed` shown anywhere | MISSING | absent from `packages/types/src/index.ts` (`Alert:15-27`, `AlertFeatureProperties:57-66`) |
| F7 | PWA subscription/opt-in form | MISSING | `ReportForm.tsx` collects no phone number |
| F8 | Push notifications | MISSING | zero hits for `pushManager` / `VAPID` |
| F9 | Offline queue never drains | **BUG** | `useReportQueue` (`hooks/useReportQueue.ts:7`) is **never imported by any component**. Reports queue to `localStorage` and sit there forever |
| F10 | PWA manifest icons | BUG | `vite.config.mts:19,29-30` reference `apple-touch-icon.png`, `pwa-192x192.png`, `pwa-512x512.png`; `apps/frontend/public/` contains only `favicon.ico` |
| F11 | Workbox cache rule ordering | BUG | `/api/alerts(\?.*)?$/` (`vite.config.mts:38`) is registered before the geojson rule and can swallow `/api/alerts/geojson?...` into the wrong cache |
| F12 | Alert zones + heatmap layers | IMPLEMENTED | `HaliMap.tsx:67-99`, `:105-123` |
| F13 | 5 routes, Workbox strategies, offline queue lib | IMPLEMENTED | `App.tsx:34-38`, `vite.config.mts:36-70`, `lib/offlineQueue.ts` |

---

## 2. Plan of attack

Sequenced so nothing is blocked and each phase is independently demoable. **Phase 0 must land first** —
every later phase writes to new tables, and migrations currently cannot run in the deployed container.

### Phase 0 — Unblock the schema (≈45 min, blocking everything)

**0.1 Fix the migration path bug (D7).** Add `COPY sql/ ./sql/` to `apps/backend/Dockerfile` (or inline
the DDL into the Alembic revision bodies — inlining is more robust and removes the `parents[4]` fragility
entirely). Then add `alembic upgrade head &&` to the container `CMD`, or a small `entrypoint.sh`, so
schema changes actually reach Railway. Verify with a local `docker build` + `docker run`.

**0.2 Write `sql/migrations/004_spatial_and_subscribers.sql` + Alembic revision 004** covering D1–D4:

```sql
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS population_exposed INTEGER DEFAULT 0;
ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS channel TEXT DEFAULT 'pwa'
  CHECK (channel IN ('pwa','ussd','whatsapp'));

CREATE TABLE emerging_hotspots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    location        geometry(Point,4326) NOT NULL,
    report_count    INTEGER NOT NULL,
    dominant_hazard TEXT NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL,
    first_reported  TIMESTAMPTZ NOT NULL,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_subscriptions (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number   TEXT NOT NULL UNIQUE,
    channel        TEXT NOT NULL CHECK (channel IN ('sms','whatsapp','both')),
    language       TEXT NOT NULL DEFAULT 'sw',
    livelihood     TEXT NOT NULL DEFAULT 'farmer',
    location       geometry(Point,4326),
    preferred_iso2 CHAR(2),
    opted_in       BOOLEAN NOT NULL DEFAULT TRUE,
    opted_in_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    opted_in_via   TEXT CHECK (opted_in_via IN ('ussd','whatsapp','pwa')),
    min_severity   TEXT NOT NULL DEFAULT 'orange',
    last_active    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- for the WhatsApp opt-in state machine (C7) — avoids adding Redis
    convo_state    TEXT,
    convo_data     JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX emerging_hotspots_geom_idx ON emerging_hotspots USING GIST(location);
CREATE INDEX user_subscriptions_loc_idx ON user_subscriptions USING GIST(location);
CREATE INDEX user_subscriptions_optin_idx ON user_subscriptions (opted_in) WHERE opted_in;
```

`convo_state`/`convo_data` on `user_subscriptions` is the cheapest correct answer to C7 — no new
infrastructure, and the row you need to write at the end of the flow already exists.

**0.3 Add deps (S9):** `scikit-learn ^1.5`, `numpy ^2.0` to `apps/backend/pyproject.toml`. While there,
drop the unused `nltk` and `asyncio-throttle`. Run `poetry lock`.

**0.4 (optional, 20 min, high visual payoff) Replace the bounding-box countries (D8)** with real Natural
Earth `ne_110m_admin_0_countries` geometry for the 8 IGAD states as migration 005. Bounding boxes make
the compound-risk choropleth look obviously wrong on a map — rectangles over Africa.

---

### Phase 1 — Spatial layer (the biggest single gap; ≈4–5 h)

Creates one new module and one new router. Nothing here depends on Phase 2.

**1.1 `apps/backend/src/hali/ai/spatial_clustering.py` (S1).** Implement `detect_emerging_hotspots(pool)`
per spec §4.5: DBSCAN, `eps = 50/6371`, `min_samples=3`, `metric='haversine'`, `algorithm='ball_tree'`,
on `community_reports` from the last 7 days. For each cluster, `ST_DWithin(geom::geography, ST_Point(...)::geography, 100000)`
against active alerts; keep only uncovered clusters. Two deviations from the spec pseudo-code worth making:
run the coverage check as **one batched query** rather than per-cluster `pool.acquire()` in a loop, and
write results in a **transaction** so `DELETE` + re-`INSERT` is never observed empty by a concurrent
map request.

**1.2 `apps/backend/src/hali/repositories/spatial.py`** — the three PostGIS queries. Take the compound-risk
CTE from spec §4.3 and the analyse query from §4.6 as-is; both are sound. Bind `lat`/`lng` as parameters,
never interpolate.

**1.3 `apps/backend/src/hali/routers/spatial.py` (S2–S4)** — `GET /api/spatial/compound-risk`,
`GET /api/spatial/analyse?lat=&lng=`, `GET /api/spatial/emerging-hotspots`. Register in `main.py:48-53`.
Validate `lat ∈ [-90,90]`, `lng ∈ [-180,180]` with FastAPI `Query(ge=, le=)`.

**1.4 WorldPop population exposure (S5).** New `apps/backend/src/hali/services/population.py`:
`compute_population_exposure(geojson) -> int` against `api.worldpop.org/v1/services/stats`. Wrap in
`tenacity` retry (already a dep) and **default to 0 on any failure** — this must never block alert
creation. Call it once from `ingestion/loader.py` after insert, or from `ai/processor.py` before
translation; cache into `alerts.population_exposed`.

**1.5 Alerts geojson upgrades (S6, S7, S10).** In `repositories/alerts.py:29-58`: add `from_date`/`to_date`
params (`valid_from <= $to AND valid_to >= $from`), add `population_exposed` to the properties, and add
the `valid_to > NOW()` filter — but **only when no date range is supplied**, otherwise temporal playback
of past alerts breaks. Thread the params through `routers/alerts.py:19-24`.

**1.6 Scheduler + admin (S8, C14).** Add an `IntervalTrigger(minutes=30)` job `hotspot-detection` to
`scheduler.py:56-73`, in its own `try/except` like the existing jobs. Add
`POST /api/admin/run-hotspot-detection` to `routers/admin.py` for manual/demo triggering.

**Demo checkpoint:** `curl /api/spatial/compound-risk`, `/api/spatial/analyse?lat=-1.29&lng=36.82`,
`/api/spatial/emerging-hotspots` all return valid FeatureCollections.

---

### Phase 2 — Subscribers, delivery, broadcast (≈5–6 h)

The "last-mile" claim lives or dies here. Depends only on Phase 0.

**2.1 `apps/backend/src/hali/repositories/subscriptions.py` (C12).** `upsert_subscriber`, `opt_out`,
`get_matching_subscribers(alert_id)`, `subscriber_stats`, plus `get_convo_state`/`set_convo_state`.
The matching query is spec §7.3 verbatim — `ST_Intersects(location, alert.geom) OR preferred_iso2 = ANY(affected_countries)`,
gated on `min_severity`. This spatial targeting is a headline differentiator; make sure it's the real
query and not a list scan.

**2.2 `apps/backend/src/hali/services/sms.py` (C10).** Wrap `africastalking` (already a declared dep).
Guard on `settings.africastalking_api_key` being present; log-and-skip in dev rather than raising. Add
an `sms_enabled` property to `config.py` mirroring the existing `whatsapp_enabled` at `config.py:77-79`.

**2.3 Rewrite `routers/ussd.py` (C1–C5).** This is the largest single-file change. It becomes a real
router with `db` injected:
- Parse `text` into `parts = text.split("*")`; dispatch on depth.
- `"1"` → live query: nearest active alert to the subscriber's `preferred_iso2` (or the country resolved
  from their stored location), returning the translated headline. Then the 4-livelihood submenu
  `1*1..1*4` → real `action_cards` rows.
- `"2*N"` → INSERT into `community_reports` with `channel='ussd'`. **`location` is `NOT NULL`** — resolve
  it from the subscriber's stored point, else the centroid of their `preferred_iso2` country, else
  reject with a friendly END. Do not make the column nullable.
- `"3"` → opt-in: capture `phoneNumber` from the AT POST body, walk language → livelihood → country,
  UPSERT `user_subscriptions` with `opted_in_via='ussd'`.
- `"4"` → About.
- Add a `_page(text: str) -> str` helper enforcing the 182-char limit, and wrap every DB call in
  `asyncio.wait_for(..., timeout=2.0)` with a static fallback string — **AT kills the session at 3 s**,
  so a slow query must degrade, not hang.

**2.4 WhatsApp completion (C6–C9, C15, C16).** In `routers/whatsapp.py`:
- Add `subscribe` and `stop` to the intent router at `:109-130`.
- Implement the region → livelihood → confirm flow using `convo_state`/`convo_data` from 0.2.
- Persist `report <text>` to `community_reports` with `channel='whatsapp'` (replacing the
  `"not persisted"` log at `:117-118`), reusing the same location-resolution fallback as USSD.
- Add `_send_whatsapp_template(...)` emitting `"type": "template"` with `hali_alert_v1` and the 4
  body params from spec §5.2.
- **Fix C15:** make the empty-app-secret case fail *closed* in production — return `True` only when
  `settings.environment == "development"`.
- **Fix C16:** `return PlainTextResponse(hub_challenge)` instead of `int(...)`.

**2.5 `apps/backend/src/hali/services/broadcast.py` (C11).** `broadcast_alert(alert_id, pool)` per spec
§5.3: fetch matching subscribers, resolve translation + action card per subscriber's language/livelihood,
fan out to SMS and/or WhatsApp. Guard rails that matter for a live demo:
- Fire **only** for `orange`/`red`.
- Bound concurrency with a semaphore and use `asyncio.gather(..., return_exceptions=True)` — one bad
  number must not abort the batch.
- Record what was sent (at minimum a structured log line per delivery) so failures are diagnosable.
Trigger it from the end of `ai/processor.py`'s per-alert processing, once translations exist.

**2.6 `GET /api/admin/subscriber-stats` (C13)** — counts by channel / language / country.

**Demo checkpoint:** opt in via the AT sandbox simulator → trigger an orange alert →
receive an SMS in Swahili with livelihood-specific first action step.

---

### Phase 3 — Frontend GIS (≈4–5 h, parallelisable with Phase 2)

Depends on Phase 1's endpoints. F1 depends on nothing and can be done immediately.

**3.1 Extend `lib/api.ts` + `packages/types/src/index.ts`.** Add `fetchCompoundRisk()`,
`fetchEmergingHotspots()`, `analyseLocation(lat,lng)`, and `from_date`/`to_date` params on
`fetchAlertsGeoJSON`. Add `population_exposed` to `Alert` and `AlertFeatureProperties` (F6).

**3.2 ICPAC WMS layer switcher (F1) — do this first.** Zero backend dependency, and it is the single
most judge-legible feature in the spec: ICPAC's own GeoServer data rendered inside HALI. Add the four
`L.tileLayer.wms` layers from spec §4.2 and an `L.control.layers` overlay control to `HaliMap.tsx`.
**Verify the four `geonode:*` layer names against the live GetCapabilities before demo day** — layer
names on public GeoServers drift, and a 404 tile grid is worse than no layer. Fall back to whichever
layers actually resolve.

**3.3 Emerging hotspot layer (F2).** `L.circleMarker` amber dots sized by `report_count`, with a CSS
`@keyframes` pulse. Popup per spec §4.5: report count, dominant hazard, `"UNCONFIRMED — no official alert"`,
first-reported relative time.

**3.4 Compound-risk choropleth (F3).** GeoJSON layer over IGAD countries, light-blue → deep-red scale on
`compound_risk_score`. Add the "Top 5 at-risk right now" ranked panel — it reads far better than the
choropleth alone.

**3.5 Click-to-analyse panel (F4).** Map `click` handler → `analyseLocation(lat,lng)` → render into the
existing shadcn `Sheet` component (already in `components/ui/sheet.tsx`, so no new dependency). Layout
per spec §4.6.

**3.6 Temporal slider (F5).** 30-day range slider driving `from_date`/`to_date` on the geojson fetch and
the heatmap window (currently hardcoded to 7 days at `HaliMap.tsx:107`). Debounce ~250 ms. Lowest priority
in this phase — cut it first if time runs short.

**3.7 PWA opt-in form (F7).** Phone + language + livelihood + optional GPS → the Phase 2 subscription
endpoint, with `opted_in_via='pwa'`.

---

### Phase 4 — Correctness fixes in shipped code (≈2–3 h)

These are small, isolated, and each one closes a gap between what §13.1 claims and what runs.

**Ship-blocking-ish (do these):**
- **F9 — mount `useReportQueue`.** One import in `App.tsx`. Right now every offline report is written to
  `localStorage` and never sent. The offline story is claimed as `✅ Built` and is currently non-functional.
- **A2 + A3 — severity escalation.** Add the `confidence > 0.6` gate at `processor.py:311`, and requeue
  translations + action cards after an upgrade (set `processed_at = NULL` so the existing backlog job
  picks it up). Without A3 the alert text still says "orange" after upgrading to red.
- **A4 — `_fallback_translate` coroutine leak** (`router.py:264-268`): build coroutines lazily inside the
  loop.
- **A1 — enforce `AI_MIN_CLARITY_SCORE`** at `router.py:252`: if the best score is below the floor, fall
  through to the next provider rather than shipping it.
- **C15/C16** — covered in 2.4.
- **F10 — generate the three missing PWA icons** into `apps/frontend/public/`. The manifest currently
  ships broken icon URLs, which fails PWA installability checks.

**Worth doing if time allows:**
- **A5** — on-demand translation generation, mirroring the action-card path.
- **A6** — `asyncio.gather` the 24 action cards (respecting `AI_MAX_CONCURRENT_ALERTS`); cuts per-alert
  processing time roughly an order of magnitude.
- **A7** — extend `scorer.py:25-42` keyword sets to `so`/`am`/`om`/`ar`, or normalise per-language so the
  ensemble isn't biased for 4 of 6 languages.
- **A8** — hold a reference to the classification task; validate labels against the 17-label allow-list.
- **A9** — drop the `lang != "en"` gate at `services/alerts.py:33`.
- **A10** — pass the actual provider through to `ActionCard.generated_by` so `/ai-stats` is truthful.
- **F11** — reorder the Workbox `runtimeCaching` rules so geojson matches its own cache.
- **S11** — compute real heatmap intensity instead of the hardcoded `1`.

---

## 3. Suggested sequencing against the deadline

~3.5 days remain. Phases 2 and 3 are independent and should run in parallel if there are two of you
(spec §13.3 already splits ownership: Martin on backend, GIS dev on frontend).

| When | Backend track | Frontend track |
|---|---|---|
| **Tue 29 AM** | Phase 0 (schema + Docker migration fix + deps) | 3.2 ICPAC WMS switcher (no backend dep) |
| **Tue 29 PM** | Phase 1.1–1.3 (DBSCAN + spatial router) | 3.1 api.ts + types scaffolding |
| **Wed 30 AM** | Phase 1.4–1.6 (WorldPop, geojson params, scheduler) | 3.3 + 3.4 hotspots + choropleth |
| **Wed 30 PM** | Phase 2.1–2.3 (subscriptions repo, SMS, USSD rewrite) | 3.5 click-to-analyse panel |
| **Thu 31 AM** | Phase 2.4–2.6 (WhatsApp, broadcast, admin stats) | 3.6 temporal slider · 3.7 PWA opt-in |
| **Thu 31 midday** | Phase 4 fixes · end-to-end rehearsal · deploy | F9/F10 fixes · deploy |

**External dependencies to start *today*, because they have approval latency and will otherwise block
the Thursday demo regardless of code readiness:**
- Africa's Talking USSD service code (§13.3 marks this Critical) — sandbox works for the demo, but request
  the real code now.
- Meta `hali_alert_v1` template submission — **template approval can take 24 h+**. Submit before writing
  the code that uses it.
- `GEMINI_API_KEY` / `GROQ_API_KEY` / `GLOFAS_CDS_API_KEY` present in the Railway environment.

**If time runs out, cut in this order:** 3.6 temporal slider → 3.7 PWA opt-in → 0.4 real country
geometry → the "worth doing" half of Phase 4. Do **not** cut Phase 0, Phase 1, or 2.5 — the schema fix,
the spatial layer, and the broadcast are what the differentiation matrix in §13 is actually claiming.

---

## 4. Spec corrections to make alongside the code

`HALI_FEATURES_TECHNICAL_SPECS.md` §13.1 currently overstates status. Once the above lands, the honest
version is: **DBSCAN hotspots, population exposure, compound risk, click-to-analyse, temporal animation,
spatial subscriber targeting, and ICPAC WMS were all marked `✅ Built` or `✅ Designed` while having zero
implementing code.** Update §13.1 to reflect reality as each phase merges — a judge who greps the repo
against that table will find the discrepancy faster than they'll find the features.

Two smaller drift items to reconcile in the doc: the spec's `community_reports.phone_ref` is
`phone_number` in the schema (D5), and `alerts.is_new` is a derived read-time expression, not a column (D6).
