# HALI — Devpost Submission Package

Deadline: Jul 31, 2026 @ 17:00 EAT. Top 10 present at the physical workshop.
Top 5 get cash ($4000/$2500/$1500/$1000/$1000). Positions 6-10 get the
workshop only, no cash. **Aim everything at technical + AI + impact —
that's 85% of the score combined.**

---

## 1. Project Overview (max 250 words) — READY TO PASTE, ~230 words

```
East Africa faces recurring floods, drought, disease outbreaks, and food
insecurity, yet the region's leading early-warning platform, ICPAC's
Husika, only reaches people already registered through a subscribing
organisation. A pastoralist with no NGO affiliation receives nothing,
even when 48 hours' notice could mean survival.

HALI closes that gap. It ingests live data from 13 sources, including
FEWS NET's IPC food insecurity classifications, HDX rainfall anomalies,
GDACS, CHIRPS, NOAA's GFS forecast, IFRC's appeal data, and WHO's disease
outbreak feed, and turns it into action within minutes, with no
registration required. Alerts are translated into ten languages by a
three-model AI ensemble scored for clarity, then paired with guidance
tailored to seven livelihoods, from pastoralists to displaced
populations, resolved down to the district level using 891 subnational
administrative boundaries, not just country outlines.

Delivery meets people on whatever device they already own: USSD for a
basic phone with no data, WhatsApp for a smartphone, or a full spatial
web app for coordinators, backed by a real population layer of 289
million people ingested from WorldPop, not a live external lookup.
Community members report what they see, and those reports cluster to
surface emerging hazards before any official alert exists, sometimes
escalating severity automatically.

HALI is designed to complement Husika's organisational reach, extending
early warning to the last mile: the person with a phone and no
subscription who needs to know what is coming, in their own language, now.
```

---

## 2. Solution Details (max 250 words) — READY TO PASTE, ~245 words
### (right at the cap — if Devpost flags it over, cut the Djibouti/Eritrea
### parenthetical first; that nuance already lives in the Project Story)

```
HALI runs on FastAPI and PostgreSQL with PostGIS, deployed across three
Railway services with GitHub Actions testing against a live PostGIS
container before every deploy.

An automated ETL pipeline ingests 13 external sources on independent
schedules: FEWS NET IPC food insecurity classifications, HDX HAPI
rainfall anomalies, GDACS, CHIRPS, NOAA GFS, IFRC GO appeals, WHO disease
outbreak news, plus three one-shot reference layers — WorldPop's 1km
population grid (248,997 cells, 289 million people), Natural Earth
country boundaries, and OCHA's COD-AB subnational administrative
polygons (891 districts across six countries; Djibouti and Eritrea are
honestly absent where no authoritative geometry or rainfall series
exists). Each adapter is isolated so one failure never blocks another,
loads are idempotent, and every raw record is dead-letter tracked for
replay. A cross-border attribution bug, where two of our highest-volume
adapters were bypassing the loader's spatial join, was caught and fixed
against live production data.

Every alert is processed by a three-model AI ensemble, Claude, Gemini,
and Groq, scored against a five-dimension clarity rubric so the clearest
translation wins. Ten languages are supported, including Tigrinya,
Luganda, and Afar, with seven livelihood-specific action plans per alert.

The spatial layer computes a compound risk index per country and
district, real population exposure from the ingested WorldPop grid, and
a DBSCAN model that clusters community reports to surface hazards with
no matching official alert. Users can draw a polygon on the map and
query every alert, report, and population figure inside it.

Delivery spans USSD, a WhatsApp bot on Meta's Cloud API, and an
offline-capable PWA, with rate limiting, input validation, and
poisoning-resistant escalation on every public endpoint.
```

---

## 3. Built With tags (pick your best 25, Devpost autocompletes most)

```
FastAPI, Python, PostgreSQL, PostGIS, React, TypeScript, Vite, TailwindCSS,
shadcn/ui, Leaflet, Astro, Claude API, Anthropic, Google Gemini, Groq,
scikit-learn, APScheduler, asyncpg, Africa's Talking, WhatsApp Business
Platform, Railway, Docker, GitHub Actions, FEWS NET, HDX
```

