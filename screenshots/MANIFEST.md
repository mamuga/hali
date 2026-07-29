# HALI Screenshot Manifest

Captured 2026-07-30 against the live Railway deployment:
`https://frontend-production-ba31.up.railway.app/` and
`https://landing-production-d6be4.up.railway.app/`.

The map capture contains live FEWS NET district polygons, the separate IPC
layer toggle, compound-risk ranking, community heatmap, and the seeded live
emerging-hotspot marker. The six GPS community reports used for the hotspot
were submitted through `/api/reports` and persisted in Railway PostGIS; the
existing DBSCAN admin job detected and stored the cluster.

The displaced/camp action card used in slot #7 was added for the selected live
alert in Railway PostGIS and verified through `/api/alerts/{id}/action-card`.

| File | Devpost gallery slot | Status |
|---|---:|---|
| `01-district-choropleth.png` | #1 | captured live — FEWS NET district polygons visible |
| `02-ipc-food-insecurity.png` | #2 | captured live — IPC layer visible in the layer control |
| `03-alert-zones-icpac-wms.png` | #3 | captured live — alert zones composited with ICPAC flood-prone WMS |
| `04-compound-risk-choropleth.png` | #4 | captured live — compound risk and ranked panel visible |
| `05-emerging-hotspot-popup.png` | #5 | captured live — six-report wildfire cluster, no official alert |
| `06-aoi-polygon-query.png` | #6 | captured live — alerts, 7 reports, 1 hotspot, population visible |
| `07a-action-card-farmer.png` | #7 | captured live — farmer card |
| `07b-action-card-pastoralist.png` | #7 | captured live — pastoralist card |
| `07c-action-card-displaced.png` | #7 | captured live — displaced/camp card |
| `07-action-card-comparison.png` | #7 | captured live — side-by-side composite |
| `08a-language-dropdown-open.png` | #8 | captured live — all 10 language options visible |
| `08b-alert-in-swahili-or-amharic.png` | #8 | captured live — Swahili alert and action content |
| `09-alert-feed-mobile-dark.png` | #9 | captured live — 390x844 dark-mode viewport |
| `10-whatsapp-conversation` | #10 | MANUAL — requires WhatsApp Web/phone session |
| `11-ussd-simulator` | #11 | MANUAL — requires Africa’s Talking dashboard login |
| `12-architecture-diagram.png` | #12 | captured/generated from the documented HALI stack; editable SVG source included |
| `13-report-submit-toast.png` | #13 | captured live — Sonner success toast after submission |
| `14-admin-ai-stats.png` | #14 | captured live — formatted response from protected Railway endpoint |
| `15-landing-hero.png` | #15 | captured live — Railway landing site |

Total automated/live captures: 12/15. Total requiring manual platform access:
2/15. Slot #12 is a designed architecture asset based on the implemented stack,
not a screenshot of a live UI.
