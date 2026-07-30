# HALI — Spatial Intelligence Audit

- **Run:** 2026-07-30
- **Target:** the deployed production system, not a local dev instance
- **API:** `https://backend-production-a6cf.up.railway.app`
- **Database:** Railway PostGIS — PostgreSQL 16.14, PostGIS 3.7

Every row below was produced by a command run against that live system on the
date above. Commands are included so a reviewer can re-run any of them. Where
something is partial or empty, it is marked and explained rather than dropped.

---

## Summary

| # | Capability | Status | Evidence, one line |
|---|---|---|---|
| 1 | Ingest spatial join | ✅ Pass | Alerts carry multi-country `affected_countries` from a real PostGIS join: `{SS,UG}`, `{KE,SS,UG}`, `{ET,SD}` |
| 2 | Point analyse | ✅ Pass | `lat=3.12,lng=35.60` → Kenya, 5 drought alerts at 0.0–64.1 km with population and 7-day report breakdown |
| 3 | AOI polygon query | ✅ Pass | 590,741 km² polygon → 96 alerts, 8 reports, 32,517,488 people, per-alert `overlap_km2` |
| 4 | DBSCAN emerging hotspots | ⚠️ Pass, thin data | Endpoint live and correct; **1** hotspot from 21 community reports — real but a small sample |
| 5 | Compound risk index | ✅ Pass | 8 country features with `alert_count`, `alert_area_pct`, `dominant_hazard` |
| 6 | Real geometry, not bounding boxes | ✅ Pass | `countries.geom` carries 187–972 vertices per country; areas match published land areas |
| 7 | Population exposure, zonal | ✅ Pass | 248,997-cell grid, 289,931,311 people, resolved in-database, no external call |
| 8 | Population exposure coverage | ⚠️ Partial | **93.5%** of alerts have a value; 37 of 567 are `null`, concentrated in the named-event adapters |
| 9 | District-level resolution | ⚠️ Pass, scoped | 891 admin2 polygons across **6** of 8 countries; Djibouti and Eritrea have no COD-AB geometry |
| 10 | USSD on live PostGIS | ✅ Pass | `POST /ussd` on the production callback returns the real menu, not a static fixture |

Response times measured the same day, cold, over the public internet:

```
/health                          200   1.19 s
/api/spatial/emerging-hotspots   200   0.79 s
POST /api/spatial/query-polygon  200   1.13 s
/api/spatial/analyse             200   1.77 s
/api/spatial/compound-risk       200   3.31 s
```

---

## 1. Ingest spatial join

Alerts must be attributed to countries by intersecting geometry, not by
copying a label off the source feed.

```sql
SELECT hazard_type, affected_countries, source
  FROM alerts ORDER BY created_at DESC LIMIT 5;
```

```
 hazard_type | affected_countries | source
-------------+--------------------+--------
 flood       | {SS,UG}            | hapi
 drought     | {KE,SS,UG}         | hapi
 drought     | {UG}               | hapi
 drought     | {UG}               | hapi
 flood       | {ET,SD}            | gfs
```

**Status: pass.** Multi-country arrays are the tell. A cross-border alert
resolving to `{KE,SS,UG}` can only come from a geometry intersection. All 567
alerts in the database have non-null `geom`.

---

## 2. Point analyse

```bash
curl -s "$API/api/spatial/analyse?lat=3.12&lng=35.60"
```

```json
{
  "location": {"lat": 3.12, "lng": 35.6},
  "country": "Kenya",
  "nearest_alerts": [
    {"hazard_type":"drought","severity":"orange","dist_km":0.0,"population_exposed":168255},
    {"hazard_type":"drought","severity":"orange","dist_km":3.9,"population_exposed":204214},
    {"hazard_type":"drought","severity":"orange","dist_km":12.2,"population_exposed":191335},
    {"hazard_type":"drought","severity":"orange","dist_km":47.9,"population_exposed":198086},
    {"hazard_type":"drought","severity":"orange","dist_km":64.1,"population_exposed":91528}
  ],
  "nearby_reports_7d": 1,
  "report_breakdown": [{"label":"flood","count":1},{"label":"road_blocked","count":1}],
  "emerging_hotspots_nearby": 0
}
```

