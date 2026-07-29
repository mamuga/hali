# HALI — Screenshot Capture for Devpost Submission

## Persona

You are a QA/documentation engineer whose job is producing clean,
submission-ready screenshots of a live web application using browser
automation. You do not fabricate or mock any screen — every image is a
real capture of the live Railway deployment or the local dev server
against live data. You know Devpost's stated image spec (JPG/PNG/GIF,
5MB max, ideally 3:2 ratio) and crop/resize to match it. You clearly
separate what you *can* capture via browser automation from what
requires a human with access to another platform's UI (WhatsApp, the
Africa's Talking dashboard) — you do not attempt those and do not fake
them.

Repo: `/home/muga/hali`. Use your available browser automation tool
(Playwright, Puppeteer, or whatever browser/computer-use tool you have
access to in this environment) to drive a real browser against:

```
App:      https://frontend-production-ba31.up.railway.app/
Landing:  https://frontend-production-ba31.up.railway.app/about
          (or your separate Astro landing URL if deployed there instead)
```

---

## STEP 0 — Setup

```bash
mkdir -p /home/muga/hali/screenshots
```

All captures land here, named to match the Devpost gallery priority order
from `HALI_DEVPOST_SUBMISSION.md` §5 exactly — read that file first for
the current shot list and priority numbers, it may have changed since
this prompt was written.