Thirteen data sources won't all fit as tags — the ones above cover the
technology; the source breadth is the Solution Details field's job.
If you want to swap two in, `IFRC GO` and `WorldPop` are the next most
recognizable to judges over `Docker`/`GitHub Actions`.

---

## 4. "Try it out" links

```
Primary:  https://frontend-production-ba31.up.railway.app/about
          (or your Astro landing URL once deployed — submit THIS as the
          main link, not the bare app)
Second:   https://frontend-production-ba31.up.railway.app/  (the live app)
Third:    <your public GitHub repo URL>
```

---

## 5. Image gallery — shot list (up to 15, 3:2 ratio, prioritized)

Capture in this order if time runs short — first 8 matter most now that
subnational data raises the GIS ceiling:

1. **District-level (admin2) choropleth**: 891 subnational polygons, not
   country-level bboxes — this is the single biggest visual upgrade over
   Husika and worth leading with for the GIS judges
2. **FEWS NET IPC food insecurity map**: a recognizable humanitarian
   visualization type (IPC phase classification) that signals real
   data integration, not a toy dataset
3. **Live map**: alert zones colored by severity + ICPAC WMS layer toggled on
4. **Compound risk choropleth**: ranked country/district risk scores visible
5. **Emerging hotspot popup**: pulsing dot showing "no official alert" status
6. **Draw-polygon AOI result panel**: a shape drawn with the intelligence
   panel open showing alerts/reports/population inside it
7. **Action card comparison**: same alert, farmer vs pastoralist vs
   displaced side by side (crop three screenshots into one image)
8. **Language selector**: showing all 10 languages, one alert open in
   Swahili or Amharic script
