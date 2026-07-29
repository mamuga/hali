# HALI — Final Sprint: Corrected Execution Plan

Derived from `hali_final_sprint_prompt.md`, reconciled against the actual repo
state on 2026-07-28. **Deadline: 2026-07-31 @ 17:00 EAT.**

This file supersedes the prompt where they disagree. The prompt was written
against an older snapshot of the codebase; roughly 40% of its work is already
merged (commits `b6647b2`, `b361129`, `0b0f45b`).

---

## Reconciliation: what the prompt asks for vs. what exists

### Already done — DO NOT redo

| Prompt § | Instruction | Actual state |
|---|---|---|
| 1.4 | Implement `/api/admin/run-hotspot-detection` | Exists — `routers/admin.py:68` |
| 1.4 | Implement `/api/spatial/emerging-hotspots` | Exists — `routers/spatial.py:21` |
| 1.4 | USSD stores `POINT(0 0)`; add centroid lookup | Fixed — `routers/ussd.py:209` `_resolve_country_point()` |
| 1.4 | Add `channel` column | Migration `004_spatial_and_subscribers.sql:14` |
| 3.1 | Replace bbox countries w/ Natural Earth **1:50m**, as migration 004 | **Already real, at 1:10m** — `006_real_country_boundaries.sql` (132 KB). Following the prompt would *downgrade* resolution and collide with an existing migration number. **SKIP ENTIRELY.** |
| 3.3 | "choropleth gets better automatically after 3.1" | Already true |
| 5.2 | Add `/api/admin/recompute-population` | `/api/admin/backfill-population` exists — `routers/admin.py:99` |

### Corrections to the prompt

1. **§2.3 "No DB migration needed (hazard_type is TEXT)" — FALSE and dangerous.**
   Five CHECK constraints in `sql/migrations/002_create_tables.sql` pin the
   exact vocabularies:
   - `:15` `alerts.hazard_type IN (flood, drought, locust, cyclone, health, other)`
   - `:31` `alert_translations.language IN (sw, so, am, om, ar, en)`
   - `:42` `action_cards.livelihood IN (farmer, pastoralist, fisherfolk, urban)`
   - `:43` `action_cards.language IN (sw, so, am, om, ar, en)`
   - `:51` `community_reports.hazard_type IN (...)`

   Without a migration, **every** new language / livelihood / hazard raises
   `CheckViolationError` at insert time. This must land before any Phase 2 code.

2. **Migration numbering:** 001–007 are taken. New ones are **008** (vocabulary
   + `location_precision`) and **009** (`pop_grid`), not 004/005.

3. **§2.1 low-resource fallback is self-contradictory** ("`aa`/`ti` → `am`
   script-adjacent? No — fall back to `en`"). Resolution: fall back to **`en`**,
   recorded via a `fallback_language` column. Never serve empty.

4. **§1.3's verification script targets a local backend** (`nx run backend:serve`,
   `psql $DATABASE_URL_RAW`). Per standing instruction, run against **Railway**.

5. **New data-quality bug the prompt correctly flags (§1.4):** USSD/WhatsApp
   reports now carry *real* country centroids, so N reports from one country
   form a spurious DBSCAN cluster at that centroid. `location_precision` +
   a DBSCAN filter is a genuine fix, not gold-plating.

---

## PHASE 1 — Reporting E2E verification ✅ DONE (2026-07-28)

Verified against the live Railway DB with a locally-served backend
(`ENABLE_SCHEDULER=false ENABLE_BROADCAST=false` — there is one real opted-in
subscriber and a live Africa's Talking key, so an escalation could otherwise
have sent a real SMS).

