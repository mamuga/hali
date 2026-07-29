# HALI demo video — edit guide

Web clips were recorded against the live Railway deployment at
`https://frontend-production-ba31.up.railway.app`. They are 1920x1080 and
include a visible purple cursor. USSD and WhatsApp are intentionally left for
the human phone recording.

| Order | Segment | Source | Target | Narration |
|---|---|---|---:|---|
| 1 | Cold open, no login, live alerts | `captioned-01.mp4` | 0:20 | “A pastoralist with no organisation affiliation gets nothing from existing systems. This is HALI, open with no login at all.” |
| 2 | Live language switch | `captioned-02.mp4` | 0:25 | “Every alert is machine-translated into ten languages, scored for clarity across three AI models, not looked up from a static table.” |
| 3 | Insert USSD phone clip here | human recording | 0:25 | “The same alert reaches a feature phone with no data connection, over USSD, in seconds.” |
| 4 | Map: ICPAC layers and district risk | `captioned-03.mp4` | 0:30 | “This map blends ICPAC’s own hazard layers with district-level risk scoring across subnational boundaries, not eight country rectangles.” |
| 5 | Draw-polygon AOI query | `captioned-04.mp4` | 0:25 | “Draw any area and query every alert, community report, and population figure inside it, live.” |
| 6 | AI ensemble stats | `captioned-05.mp4` | 0:20 | “Claude, Gemini, and Groq run in parallel on every translation. The highest-scoring output wins, and we can prove which model won.” |
| 7 | Action card comparison | `captioned-06.mp4` | 0:25 | “The same flood alert produces genuinely different guidance for a farmer, a pastoralist, and a displaced household.” |
| 8 | Insert WhatsApp phone clip here | human recording | 0:20 | “Submit what you see over WhatsApp, in your own language.” |
| 9 | Report triggers hotspot | `captioned-07.mp4` | 0:25 | “That report just contributed to a cluster with no official alert yet, detected before any authority declared it.” |
| 10 | Close, title card | last frame or title card | 0:15 | “Husika reaches an organisation. HALI reaches a phone.” |

`demo/clips/web-segments-rough-cut.mp4` is a web-only review preview. Add the
two phone clips, narration, transitions, and the close in any editor, then
export the final cut at 1080p.

## Live-data gate

- Production health: database and PostGIS connected.
- Swahili, French, and Amharic alerts: present.
- Compound risk: 8 scored district/country features.
- Emerging hotspot: 1 live DBSCAN-generated hotspot.
- AI ensemble: active; the capture read live Claude 0, Gemini 2, Groq 41.
- Farmer, pastoralist, and displaced/camp action cards: present and distinct.

The admin key is used only for the beat 05 request and is never rendered or
written into a clip.
