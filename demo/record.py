"""Record HALI's live web demo beats.

Usage: python3 demo/record.py [1|2|3|4|5|6|7|all]
"""
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

APP_URL = os.getenv("HALI_APP_URL", "https://frontend-production-ba31.up.railway.app")
API_URL = os.getenv("HALI_API_URL", "https://backend-production-a6cf.up.railway.app")
VIEWPORT = {"width": 1920, "height": 1080}
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "demo" / "raw"
CLIPS = ROOT / "demo" / "clips"
CURSOR_JS = (ROOT / "demo" / "cursor-overlay.js").read_text()


async def new_page(browser, number):
    out_dir = RAW / f"{number:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    context = await browser.new_context(
        viewport=VIEWPORT,
        record_video_dir=str(out_dir), record_video_size=VIEWPORT,
        geolocation={"latitude": 11.603, "longitude": 42.704}, permissions=["geolocation"],
    )
    page = await context.new_page()
    await page.add_init_script(CURSOR_JS)
    await page.add_init_script("window.addEventListener('load', () => window.__installCursor());")
    return context, page


async def smooth_move(page, x, y, steps=25):
    center = await page.evaluate("({x: window.innerWidth/2, y: window.innerHeight/2})")
    await page.mouse.move(center["x"], center["y"])
    await page.mouse.move(x, y, steps=steps)


async def finish(context, page, number):
    await page.wait_for_timeout(900)
    video = page.video
    await context.close()
    if video:
        source = Path(await video.path())
        target = CLIPS / f"beat-{number:02d}.webm"
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
        print(f"wrote {target} ({target.stat().st_size:,} bytes)")


async def wait_for_map(page):
    await page.goto(f"{APP_URL}/map", wait_until="networkidle", timeout=60_000)
    await page.locator('[aria-label*="early warning map"]').wait_for(state="visible", timeout=30_000)
    await page.get_by_text("Most at risk now", exact=False).wait_for(state="visible", timeout=30_000)
    await page.wait_for_timeout(2200)


async def beat_01(browser):
    context, page = await new_page(browser, 1)
    await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(4200)
    await finish(context, page, 1)