| # | Check | Result |
|---|---|---|
| 1 | PWA report stored (Lodwar GPS) | ✅ |
| 2 | AI classification fires | ✅ `{flood, road_blocked}` |
| 3 | USSD report, `channel='ussd'` | ✅ (prompt's `text=2*1` was wrong; the save step is `2*1*1`) |
| 4 | WhatsApp report, `channel='whatsapp'` | ❌ → fixed |
| 5 | Heatmap aggregation | ✅ after fix |
| 6 | DBSCAN pickup | ✅ 1 hotspot, 4 reports, correctly UNCONFIRMED |
| 7 | Severity escalation | ✅ orange→red, confidence 0.8, reasoning cites the reports |
| 8 | Offline queue | ✅ covered by 6 new unit tests |

### Defects found and fixed

1. **WhatsApp reports from non-subscribers were silently dropped.** `_save_report`
   required a subscription to resolve a location and otherwise returned a
   "please subscribe" message without storing anything — discarding reports from
   exactly the people most likely to message during a disaster. Now falls back
   subscriber point → chosen country → **dialling-code country**
   (`_iso2_from_phone`, longest-prefix match so `211`/SS is not shadowed).

2. **USSD and WhatsApp reports were never classified.** Both routers wrote
   straight to `ReportRepository`, bypassing `ReportService.schedule_classification`.
   The channels most of our users actually have were the only ones producing
   reports with no AI labels — invisible to every label-driven aggregate.
   Added `ReportService.create_from_channel`; both routers now use it.

3. **Country-precision reports poisoned the spatial layer.** Migration **008**
   adds `location_precision` (`gps` | `country`), backfilled by channel. DBSCAN
   and the heatmap now read GPS only; raw reports still count in aggregates,
   analysis, and severity escalation.

4. **`.env` pinned a dead Groq model.** `AI_GROQ_MODEL` was still
   `meta-llama/llama-4-scout-17b-16e-instruct` (404) in `.env` and `.env.example`,
   even though `config.py` and Railway were fixed earlier. With `ANTHROPIC_API_KEY`
   empty and Gemini's free tier capped at 20 req/day, Groq was the only working
   fallback and it was disabled — which is why the first escalation run produced
   **1 of 24** action cards and no upgrade signal. After the fix: 20/24 cards and
   a correct escalation.

### Still open (environment, not code)
- `ANTHROPIC_API_KEY` unset locally and on Railway — the ensemble runs on
  Gemini + Groq only, and Gemini's free tier caps at 20 requests/day. This is the
  binding constraint on any bulk regeneration in Phase 2.

### Notes
- Test artifacts were removed from production afterwards (1 synthetic alert,
  6 reports). One realistic Swahili Lodwar report was kept as demo data.
- Local `alembic` does **not** read `.env`; it silently falls back to
  `localhost:5433`. Always run it with `MIGRATION_DATABASE_URL` exported.

<details><summary>Original Phase 1 plan</summary>

1. Run the 7-step chain from prompt §1.3 **against Railway**, backend served
   locally with `DATABASE_URL` pointed at production.
2. Checks: PWA report stored → labels populate async → USSD row (`channel='ussd'`)
   → WhatsApp row (`channel='whatsapp'`) → heatmap points → DBSCAN pickup →
   severity escalation path.
3. Document any check that is "valid-but-zero" (e.g. 0 hotspots because an
   official alert already covers Lodwar) rather than reporting it as a failure.
4. **Fix expected to be needed:** add `location_precision TEXT DEFAULT 'gps'`
   (migration 008) and exclude non-`gps` rows from DBSCAN in
   `ai/spatial_clustering.py`.
5. Offline queue: build frontend, throttle to offline, submit, verify
   `hali:report_queue` in localStorage, restore, verify auto-retry + toast.

**Gate:** 7 checks pass or documented-valid; `pytest` green.
</details>

**Gate result:** backend `153 passed` (was 132), `ruff` clean,
frontend `17 passed` (was 11). Migration 008 applied to Railway;
`alembic current` → `008_report_location_precision (head)`.

---

## PHASE 2 — Domain expansion ✅ DONE (2026-07-28)

10 languages · 7 livelihoods · 10 hazards. Migration **009** applied to Railway
(`alembic current` → `009_expand_domain_vocabularies`).

### The blocker the prompt got wrong
`hali_final_sprint_prompt.md` §2.3 states "No DB migration needed (hazard_type is
TEXT)". It is TEXT **with a CHECK constraint**, and there were five of them.
Constraint names were read from `pg_constraint`, not guessed. Verified on Railway
by inserting a `heatwave` alert + `ti` translation + `displaced`/`fr` card inside
a transaction and rolling back — all accepted.

### Delivered
- **Languages** `+fr +ti +lg +aa` → `sw so am om ar en fr ti lg aa`.
  `LANGUAGE_NAMES`, `processor.LANGUAGES`, `schemas.Language`, `packages/types`,
  `LanguageSelector`, `Subscribe`, USSD menu. Selector labels are in each
  language's own script — someone who reads only Tigrinya cannot find "Tigrinya"
  in a list of English names.
- **Script enforcement** generalised into `prompts.script_requirement()`; `ti`
  now pinned to Ge'ez exactly as `am` is, `ar` to Arabic script.
- **Low-resource fallback**: `ti`/`lg`/`aa` below `AI_MIN_CLARITY_SCORE` are
  replaced with English and tagged `fallback_language` (new column). The row keeps
  the requested language code so lookups still resolve. Resolves the prompt's
  self-contradictory "script-adjacent? No — fall back to en".
- **Livelihoods** `+agropastoralist +trader +displaced` with real context strings.
- **Hazards** `+heatwave +landslide +wildfire +epidemic`; GDACS `WF` and `LS` no
  longer collapse to `other`.
- **Frontend**: hazard icon map and report-form chip list had already drifted
  apart, so both now read from one `lib/hazards.ts` (icon + label per hazard).
  Chips show icons — 10 text-only chips do not scan.