**Status: pass.** The point is in Turkana. Reverse country lookup, ordered
distance in kilometres, per-alert population and a 7-day community report
breakdown all resolve server-side in one call. `dist_km: 0.0` means the point
falls inside that alert's polygon.

---

## 3. AOI polygon query

The draw-a-shape capability. Arbitrary polygon in, everything inside it out.

```bash
curl -s -X POST "$API/api/spatial/query-polygon" \
  -H "Content-Type: application/json" \
  -d '{"geometry":{"type":"Polygon","coordinates":[[[34,0],[42,0],[42,6],[34,6],[34,0]]]}}'
```

```json
{
  "area_km2": 590740.9,
  "alert_count": 96,
  "report_count": 8,
  "report_hazards": ["flood"],
  "emerging_hotspots": 0,
  "population_estimate": 32517488
}
```

**Status: pass.** The polygon spans the Kenya–Ethiopia–Somalia corridor. Every
returned alert carries its own `overlap_km2` — the intersection area with the
drawn shape, not the alert's full extent — which is a genuine `ST_Intersection`
computation. Largest overlap in this run: 337,440 km². Smallest: 4,446 km².

---

## 4. DBSCAN emerging hotspots

```bash
curl -s "$API/api/spatial/emerging-hotspots"
```

```json
{"type":"FeatureCollection","features":[{
  "type":"Feature",
  "geometry":{"type":"Point","coordinates":[42.7041,11.6028]},
  "properties":{
    "status":"UNCONFIRMED — no official alert",
    "confidence":1, "report_count":10,
    "dominant_hazard":"wildfire",
    "first_reported":"2026-07-29T21:55:20Z",
    "detected_at":"2026-07-30T15:51:22Z"
  }}]}
```

**Status: pass, on thin data — stated plainly.** The clustering job runs every
30 minutes and works: 10 community reports near Djibouti clustered into one
wildfire hotspot correctly labelled `UNCONFIRMED — no official alert`, which is
exactly the intended "community saw it before the satellites did" case.

The honest caveat: the database holds **21 community reports total**, so the
model is operating on a small sample and returns **1** cluster. This is a
demonstration of a working mechanism, not evidence of scale. A reviewer
querying this endpoint should expect one feature, not a map full of them.

---

## 5. Compound risk index

```bash
curl -s "$API/api/spatial/compound-risk"
```

| ISO2 | Country | Alerts | Max severity | Alert area km² | % of country | Dominant hazard |
|---|---|---|---|---|---|---|
| SO | Somalia | 121 | red | 594,014 | 92.9 | drought |
| SS | South Sudan | 105 | red | 624,690 | 99.7 | drought |
| SD | Sudan | 201 | red | 1,534,889 | 82.6 | drought |
| KE | Kenya | 75 | red | 361,704 | 61.7 | drought |
| UG | Uganda | 90 | red | 109,585 | 45.3 | drought |
| ET | Ethiopia | 92 | red | 568,346 | 50.4 | drought |
| ER | Eritrea | 15 | orange | 2,585 | 2.1 | drought |
| DJ | Djibouti | 6 | orange | 325 | 1.5 | flood |

**Status: pass.** All 8 IGAD states return. `alert_area_pct` is a real
`ST_Union` / `ST_Area` ratio against country geometry — note it is not a naive
sum, or the overlapping drought alerts would push it past 100%.

---

## 6. Real geometry, not bounding boxes

An early build used 5-point bounding boxes for country outlines. This checks
that Natural Earth geometry actually replaced them.

```sql
SELECT iso2, ROUND((ST_Area(geom::geography)/1e6)::numeric) AS km2,
       ST_NPoints(geom) AS vertices
  FROM countries ORDER BY iso2;
```

```
 iso2 |   km2   | vertices
------+---------+----------
 DJ   |   21847 |      187
 ER   |  122535 |      885
 ET   | 1127357 |      839
 KE   |  585764 |      665
 SD   | 1857199 |      908
 SO   |  639244 |      682
 SS   |  626863 |      972
 UG   |  241863 |      498
```