9. Alert feed on mobile (dark mode) — shows PWA polish
10. WhatsApp conversation: opt-in flow + a delivered alert template
11. USSD session (Africa's Talking sandbox simulator screenshot)
12. Architecture/pipeline diagram showing all 13 sources feeding the ETL
13. Report submission form + offline queue toast (Sonner)
14. Admin `/api/admin/ai-stats` output showing ensemble provider counts
15. Landing page hero

**Do not include a direct Husika-vs-HALI comparison graphic in the public
gallery.** Save that framing for spoken narrative at the workshop, phrased
as complementary — a judge built Husika, and a public "we're better than
you" image reads very differently than the same point made in conversation.

---

## 6. Demo video script (5:00 max) — time-boxed to judging weights

| Time | Segment | Criteria weighted |
|---|---|---|
| 0:00-0:30 | Hook: the registration gap. "A pastoralist with no NGO affiliation gets nothing from existing systems." State it, don't dwell. | Impact |
| 0:30-1:15 | Open the live PWA cold, no login. Alert feed in Swahili. Switch language live to French or Amharic — content actually changes. | Technical + Impact |
| 1:15-2:15 | Map: toggle ICPAC WMS layer on top of alert zones. Show compound risk choropleth. **Draw a polygon live** and show the intelligence panel populate with real numbers. This is your GIS-judge moment — slow down here. | Technical + Innovation |
| 2:15-3:15 | AI layer: open `/api/admin/ai-stats`, show ensemble provider split. Show the same alert's action card for pastoralist vs displaced — genuinely different content, not a template swap. | Innovation (AI Creativity) |
| 3:15-4:00 | Community loop: submit a report via WhatsApp on screen. Cut to the map — a hotspot appears labeled "no official alert." This is the single most novel capability — give it room. | Innovation + Impact |
| 4:00-4:30 | Dial the USSD code on a real or simulated feature phone. Get an alert with zero data, zero smartphone. | Impact (last mile) |
| 4:30-5:00 | Architecture diagram flash (2-3 sec), one-line close: "Husika reaches an organisation. HALI reaches a phone." GitHub link on screen. | Presentation |

Record in landscape, 1080p minimum. Subtitle the Swahili/Amharic text on
screen in English for judges who don't read it — this matters for the
15% Presentation score.

---

## 7. Project Story (Markdown field — paste and personalize the italicized parts)

```markdown
## Inspiration

East Africa loses lives every rainy season to floods, drought, and
locusts that are increasingly predictable from satellite data, yet that
data rarely reaches the person who needs it most. We looked at ICPAC's
own Husika platform and found it excellent for organisational broadcast,
but structurally unable to reach anyone outside a subscribed
organisation's list. HALI exists to close that specific gap: the last
mile, the person with a phone and no subscription.

## What it does

HALI ingests hazard and condition data from 13 external sources —
including FEWS NET's IPC food insecurity classifications, HDX's rainfall
anomaly feed, GDACS, CHIRPS, NOAA's GFS forecast, IFRC's appeal data, and
WHO's disease outbreak news — automatically, on independent schedules,
with no human writing the alert. Three reference datasets sit underneath
it: a WorldPop population grid (248,997 cells, 289 million people), Natural
Earth country boundaries, and 891 OCHA COD-AB subnational district
polygons across six countries, giving HALI district-level resolution that
country-level tools can't match. A three-model AI ensemble (Claude,
Gemini, Groq) translates every alert into ten languages and generates
livelihood-specific action guidance for seven groups, from farmers to
displaced populations. Delivery happens over USSD, WhatsApp, or a spatial
PWA, whichever the person already has. Community reports feed back in: a
DBSCAN clustering model detects emerging hazards before any official
alert exists, and enough corroborating reports can automatically escalate
an alert's severity.

## How we built it

*Describe your actual build sequence here — DB → ingestion → AI →
frontend → messaging → GIS layer. Mention the Nx monorepo, Railway
three-service deployment, GitHub Actions CI gating every deploy on a
live PostGIS test container.*

## Challenges we ran into

Our two highest-volume adapters, FEWS NET and HDX HAPI, together account
for over 97% of our alert volume, and for a stretch they were both
silently bypassing our loader's spatial join — meaning alerts weren't
being correctly attributed to the country whose polygon they actually
intersected. It only surfaced once alert counts across countries stopped
matching what we expected from source coverage, and we traced it back to
an assumption the loader made about a field FEWS NET and HDX structure
differently from GDACS. Fixing it against live production data, not a
synthetic test fixture, was the right call but a nervous one.

*Add your own — e.g. "GDACS returns `properties.url` as a dict for some
events, which broke our normaliser until we added explicit type
coercion." "Free-tier rate limits on Gemini (5 req/min) and Groq (30
req/min) meant our AI backlog processor needed a concurrency cap and
batching strategy." "Our first country boundaries were bounding boxes,
not real geometry, which silently broke our compound risk choropleth
until we re-ingested from Natural Earth."*

## Accomplishments that we're proud of

A fully automated pipeline running with zero human content authorship
across 13 live sources — every alert, translation, and action card is
machine-generated and verified end to end against live data, resolved
down to 891 subnational districts, not just 8 country outlines. A DBSCAN
model that finds hazards no official system has flagged yet. Ten
languages, including three — Tigrinya, Luganda, Afar — that no existing
regional tool serves. A real population layer of 289 million people, not
a per-call external lookup. And the honesty to leave Djibouti and Eritrea
out of our subnational layer rather than fake geometry that doesn't exist.

## What we learned

*Personal — what surprised you technically or about the humanitarian
problem space.*

## What's next for HALI

Business Verification with Meta to lift the WhatsApp template limit,
CHIRPS/GFS/GloFAS/ICPAC sources enabled beyond GDACS, and a direct
conversation with ICPAC about integrating HALI's community-triggered
escalation signal into their own Thresholds and Triggers system.
```

---

## 8. Additional info (private upload, judges only, zip up to 35MB)

This field is NOT public — use it for depth without bloating the public
story. Zip and upload:

```
docs/ARCHITECTURE.md   (the full 13-section spec doc)
architecture-diagram.png           (export from your pipeline diagram)
spatial-intelligence-audit.md      (the 8-capability verification table)
```

This is where the judges who dig deeper — likely Jason Kinyua and
Crimson Sikolia — find the depth that a 250-word field can't hold.

---

## 9. Final priority order for remaining time

1. Paste Overview + Solution Details (5 min) — do this first, it's done
2. Fill Built With tags + Try it out links (5 min)
3. Record demo video following the script above (2-3 hours including retakes)
4. Capture image gallery, screenshots 1-6 minimum (1 hour)
5. Write Project Story, personalize the italicized sections honestly (30 min)
6. Zip and upload Additional info (10 min)
7. Confirm GitHub repo is public, README is current
8. Submit with time to spare — do not submit at the deadline minute