### Pre-generation budget
The full matrix is 7 × 10 = **70 model calls per alert**, which no free tier
survives. Pre-generate 4 core livelihoods × `sw, en, fr` = **12**; the other 58
are generated and cached on request. Translations stay pre-generated for all 10.

Deviation from the prompt: it said "LANGUAGES = all 10 minus `en`". English must
be generated — `alerts` stores no headline of its own, and `en` is the fallback
target for low-resource languages.

**No backlog regeneration was needed.** The prompt planned to re-run `fr` over the
5 most recent alerts; the on-demand endpoint already generates and caches a
missing translation on first request, which is how `fr`, `ti` and `lg` were
verified live.

### Live verification (Railway)
| Check | Result |
|---|---|
| `displaced` × `fr` action card | ✅ genuinely camp-specific French — shelter within the camp, camp officials, helping elderly/sick |
| `fr` translation | ✅ "Inondation en Éthiopie et Soudan…", `fallback_language=NULL` |
| `ti` translation | ✅ scored 0.55 < 0.6 floor → English served, `fallback_language='en'`, logged |
| `lg` translation | ✅ same fallback path |
| `heatwave` report POST | ✅ 200 (a CHECK violation before 009), classified `health_emergency` |

**Gate result:** backend `214 passed` (was 163), `ruff` clean,
frontend `24 passed` (was 17), `frontend:build` succeeds.

Test artifact (1 heatwave report) removed from production afterwards.

---

## PHASE 3 — Map overhaul ✅ DONE (2026-07-28)

§3.1 was skipped as planned — boundaries were already Natural Earth 1:10m from
migration 006. Everything else delivered and verified in a real browser.

### Delivered
- **`GET /api/spatial/countries/geojson`** — `ST_SimplifyPreserveTopology`
  (not `ST_Simplify`, which can self-intersect and drop rings, tearing holes in
  the mask). Tolerance is a clamped query param, default 0.02.
  Measured: raw 118 KB / 5,636 pts → **29.6 KB / 1,342 pts**. All 8 countries.
- **4 basemaps** (`lib/basemaps.ts`): OSM · Esri World Imagery · OpenTopoMap ·
  Esri Shaded Relief. Per-provider `maxZoom` — asking OpenTopoMap for z18
  returns 404s that Leaflet paints as grey squares.
- **Outside-IGAD mask + hollow outlines** (`lib/igad.ts`). Only exterior rings
  are punched out, so lakes are not re-dimmed. Both layers `interactive: false`.
- **One unified layer control**, expanded by default, with basemaps + 5 HALI
  overlays + 5 ICPAC WMS layers. Overlays self-register as their fetches land,
  keyed by name so a rebuilt layer replaces its row instead of duplicating it.
- **PWA caching** for the two new tile hosts, plus a dedicated 30-day
  `hali-boundaries` rule placed *before* the 5-minute `/api/spatial/` rule —
  otherwise the outlines and mask vanish the moment the device goes offline.

### Bugs found by looking at the actual rendered map
1. **Every overlay was missing.** `CORS_ORIGINS` allowed only `localhost:5173`,
   so every API call from the dev server was blocked. Local config, not code —
   but it would have looked like a total failure of the phase.
2. **`fitBounds` ran before layout.** The container was still 0x0, so it picked
   the lowest zoom and `setMinZoom` locked that in. Fixed with
   `invalidateSize()` + a `requestAnimationFrame` re-clamp + a `resize` handler.
3. **Whole-number zoom overshot the region badly.** IGAD is ~30 deg tall and
   ~32 deg wide, so latitude binds and the ideal fit is ~4.7 — which Leaflet
   floors to 4, more than doubling the visible longitude. The map opened showing
   Portugal and India either side. Fixed with `zoomSnap: 0.25`.
   The prompt's hardcoded `minZoom = 4` would have shipped exactly this.
4. **`registerOverlay` removed the wrong layer** on re-registration (the new one,
   not the previous), which would have duplicated the "Alert zones" row on every
   language or playback change. Caught before it shipped.

### Browser verification
Mask dims outside IGAD · hollow cyan outlines · all 5 overlays in the control ·
choropleth renders on Ethiopia and Sudan · Satellite basemap switches with
correct Esri attribution · **click-to-analyse still works** (resolved Kenya at
-0.486, 37.187) despite a world-covering mask and a country-covering choropleth.

**Gate result:** backend `222 passed` (was 214), `ruff` clean,
frontend `44 passed` (was 24), `frontend:build` succeeds.

---

## PHASE 4 — Draw-polygon AOI query ✅ DONE (2026-07-28)

Draw a shape, get every alert, report and hotspot inside it. Verified in a
browser against live Railway data.

