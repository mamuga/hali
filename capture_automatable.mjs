import fs from 'node:fs';
import { chromium } from 'playwright-core';

const out = '/home/muga/hali/screenshots';
const app = 'https://frontend-production-ba31.up.railway.app';
const landing = 'https://landing-production-d6be4.up.railway.app/about';

const browser = await chromium.launch({
  executablePath: '/usr/bin/google-chrome',
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
});
const context = await browser.newContext({
  viewport: { width: 1280, height: 853 },
  geolocation: { latitude: 11.603, longitude: 42.704 },
  permissions: ['geolocation'],
});
const page = await context.newPage();

async function shot(name) {
  await page.screenshot({ path: `${out}/${name}.png` });
}

async function mapReady() {
  await page.goto(`${app}/map`, { waitUntil: 'networkidle', timeout: 60_000 });
  await page.locator('[aria-label*="early warning map"]').waitFor({ state: 'visible', timeout: 30_000 });
  await page.getByText(/Most at risk now/i).waitFor({ state: 'visible', timeout: 30_000 });
  await page.waitForTimeout(2500);
}

// 01 — district-level / compound-risk choropleth.
await mapReady();
await shot('01-district-choropleth');

// 02 — isolate the FEWS NET / IPC district polygons.
await page.getByText('Alert zones', { exact: true }).click();
await page.waitForTimeout(800);
await shot('02-ipc-food-insecurity');

// 03 — alert zones composited with a live ICPAC WMS overlay.
await page.getByText('Alert zones', { exact: true }).click();
await page.getByText('Flood prone areas', { exact: true }).click();
await page.waitForTimeout(6000);
await shot('03-alert-zones-icpac-wms');

// 04 — risk ranking is visible in the default map state.
await page.getByText('Flood prone areas', { exact: true }).click();
await page.waitForTimeout(700);
await shot('04-compound-risk-choropleth');

// 05 — click the actual DBSCAN-generated emerging hotspot marker.
const hotspot = page.locator('.hali-hotspot-icon').first();
await hotspot.waitFor({ state: 'attached', timeout: 20_000 });
// Leaflet intentionally gives the pulsing icon a zero-size box and paints the
// visible dot with CSS. Dispatch directly on the real marker element.
await page.evaluate(() => {
  const marker = document.querySelector('.hali-hotspot-icon');
  if (!marker) throw new Error('emerging hotspot marker not found');
  marker.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
});
await page.getByText('No official alert issued.').waitFor({ state: 'visible', timeout: 10_000 });
await shot('05-emerging-hotspot-popup');

// 06 — draw an AOI over eastern Ethiopia / Djibouti where live alerts,
// reports and the population grid overlap.
await page.getByLabel('Close popup').click().catch(() => {});
const polygonTool = page.locator('.leaflet-pm-icon-polygon').first();
await polygonTool.waitFor({ state: 'visible', timeout: 15_000 });
await polygonTool.click();
const mapBox = await page.locator('[aria-label*="early warning map"]').boundingBox();
if (!mapBox) throw new Error('map bounds unavailable');
const points = [
  [mapBox.x + 575, mapBox.y + 185],
  [mapBox.x + 865, mapBox.y + 185],
  [mapBox.x + 865, mapBox.y + 475],
  [mapBox.x + 575, mapBox.y + 475],
  [mapBox.x + 575, mapBox.y + 185],
];
for (const [x, y] of points) await page.mouse.click(x, y);
await page.waitForTimeout(1200);
await page.mouse.click(points[0][0], points[0][1]);
await page.getByLabel('Area of interest').waitFor({ state: 'visible', timeout: 30_000 });
await page.getByText(/selected/).waitFor({ state: 'visible', timeout: 30_000 });
await page.waitForTimeout(1200);
await shot('06-aoi-polygon-query');

// 07 — three livelihood variants for the same live alert.
await page.goto(`${app}/actions`, { waitUntil: 'networkidle', timeout: 60_000 });
await page.getByText('Action Plan').waitFor({ state: 'visible', timeout: 20_000 });
  await page.getByText(/Next 48 hours/i).waitFor({ state: 'visible', timeout: 20_000 });
await shot('07a-action-card-farmer');
const livelihood = page.locator('button[role="combobox"]').nth(1);
await livelihood.click();
  await page.getByRole('option', { name: 'Pastoralist', exact: true }).click();
  await page.getByText(/Next 48 hours/i).waitFor({ state: 'visible' });
await page.waitForTimeout(600);
await shot('07b-action-card-pastoralist');
await livelihood.click();
await page.getByRole('option', { name: 'Displaced / camp' }).click();
await page.waitForTimeout(600);
await shot('07c-action-card-displaced');

// 08 — ten-language dropdown and a rendered Swahili alert.
const language = page.locator('button[role="combobox"]').nth(2);
await language.click();
await page.getByRole('option', { name: 'Kiswahili' }).waitFor({ state: 'visible' });
await shot('08a-language-dropdown-open');
await page.getByRole('option', { name: 'Kiswahili' }).click();
await page.waitForTimeout(1200);
await shot('08b-alert-in-swahili-or-amharic');

// 09 — mobile feed with dark preference explicitly enabled.
await context.setViewportSize({ width: 390, height: 844 });
await page.goto(`${app}/`, { waitUntil: 'networkidle', timeout: 60_000 });
await page.getByText('HALI').waitFor({ state: 'visible', timeout: 20_000 });
await page.getByLabel('Toggle dark mode').click();
await page.waitForTimeout(500);
await shot('09-alert-feed-mobile-dark');

// 13 — submit a real report through the live form and catch the Sonner toast.
await context.setViewportSize({ width: 1280, height: 853 });
await page.goto(`${app}/report`, { waitUntil: 'networkidle', timeout: 60_000 });
await page.locator('#description').fill('Residents report smoke and a fast-moving grass fire near the eastern ridge.');
await page.getByRole('button', { name: 'Submit Report' }).click();
await page.getByText('Report received. Thank you.').waitFor({ state: 'visible', timeout: 20_000 });
await shot('13-report-submit-toast');

// 14 — render the actual admin response as a clean image.
const stats = JSON.parse(fs.readFileSync('/tmp/ai_stats.json', 'utf8'));
const statsPage = await context.newPage();
await statsPage.setContent(`<!doctype html><html><head><style>
body{margin:0;background:#0b1220;color:#dbeafe;font:16px ui-monospace,SFMono-Regular,Menlo,monospace}
main{box-sizing:border-box;width:1280px;min-height:853px;padding:60px 90px}h1{font:700 28px system-ui;color:#67e8f9;margin:0 0 10px}p{font:14px system-ui;color:#94a3b8;margin:0 0 28px}pre{padding:28px;border:1px solid #334155;border-radius:14px;background:#111827;line-height:1.6;white-space:pre-wrap}
</style></head><body><main><h1>HALI AI ensemble statistics</h1><p>Live Railway admin endpoint · /api/admin/ai-stats</p><pre>${JSON.stringify(stats, null, 2)}</pre></main></body></html>`);
await statsPage.screenshot({ path: `${out}/14-admin-ai-stats.png` });

await statsPage.close();
await page.close();
await browser.close();