**Status: pass.** A bounding box has 5 vertices. These have 187 to 972. The
computed areas track published land areas closely — Kenya 585,764 km² against
a published 580,367 km², Ethiopia 1,127,357 against 1,104,300. The residual is
coastline and border generalisation at 1:10m, which is expected and correct.

---

## 7. Population exposure — zonal, not per-call

```sql
SELECT count(*) AS cells, SUM(pop)::bigint AS total_pop FROM pop_grid;
```

```
 cells  | total_pop
--------+-----------
 248997 | 289931311
```

**Status: pass.** The WorldPop 1km grid is resident in PostGIS. Exposure is a
`SUM(pop)` over cells intersecting the alert polygon — one in-database
operation with no external HTTP call, no per-day quota, and no failure mode
when WorldPop's API is slow.

This is a correction to the original specification, which described a per-call
lookup against `api.worldpop.org`. The shipped implementation is the stronger
one. See `01_TECHNICAL_SPECS.md` §4.4.

---

## 8. Population exposure coverage — partial, quantified

```sql
SELECT count(*) AS total, count(population_exposed) AS with_pop,
       count(*) - count(population_exposed) AS null_pop
  FROM alerts;
```

```
 total | with_pop | null_pop | pct
-------+----------+----------+------
   567 |      530 |       37 | 93.5
```

Nulls by source:

```
 source  | nulls | total
---------+-------+-------
 gfs     |    20 |    24
 ifrc    |    11 |    11
 who     |     3 |     3
 chirps  |     2 |     2
 manual  |     1 |     1
 fewsnet |     0 |   445
 hapi    |     0 |    80
 gdacs   |     0 |     1
```

**Status: partial — flagged deliberately.** 93.5% of alerts carry a population
figure. The 37 that do not are concentrated in the named-event adapters (IFRC
GO, WHO) whose geometry is coarse or country-wide, plus a GFS batch that
landed after the last 07:45 UTC backfill window.

A reviewer clicking a WHO epidemic alert **will** see a blank population field.
That is the truthful state of the data. `population_exposed` is typed nullable
precisely so that `null` reads as "not computed yet" and never as "nobody lives
here" — see `packages/types/src/index.ts`. The daily backfill job closes these
as geometry improves; it does not invent a number in the meantime.

---

## 9. District-level resolution — scoped

```sql
SELECT count(*) AS districts, count(DISTINCT iso2) AS countries
  FROM admin_boundaries;
```

```
 districts | countries
-----------+-----------
       891 |         6
```

**Status: pass, with a stated scope limit.** 891 OCHA COD-AB admin2 polygons
are loaded, covering 6 of the 8 IGAD states. Djibouti and Eritrea are absent
because no authoritative COD-AB geometry or matching rainfall series exists for
them at admin2 level. They remain covered at country level — both appear in the
compound risk table in check 5. This is a data availability limit upstream of
HALI, and the packet states it rather than implying 8-country district coverage.

---

## 10. USSD against live PostGIS

```bash
curl -s -X POST "$API/ussd" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "sessionId=judge-test-1&serviceCode=*384*97980#&phoneNumber=%2B254700000000&text="
```

```
CON Welcome to HALI
1. Latest alert
2. Report hazard
3. Get SMS alerts
4. About HALI
```

**Status: pass.** This is the production callback that Africa's Talking hits.
Menu option 1 runs a live PostGIS query for the caller's nearest alert; it is
not a static text fixture.

**Caveat:** the Africa's Talking account is a **sandbox** account. The channel
`*384*97980#` is dialable in the AT web simulator; it is not provisioned on a
carrier network for dialling from an ordinary handset. Promoting it to a
production short code is a commercial step, not an engineering one.

---

## What this audit does not cover

- **WhatsApp end to end.** The webhook and signature verification are built and
  the Meta test number is configured, but exercising it requires a session on
  the tester allow-list, which cannot be scripted from here. Not claimed as
  verified.
- **The four flag-gated adapters.** CHIRPS, GFS, GloFAS and ICPAC SPI are built
  and tested but off by default. GFS and CHIRPS alerts exist in the database
  from earlier enabled runs (24 and 2 respectively); GloFAS and ICPAC SPI have
  produced none.
- **Load or concurrency behaviour.** Every timing above is a single cold
  request. No throughput claim is made.