### Backend — `POST /api/spatial/query-polygon`
- Geometry parsed **once** into a CTE. The prompt's draft re-parsed `$1` in five
  separate subqueries and PostgreSQL will not deduplicate that.
- `ST_MakeValid` — a hand-drawn bowtie makes `ST_Intersects` raise, not return false.
- Area measured by a **separate, cheap query first**, so an oversized shape is
  rejected before any spatial join runs.
- `pop_grid` guarded by `to_regclass`; returns `null`, never `0`, until Phase 5.

### The guard the obvious approach misses
An area cap alone is not enough. `ST_Area` on **geography** treats a ring
enclosing more than a hemisphere as its *complement*, so a polygon covering the
whole planet measures **2.8M km²** and sails under any sane cap — while
`ST_Intersects` runs on planar **geometry**, where that ring really does match
every row in every table. Found by probing the endpoint, not by reading it.

Fixed with a bounding-box span limit (`MAX_SPAN_DEGREES = 60`) evaluated in pure
Python during validation: no blind spot, and no database round trip at all.

| Probe | Result |
|---|---|
| whole planet | 422 "spans 358 deg by 178 deg" |
| hemisphere-wide | 422 |
| LineString / Point | 422 "must be a Polygon or MultiPolygon" |
| lat/lng out of range | 422 |
| degenerate 3-point ring | 422 |
| non-numeric coords | 422 |
| self-intersecting bowtie | 200 (repaired — a user slip, not an attack) |
| MultiPolygon | 200 |
| ocean | 200, clean empty state |

### Frontend
- `@geoman-io/leaflet-geoman-free` 2.20.0, polygon + rectangle only (offering a
  line tool would let users draw something the backend can only reject).
- **Lazy-loaded**: geoman lands in its own 274 KB / **72.7 KB gzip** chunk rather
  than the initial bundle.
- `AoiPanel` — area, alerts with severity badge + overlap km², report count with
  hazard tags, hotspot count, population (only when a grid exists), clear button.
- Re-queries on `pm:edit`, so the numbers always describe the outline on screen.

### Two bugs found by using it
1. **`map.pm` was undefined.** Geoman registers via `L.Map.addInitHook`, which
   only runs for maps built *after* it loads — and the lazy import means the map
   already exists. Fixed by attaching `new L.PM.Map(map)` the way the init hook
   would, keeping the lazy chunk.
2. **Every vertex click also fired click-to-analyse.** Drawing a five-sided
   polygon would have run five location analyses and slid the wrong panel over
   the shape being drawn. Fixed with an `isDrawing()` guard on the map click.

### Browser verification
Rectangle over Ethiopia/Sudan → **1,462,501 km²**, the live red flood alert with
**760.8 km² inside selection** (matching a direct curl probe exactly), 1
community report tagged Flood. Headline rendered in Swahili, confirming `lang`
flows through. A rectangle just north of the alert correctly returned the empty
state — the alert is four 0.25 deg squares, not a country-sized blob.

**Gate result:** backend `253 passed` (was 222), `ruff` clean,
frontend `50 passed` (was 44), `frontend:build` succeeds.

Note: `npm audit` reports pre-existing moderate/high advisories (react-router,
axios, nx). Geoman is not implicated. The react-router fix is a breaking major
bump — not a trade worth making three days from the deadline.

---

## PHASE 5 — WorldPop pop_grid ✅ DONE (2026-07-28)

Migration **010** applied to Railway. All eight countries ingested and loaded.

### Loaded (verified against UN 2020 figures)
| ISO2 | cells | population | UN 2020 |
|---|---|---|---|
| ET | 53,999 | 114,961,734 | ~115M ✓ |
| KE | 27,043 | 53,765,498 | ~53.8M ✓ |
| UG | 10,264 | 45,737,289 | ~45.7M ✓ |
| SD | 89,890 | 43,847,675 | ~43.8M ✓ |
| SO | 30,515 | 15,893,002 | ~15.9M ✓ |
| SS | 29,850 | 11,192,952 | ~11.2M ✓ |
| ER | 6,306 | 3,546,354 | ~3.5M ✓ |
| DJ | 1,130 | 986,807 | ~1.0M ✓ |
| **total** | **249,000** | **289,931,311** | |

Download URLs HEAD-checked before writing the adapter (27 MB total). The
prompt's URL pattern was correct; two plausible variants 404.

### Performance
Zonal-stats query is **0.17 ms server-side** (EXPLAIN ANALYZE) — the ~1s
wall-clock is round-trip latency to Railway from a dev machine. Replaces a
WorldPop REST call per alert that could take tens of seconds and often returned
nothing at all.

### Wiring
- `backfill_population_exposure` now prefers `pop_grid` when populated and only
  falls back to the REST path while the grid is empty. Existing callers
  (scheduler, admin endpoint) get the fast path with no change.
- `POST /api/admin/ingest-worldpop` (one-shot) and
  `POST /api/admin/recompute-population` added.