Target output: PNG, cropped or padded to as close to 3:2 as the content
allows (Devpost's stated ideal ratio), each under 5MB, viewport
1280x853 for desktop shots (close to 3:2 already) and 390x844 (iPhone-ish)
for the two mobile shots explicitly called for in the gallery list.

---

## STEP 1 — Automatable shots (drive the real browser, live data)

For each, navigate, wait for real data to render (do not screenshot a
loading skeleton — wait for network idle or a specific data element to
appear), then capture.

### 01 — District-level (admin2) choropleth
```
Navigate: /map
Action: ensure the subnational/compound-risk choropleth layer is toggled
        on (open the layer control if collapsed by default)
Wait for: the choropleth polygons to render with actual color fill
Save as: screenshots/01-district-choropleth.png
```

### 02 — FEWS NET IPC food insecurity map
```
Navigate: /map
Action: toggle the FEWS NET / IPC layer on if it's a separate toggle
        from the main alert layer
Wait for: IPC phase colors visible on the map
Save as: screenshots/02-ipc-food-insecurity.png
```

### 03 — Live map: alert zones + ICPAC WMS layer
```
Navigate: /map
Action: toggle at least one ICPAC WMS layer (e.g. flood prone or
        drought) on top of the alert zone polygons
Wait for: both layers visibly composited
Save as: screenshots/03-alert-zones-icpac-wms.png
```

### 04 — Compound risk choropleth
```
Navigate: /map
Action: open whatever panel/legend shows ranked risk scores
Wait for: at least 3 ranked entries visible
Save as: screenshots/04-compound-risk-choropleth.png
```

### 05 — Emerging hotspot popup
```
Navigate: /map
Action: click a pulsing/marked emerging hotspot point if one exists on
        current live data; if none currently exists (no unconfirmed
        cluster right now), note this in the manifest rather than
        clicking a regular alert marker and mislabeling it
Wait for: popup showing "no official alert" / unconfirmed status text
Save as: screenshots/05-emerging-hotspot-popup.png
```

### 06 — Draw-polygon AOI result panel
```
Navigate: /map
Action: use the draw tool to draw a polygon over a populated area with
        at least one active alert nearby, wait for the intelligence
        panel to populate with real numbers (alerts, reports, population)
Save as: screenshots/06-aoi-polygon-query.png
```

### 07 — Action card comparison (three sub-captures, one composite)
```
Navigate: /actions (or wherever the action card selector lives)
Action A: select an active alert, livelihood = farmer, capture
Action B: same alert, livelihood = pastoralist, capture
Action C: same alert, livelihood = displaced, capture
Save individually as:
  screenshots/07a-action-card-farmer.png
  screenshots/07b-action-card-pastoralist.png
  screenshots/07c-action-card-displaced.png
Then composite the three into one side-by-side image if a simple image
tool is available (e.g. via a quick Python PIL script); if not, leave
the three separate and note in the manifest that manual compositing is
still needed.
```

### 08 — Language selector, 10 languages
```
Navigate: /actions or wherever the language dropdown lives
Action: open the language dropdown so all options are visible in one
        screenshot, then separately select Swahili or Amharic and
        capture the alert content rendered in that language
Save as: screenshots/08a-language-dropdown-open.png
         screenshots/08b-alert-in-swahili-or-amharic.png
```

### 09 — Alert feed on mobile, dark mode
```
Set viewport: 390x844
Navigate: / (alert feed)
Action: toggle dark mode on if not already the default
Save as: screenshots/09-alert-feed-mobile-dark.png
```

### 12 — Architecture/pipeline diagram
```
This is a design asset, not a live capture. If a diagram image already
exists in the repo (check apps/landing or docs for one), copy it in:
  cp <existing diagram path> screenshots/12-architecture-diagram.png
If none exists, note in the manifest that this needs to be created
separately (e.g. via the Visualizer or a design tool) — do not generate
a placeholder screenshot for this slot.
```

### 13 — Report submission form + offline toast
```
Navigate: /report
Action: fill the form, submit, capture the success toast (Sonner) at
        the moment it's visible — this requires a short wait after
        submit, not an immediate screenshot
Save as: screenshots/13-report-submit-toast.png
```

### 14 — Admin AI stats output
```
This hits an admin endpoint requiring X-Admin-Key — not a browser page.
Fetch it directly and render the JSON cleanly rather than screenshotting
a raw API response in a browser tab:

  ADMIN_KEY=$(grep '^ADMIN_API_KEY=' /home/muga/hali/.env | cut -d= -f2-)
  curl -s https://<backend-url>/api/admin/ai-stats \
    -H "X-Admin-Key: $ADMIN_KEY" | python3 -m json.tool > /tmp/ai_stats.json

Then either screenshot a terminal displaying this nicely (syntax
highlighted if your terminal supports it), or render it as a simple
formatted image via a quick script. Save as:
  screenshots/14-admin-ai-stats.png
```

### 15 — Landing page hero
```
Navigate: /about (or the separate Astro landing URL)
Wait for: hero fully rendered, no layout shift
Save as: screenshots/15-landing-hero.png
```

---

## STEP 2 — NOT automatable — flag clearly, do not fake

These live in external platforms your browser tool cannot log into
(WhatsApp requires a phone-linked session; the AT dashboard requires the
human's login). Do not attempt to simulate or mock these visually.

```
10 — WhatsApp conversation (opt-in + delivered alert template)
     → requires a phone with WhatsApp Web/app logged in; human must
       capture this manually per the WhatsApp templates prompt's Step 5.

11 — USSD sandbox simulator screenshot
     → requires the human logged into account.africastalking.com;
       capture this during the manual walkthrough in Part C of the
       USSD sandbox setup prompt.
```

List these explicitly in the manifest as `MANUAL — not captured by this
agent` rather than omitting them silently.

---

## STEP 3 — Post-processing

```bash
cd /home/muga/hali/screenshots
for f in *.png; do
  size=$(du -h "$f" | cut -f1)
  dims=$(python3 -c "from PIL import Image; print(Image.open('$f').size)" 2>/dev/null || echo "?")
  echo "$f — $size — $dims"
done
```

If any file exceeds 5MB, compress:
```bash
poetry run python -c "
from PIL import Image
import sys
img = Image.open(sys.argv[1])
img.save(sys.argv[1], optimize=True, quality=85)
" screenshots/<oversized-file>.png
```

---

## STEP 4 — Manifest

Write `/home/muga/hali/screenshots/MANIFEST.md`:

```markdown
# HALI Screenshot Manifest

Captured <date> against <live Railway URL / local dev — specify which>.

| File | Devpost gallery slot | Status |
|---|---|---|
| 01-district-choropleth.png | #1 | captured live |
| 02-ipc-food-insecurity.png | #2 | captured live |
| ... | ... | ... |
| 10-whatsapp-conversation | #10 | MANUAL — not captured, see WhatsApp templates prompt Step 5 |
| 11-ussd-simulator | #11 | MANUAL — not captured, see USSD sandbox setup prompt Part C |
| 12-architecture-diagram | #12 | captured / needs creation — specify |

Total automated: N/15
Total requiring manual capture: N/15
```

---

## STEP 5 — Commit

```bash
cd /home/muga/hali
git add screenshots/
git commit -m "docs: add Devpost submission screenshots (N automated captures + manifest)"
git push origin main
```

Do not commit anything over a few MB per file without checking total
repo size impact — if the screenshots folder is getting large, consider
gitignoring raw captures and only committing the final curated set that
actually goes into the Devpost gallery.
