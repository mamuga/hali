"""Render one 1920x1080 title-card WebM with Playwright Chromium."""
import asyncio
import shutil
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def main() -> None:
    text, output = sys.argv[1], sys.argv[2]
    temp_dir = Path(output).parent / ".title-recording"
    temp_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True, executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(temp_dir), record_video_size={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.set_content(f"""<!doctype html><style>
          html,body {{ margin:0; width:1920px; height:1080px; background:#0e1824; }}
          body {{ display:flex; align-items:center; justify-content:center; color:#E2E8F0;
            font-family:Inter,DejaVu Sans,Arial,sans-serif; font-size:64px;
            animation:titleFade 1.8s linear forwards; }}
          @keyframes titleFade {{ 0% {{ opacity:0 }} 17% {{ opacity:1 }} 78% {{ opacity:1 }} 100% {{ opacity:0 }} }}
        </style><body>{text}</body>""")
        await page.wait_for_timeout(2_200)
        video = page.video
        await context.close()
        source = Path(await video.path())
        shutil.move(source, output)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