- The AOI endpoint's `population_estimate` now returns real numbers.
- `ENABLE_WORLDPOP=false` by default — static data, not for the scheduler.

### Design deviations
- 5x5 aggregation to ~5 km cells, as the prompt suggested. 249k rows total.
- `MIN_CELL_POPULATION = 1` drops smoothed near-zero floats that would
  otherwise add tens of thousands of empty desert rows.
- Nodata sentinel is removed before clamping negatives — clamping alone leaves
  WorldPop's -3.4e38 contributing to block sums.
- Per-country delete-then-insert inside one transaction, so a re-run cannot
  double the population and a mid-load failure cannot leave a country partially
  loaded (which would silently understate every exposure figure touching it).

---

## INTERLUDE — "few disasters, or wrong datasets?" (answered 2026-07-28)

**Wrong datasets, and a broken adapter.** Investigated on request.

### What our own database said
| source | raw ingested | alerts produced |
|---|---|---|
| gdacs | 230 (170 **failed**) | **0** |
| gfs | 22 | 22 (all flood) |
| chirps | 23 | 2 |
| glofas, icpac | 0 — never ran | 0 |

Zero drought alerts, ever, in a region whose defining hazard is drought.

### Three compounding GDACS bugs (all fixed)
1. **The 100-result cap.** GDACS `SEARCH` ignores `bbox` server-side (our own
   code comment said so) and caps at 100 events sorted globally by date. One
   combined query for six hazard types returned 100 events from China, Japan,
   Angola and Australia and **zero** from East Africa. Querying `DR` alone
   returned 14 events — including a live **Orange drought over Ethiopia, Kenya
   and Somalia**. Now one query per hazard type: 331 events instead of 100.
2. **`fromdate = todate = today`** only matched events *starting today*. The
   drought began 2026-04-21 and is still current. Now a 60-day lookback.
3. **`iscurrent` ignored.** GDACS gave the drought a `todate` already in the
   past (it is the last re-scoring date, not the end date), so an active
   emergency would have been filed as expired — invisible on the map and
   skipped by the broadcast. Now extended while `iscurrent` is true.

Also replaced `iso3[:2]` country matching, which happened to work for all eight
IGAD states by coincidence and mismaps anything else (TCD -> "TC"), with an
explicit table plus `affectedcountries` — the drought is filed under ETH alone,
so Kenyan and Somali subscribers would never have been matched.

**Result:** HALI's first drought alert, `['ET','KE','SO']`, 173,261 people
exposed, 9,591 km2.

### What the research found (verified endpoints, not documentation)
The deeper problem: **we ingest event feeds, but East Africa's hazards are
conditions.** GDACS asks "did something explode today?" The useful question is
"which admin2 units are anomalous this dekad?"

Actually happening in IGAD right now, per FEWS NET July 2026: North Rift Kenya
~50,000 acres of maize failing; Somalia Bay/Bakool near-total maize failure;
Karamoja severely below-average; region-wide Jun 1–Jul 10 rainfall below **45%
of average**; Bundibugyo Ebola active in Uganda; Kenya cholera and Somalia
dengue appeals live; a Somalia locust appeal opened **2026-07-27**.

The seasonal hypothesis is *partly* right — late July is between rainy seasons
for the equatorial belt, so sparse *flash flood* alerts are legitimate. It does
not explain missing drought, food-insecurity, epidemic or locust alerts.

**Top three additions (all free, all verified reachable):**
1. **HDX HAPI dekadal rainfall at admin2** — `rainfall_anomaly_pct` per admin2
   unit, instant self-service auth (base64 of `app:email`), one call per country
   per day. KEN 73 / SOM 74 / ETH 64 / UGA 71 admin2 units with live data.
   Threshold `<50%` -> drought, `>200%` -> flood watch. This is the direct answer
   to "drought in Turkana, floods in Tana River".
2. **FEWS NET IPC shapefiles** — `fdw.fews.net/api/ipcpackage/?country_code=KE`,
   no key, **640 real polygons for Kenya alone** (admin2 x livelihood zone) with
   IPC phase in the `CS` attribute. Replaces our 0.25 deg squares outright.
3. **IFRC GO + WHO DON + USGS** — keyless, populate the new `epidemic`,
   `wildfire` and `locust` types with real named events. 14 IGAD appeals in the
   last 10 months.

Plus **HDX COD-AB** GeoJSON for authoritative admin boundaries to join against.

**Traps to avoid:** ReliefWeb (v1 HTTP 410, v2 403 without pre-approved appname
requiring form review), IPC official API (401, key by request), ACLED (403,
approval — free via HAPI instead), Copernicus EMS (no working enumeration
endpoint found), EM-DAT (historical only), NASA FIRMS (key emailed, not
confirmed instant), FAO Locust Hub (no verifiable FeatureServer URL).