async def beat_02(browser):
    context, page = await new_page(browser, 2)
    await page.goto(f"{APP_URL}/", wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(1600)
    selector = page.locator("button[aria-label='Select language']")
    box = await selector.bounding_box()
    if box:
        await smooth_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await selector.click(); await page.wait_for_timeout(700)
    await page.get_by_role("option", name=re.compile("Français")).click()
    await page.wait_for_timeout(2200)
    await selector.click(); await page.wait_for_timeout(500)
    await page.get_by_role("option", name=re.compile("አማርኛ")).click()
    await page.wait_for_timeout(2600)
    await finish(context, page, 2)


async def beat_03(browser):
    context, page = await new_page(browser, 3)
    await wait_for_map(page)
    await page.get_by_text("Alert zones", exact=True).click(); await page.wait_for_timeout(600)
    await page.get_by_text("Flood prone areas", exact=True).click(); await page.wait_for_timeout(5000)
    await page.get_by_text("Compound risk", exact=True).click(); await page.wait_for_timeout(2200)
    await finish(context, page, 3)


async def beat_04(browser):
    context, page = await new_page(browser, 4)
    await wait_for_map(page)
    polygon = page.locator(".leaflet-pm-icon-polygon").first
    await polygon.wait_for(state="visible", timeout=15_000)
    box = await polygon.bounding_box()
    await smooth_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await polygon.click()
    map_box = await page.locator('[aria-label*="early warning map"]').bounding_box()
    points = [(map_box["x"] + 575, map_box["y"] + 185), (map_box["x"] + 865, map_box["y"] + 185),
              (map_box["x"] + 865, map_box["y"] + 475), (map_box["x"] + 575, map_box["y"] + 475)]
    for x, y in points:
        await smooth_move(page, x, y, 15); await page.mouse.click(x, y); await page.wait_for_timeout(450)
    await page.mouse.click(points[0][0], points[0][1])
    await page.get_by_label("Area of interest").wait_for(state="visible", timeout=30_000)
    await page.wait_for_timeout(2400)
    await finish(context, page, 4)


async def beat_05(browser):
    """Fetch the protected live response; render only the response, never the key."""
    key = os.getenv("ADMIN_API_KEY") or next((line.split("=", 1)[1].strip() for line in (ROOT / ".env").read_text().splitlines() if line.startswith("ADMIN_API_KEY=")), "")
    import urllib.request
    request = urllib.request.Request(f"{API_URL}/api/admin/ai-stats", headers={"X-Admin-Key": key})
    with urllib.request.urlopen(request, timeout=30) as response:
        stats = json.loads(response.read())
    context, page = await new_page(browser, 5)
    await page.set_content(f"""<!doctype html><html><head><style>
      * {{ box-sizing:border-box }} body {{ margin:0; background:#07111f; color:#dbeafe; font:24px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace }}
      main {{ width:1920px; min-height:1080px; padding:130px 180px }} .window {{ border:1px solid #334155; border-radius:16px; overflow:hidden; box-shadow:0 20px 80px #0008; background:#0f172a }}
      .bar {{ height:58px; padding:13px 22px; background:#1e293b; color:#94a3b8; font:18px system-ui }} .dot {{ display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:8px;background:#7f77dd }}
      pre {{ margin:0; padding:36px 44px; color:#c4b5fd; white-space:pre-wrap }} .prompt {{ color:#67e8f9 }}
    </style></head><body><main><div class="window"><div class="bar"><span class="dot"></span>hali · live admin terminal</div><pre><span class="prompt">$</span> Querying live AI ensemble statistics...

{json.dumps(stats, indent=2)}</pre></div></main></body></html>""")
    await page.wait_for_timeout(3300)
    await finish(context, page, 5)


async def beat_06(browser):
    context, page = await new_page(browser, 6)
    await page.goto(f"{APP_URL}/actions", wait_until="networkidle", timeout=60_000)
    await page.get_by_text("Action Plan", exact=False).wait_for(state="visible", timeout=30_000)
    await page.wait_for_timeout(1700)
    livelihood = page.locator("button[role='combobox']").nth(1)
    for name in ("Farmer", "Pastoralist", "Displaced / camp"):
        await livelihood.click(); await page.get_by_role("option", name=name, exact=True).click(); await page.wait_for_timeout(2300)
    await finish(context, page, 6)


async def beat_07(browser):
    context, page = await new_page(browser, 7)
    await page.goto(f"{APP_URL}/report", wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(1200)
    textarea = page.locator("#description").first; box = await textarea.bounding_box()
    await smooth_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); await textarea.click()
    await page.keyboard.type("Water levels rising fast near the main road bridge", delay=35)
    submit = page.get_by_role("button", name="Submit Report"); box = await submit.bounding_box()
    await smooth_move(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2); await submit.click()
    await page.get_by_text("Report received. Thank you.").wait_for(state="visible", timeout=20_000)
    await page.wait_for_timeout(1300); await page.goto(f"{APP_URL}/map", wait_until="networkidle", timeout=60_000)
    await page.locator('[aria-label*="early warning map"]').wait_for(state="visible", timeout=30_000); await page.wait_for_timeout(5000)
    hotspot = page.locator(".hali-hotspot-icon").first; await hotspot.wait_for(state="attached", timeout=20_000); await hotspot.dispatch_event("click")
    await page.get_by_text("No official alert issued.").wait_for(state="visible", timeout=10_000); await page.wait_for_timeout(2500)
    await finish(context, page, 7)


BEATS = {1: beat_01, 2: beat_02, 3: beat_03, 4: beat_04, 5: beat_05, 6: beat_06, 7: beat_07}


async def main():
    requested = sys.argv[1] if len(sys.argv) > 1 else "all"
    async with async_playwright() as playwright:
        # Headed Chrome is available with HALI_HEADED=1, but its physical
        # surface is smaller than the requested viewport on some CI/Xvfb
        # hosts. The default uses a real 1920x1080 browser-rendered surface;
        # the injected cursor still makes mouse intent visible in the video.
        browser = await playwright.chromium.launch(
            headless=os.getenv("HALI_HEADED") != "1",
            executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-gpu", "--window-size=1920,1080", "--start-maximized"],
        )
        numbers = list(BEATS) if requested == "all" else [int(requested)]
        for number in numbers:
            print(f"Recording beat {number:02d}..."); await BEATS[number](browser)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