Correction to note: ICPAC's live system is **`eahazardswatch.icpac.net`**
(`/api/datasets/` -> 36 datasets); `geoportal.icpac.net` WFS exposes 365 feature
types but they are all static reference layers, no live alert features.

**Not implemented** — this is new scope beyond the sprint plan. Recommended as
the highest-value remaining work.

**Gate result:** backend `281 passed` (was 253), `ruff` clean,
frontend `50 passed`, `frontend:build` succeeds.

---

## PHASE 5b — New data sources integrated ✅ DONE (2026-07-28)

Requested after the research findings. Migration **011** (`admin_boundaries`)
applied to Railway.

### Active alerts: 1 -> 92

| source | active | granularity |
|---|---|---|
| **hapi** | **76** | **admin2 district** |
| ifrc | 11 | national |
| who | 3 | national |
| gfs | 1 | grid cell |
| gdacs | 1 | point buffer |

### What was built
**`admin_boundaries` + COD-AB loader** — 891 admin2 polygons across KE/ET/SO/UG/SD/SS.
P-code join verified end to end: **0 alerts skipped for missing geometry**.
Djibouti has no COD-AB GeoJSON (SHP/GDB only) and Eritrea has no HAPI series;
both are excluded explicitly rather than silently never alerting.

**`ingestion/hapi.py`** — dekadal rainfall anomaly per admin2 -> drought/flood
alerts. Thresholds: `<=50%` red drought, `<=67%` orange, `>=150%` orange flood,
`>=200%` red. Drought additionally requires **2 consecutive dry dekads** — one
dry ten-day window is weather, not drought, and without the run test a single
dekad would paint whole countries red.

**`ingestion/named_events.py`** — IFRC GO appeals + WHO Disease Outbreak News.
Both keyless. Gives HALI its first `locust` and `epidemic` alerts from real
named responses: Somalia Insect Infestation (opened 2026-07-27), Kenya Cholera,
Bundibugyo Ebola in Uganda, Ethiopia Landslide.

All three wired into the scheduler (HAPI 07:10, named events 07:25, ahead of the
07:45 population backfill) and exposed as admin endpoints.

### Bugs found by running it
1. **Every HAPI alert was born expired.** `valid_to = period_end + 14d`, but HAPI
   publishes a dekad well after it closes — the latest available on 2026-07-28
   ended 2026-07-10. All 76 alerts were already expired when written. Validity
   now runs from ingest time; `valid_from` still records when the condition was
   observed.
2. **IFRC appeal end dates run to 2028.** Honouring them literally parks an alert
   on the map for two years with nothing to refresh it. Capped at 60 days so it
   must be re-confirmed by the next run.
3. **Country-scoped alerts claimed the national population as "exposed".** An
   IFRC Ebola *readiness* appeal for Ethiopia reported 114,795,154 people
   exposed, which swamped every ranking next to a district drought affecting
   50,000. `ifrc`/`who` are now excluded from exposure entirely — NULL is the
   honest answer, and the UI already renders NULL as "not computed".
4. **National advisories buried the subnational alerts.** Drawn in the same layer,
   14 country-sized polygons painted straight over 78 district footprints — the
   exact problem the phase existed to fix. The API now emits `scope`
   (`local`/`national`) and the map splits them: districts filled, national
   advisories outline-only on their own toggle.

### Verified on the map
Zooming into Uganda shows individual districts carrying their own severity —
red, orange, and unaffected blank in between. That is the "drought in Turkana,
floods in Tana River" behaviour the request asked for.

Sample of what is now alertable, with real district names:
West Darfur/Jebel Moon, West Darfur/Kereneik, North Darfur/Saraf Omra,
Amhara/North Shewa, Dire Dawa rural, Uganda Eastern/Bugweri, Central/Kalangala.
Alert areas: min 195 km2, avg 2,294 km2, max 16,256 km2 — real districts, not
0.25 deg squares.

### Not built
- **FEWS NET IPC shapefiles** — needs a shapefile reader (no fiona/geopandas/pyshp
  installed); adding a dependency and a Docker rebuild was not worth it against
  the deadline once HAPI already delivered admin2 granularity. Highest-value
  remaining addition: 640 polygons per country at admin2 x livelihood zone.
- **USGS earthquakes** — verified working and keyless, but HALI has no earthquake
  hazard type and it is marginal for a flood/drought early-warning system.
- **NASA FIRMS wildfire** — key is emailed, not confirmed instant.

**Gate result:** backend `323 passed` (was 281), `ruff` clean,
frontend `50 passed`, `frontend:build` succeeds.

---

## PHASE 5c — FEWS NET IPC + HAPI identifier ✅ DONE (2026-07-28)

### Active alerts: 92 -> 537

| source | active | granularity |
|---|---|---|
| **fewsnet** | **445** | **admin2 x livelihood zone, unioned to district** |
| hapi | 76 | admin2 district |
| ifrc | 11 | national |
| who | 3 | national |
| gfs / gdacs | 2 | grid cell / point |

### HAPI identifier
`HAPI_EMAIL=martinmuga04@gmail.com` set on the Railway **backend** service with
`--skip-deploys` (nothing is committed yet, so a redeploy would have shipped the
old image). Derived identifier `aGFsaTptYXJ0aW5tdWdhMDRAZ21haWwuY29t` matches
what HAPI's own encode endpoint returns. Also added to local `.env`.

### FEWS NET IPC
New dependency: **pyshp 3.1.6** (pure Python, no GDAL).

`ingestion/fewsnet.py` downloads the IPC package per country, reads the `_CS`
(current situation) layer, keeps IPC phase >= 3, and unions the livelihood-zone
slivers into one polygon per district and phase.

- Phase 3 Crisis -> orange, phase 4 Emergency / 5 Famine -> red. Phases 1-2 are
  normal-to-difficult and would mark most of the region permanently.
- **Grouping matters**: Kenya's package holds 640 units, 272 at phase 3, which
  collapse to **36 districts**. One alert per sliver would have buried the map.
- `_CS` only. ML1/ML2 projections are in the archive and would make a good
  separate layer, but presenting a forecast as a current alert misrepresents it.
- Requests the **previous** month — the current month's classification is
  published during it.
- Djibouti and Eritrea excluded: both return a 4-byte empty archive.
- Weekly schedule, not daily. IPC is republished ~3x a year; a daily download of
  ~60 MB of shapefiles for unchanged data is pure waste.

Districts now alertable include Tana River/Garsen, Garissa/Dadaab, Wajir South —
the classic Kenyan food-insecurity districts, arriving already shaped correctly.

### Two performance problems this exposed
1. **Population backfill took ~9 minutes.** It ran one query per alert; fine at
   25 alerts, hopeless at 537, and almost all of it was network latency rather
   than work. Rewritten as a single set-based `UPDATE ... FROM`:
   **523 alerts in 2.9 s**.
2. **The map feed became 9.0 MB and 28 s.** FEWS NET district polygons are
   unions of livelihood-zone slivers — 331,507 vertices across 537 alerts, which
   is hopeless on the 2G this app targets. `/api/alerts/geojson` now simplifies
   at ~500 m (`MAP_GEOMETRY_TOLERANCE = 0.005`): **1.1 MB and 3.5 s**, an 8x cut,
   visually identical at the zoom levels the map permits. Analysis and AOI
   endpoints keep full precision.

### Still not built
- **ML1/ML2 IPC projections** — "where this is heading" as a distinct layer.
- **USGS earthquakes** — keyless and verified, but HALI has no earthquake hazard
  type and it is marginal for a flood/drought system.
- **NASA FIRMS wildfire** — key is emailed, not confirmed instant.

**Gate result:** backend `345 passed` (was 323), `ruff` clean,
frontend `50 passed`, `frontend:build` succeeds.

⚠️ **Deploy note:** `pyshp` is a new dependency, so the backend image must
rebuild. `poetry.lock` is updated and committed alongside.

---

## REFRESH CADENCE — measured, not assumed (2026-07-28)

All 9 scheduler jobs verified registered. `ENABLE_SCHEDULER=true` on Railway.

| source | HALI polls | source actually updates | observed lag | live? |
|---|---|---|---|---|
| IFRC GO | daily 07:25 | continuously | newest appeal **1 day** old | **yes** |
| WHO DON | daily 07:25 | continuously | newest notice **11 days** old | **yes** |
| GDACS | daily 06:00 | continuously | ongoing events, 60-day lookback | **yes** |
| GFS | daily 06:15 | 4x daily forecast | hours | **yes** |
| CHIRPS | daily 07:00 | dekadal | days | partly |
| **HAPI rainfall** | daily 07:10 | **dekadal (10 days)** | **18 days** | **partly** |
| **FEWS NET IPC** | weekly Mon 06:45 | **~every 4 months** | June release, live | **no — baseline** |
| pop_grid (WorldPop) | manual one-shot | annual | 2020 data | static by design |
| admin_boundaries | manual one-shot | years | — | static by design |

### The honest picture
- **445 of 537 active alerts (83%) come from FEWS NET**, which republishes a
  full analysis roughly three times a year. That layer is a slow-moving
  baseline, not early warning, and should be described as such.
- **HAPI is the fastest genuinely subnational signal at ~18 days** — dekadal
  data with a publication lag. Good for drought onset, useless for flash flood.
- The **fast** sources (GDACS, IFRC, WHO, GFS) are all either national or
  point-scale. Nothing HALI currently ingests is both subnational **and** faster
  than ~2 weeks.
- Community reports remain the only true real-time subnational input, which is
  what makes the DBSCAN hotspot layer (30-min interval) the genuinely novel part.

### Bug this investigation found
FEWS NET does **not** publish a current-situation layer every month. Verified
for Kenya 2026: only February and June carry `_CS`; January, March, April and
May carry projections (ML1/ML2) only, and July is empty. The adapter asked for
last month and read `_CS` only — so **from August it would have found nothing
and silently refreshed zero alerts until October**, while the existing ones aged
out at 120 days. Now walks back up to 8 months to find the newest real analysis.
Verified: starting from July (empty) it resolves to the June release.

### To make it genuinely faster (not built)
- **FEWS NET ML1** — near-term projection, updates *monthly* rather than every
  four. Would roughly triple refresh rate for the largest layer, at the cost of
  being a forecast rather than an observation.
- **ICPAC `eahazardswatch` weekly rainfall** — `weekly_extreme_heavy_rainfall`,
  `weekly_precipitation_anomaly` are weekly rather than dekadal, and regional.
- **CHIRPS-GEFS / GFS thresholds at admin2** — we already ingest both; joining
  them to `admin_boundaries` would give a daily subnational rainfall signal
  using infrastructure that now exists.

**Gate result:** backend `348 passed`, `ruff` clean.

---

## MAP PERFORMANCE at 537 alerts — measured (2026-07-29)

Asked directly: does FEWS NET slow the map down?

| metric | before | after | how fixed |
|---|---|---|---|
| geojson payload | **9.0 MB** | **1.1 MB** | `ST_SimplifyPreserveTopology` at ~500 m |
| vertices | 331,507 | 34,371 | same |
| server query time | — | **290 ms** | measured by EXPLAIN ANALYZE |
| SVG DOM paths | 554 | **0** | `preferCanvas: true` |
| total DOM nodes | 842 | **287** | same |

### What the numbers mean
- **290 ms is the real server cost.** The ~4 s I measured over HTTP is my
  laptop's link to Railway pulling 1.1 MB; in production the backend sits beside
  PostGIS, so that disappears.
- **1.1 MB is the number that matters for users.** On the 2G/3G this app targets
  that is roughly 3-10 s of download. It is cached by the service worker
  (`hali-alerts`, 5 min), so it is a first-load cost, not a per-interaction one.
  Without the simplification it would have been 9 MB and genuinely unusable.
- **Canvas rendering** replaces 554 SVG DOM elements with 2 canvases. With SVG
  the initial layer build produced a measured **2.9 s stall**; canvas draws to
  pixels rather than DOM so cost stops scaling with feature count.

### Measurement caveat
Frame-rate figures could not be measured reliably here: `requestAnimationFrame`
is throttled in a background tab, so several sampling runs returned zero frames.
The one SVG run that did capture data showed median 20.3 ms (~49 fps) with a
2.9 s worst frame. The canvas improvement is evidenced by the DOM reduction
(554 paths -> 0) rather than by a frame-rate comparison.

### Non-issues ruled out during this investigation
- **Duplicate geojson fetches** — 2x per endpoint in dev is React StrictMode.
  The production build fetches each exactly once. Verified.
- **Blank map in the production build** — twice a test-harness artifact, not a
  bug: first `CORS_ORIGINS` missing the preview port, then the PWA service
  worker serving a stale JS bundle from cache-storage.

### Worth knowing for deploys
The service worker will serve the **previous** bundle to returning users until it
updates. `registerType: 'autoUpdate'` handles this on the next load, but during
the demo a hard reload is the reliable way to guarantee the newest build.

---

## PHASE 6 — Ship (P0, ~0.25 day)

pytest + ruff + `nx run frontend:build`, commit **excluding `.md` files**
(standing instruction), push to `main`, watch CI, verify both Railway services.

---

## Risk register

| Risk | Mitigation |
|---|---|
| CHECK constraints break Phase 2 in prod | Migration 008 lands first; verify on Railway before code |
| Migration 008 must drop constraints by exact name | Read `pg_constraint` first, never guess names |
| USSD 182-char budget breaks with 10 langs / 7 livelihoods | Paginate menus; existing `test_ussd_budget.py` covers timing, add a length test |
| Country-centroid reports create fake DBSCAN clusters | `location_precision` filter (Phase 1/2.0) |
| WorldPop rasters large / slow | Run locally against Railway DB, code-only commit |
| New basemap hosts break offline PWA | Add to `runtimeCaching` in Phase 3 |
| Rate limits from mass re-translation | No mass backfill; on-demand + 5 recent alerts only |

## Deferred (post-hackathon)

GFS temperature thresholds for automated `heatwave` detection; CHIRPS extreme-rain
proxy for `landslide`. Community/manual reporting covers both for the demo.
