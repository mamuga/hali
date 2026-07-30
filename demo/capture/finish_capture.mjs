import fs from 'node:fs';
import { chromium } from 'playwright-core';

const out = '/home/muga/hali/screenshots';
const app = 'https://frontend-production-ba31.up.railway.app';
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const context = await browser.newContext({ viewport: { width: 1280, height: 853 }, geolocation: { latitude: 11.603, longitude: 42.704 }, permissions: ['geolocation'] });
const page = await context.newPage();

console.log('language');
await page.goto(`${app}/actions`, { waitUntil: 'networkidle', timeout: 60_000 });
await page.getByText('Action Plan').waitFor({ state: 'visible', timeout: 20_000 });
const language = page.locator('button[role="combobox"]').nth(2);
await language.click();
await page.getByRole('option', { name: /Kiswahili/ }).waitFor({ state: 'visible', timeout: 10_000 });
await page.screenshot({ path: `${out}/08a-language-dropdown-open.png` });
await page.getByRole('option', { name: /Kiswahili/ }).click();
await page.waitForTimeout(1600);
await page.screenshot({ path: `${out}/08b-alert-in-swahili-or-amharic.png` });

console.log('report');
await page.goto(`${app}/report`, { waitUntil: 'networkidle', timeout: 60_000 });
await page.locator('#description').fill('Residents report smoke and a fast-moving grass fire near the eastern ridge.');
await page.getByRole('button', { name: 'Submit Report' }).click();
await page.getByText('Report received. Thank you.').waitFor({ state: 'visible', timeout: 20_000 });
await page.screenshot({ path: `${out}/13-report-submit-toast.png` });

console.log('admin');
const stats = JSON.parse(fs.readFileSync('/tmp/ai_stats.json', 'utf8'));
const statsPage = await context.newPage();
await statsPage.setContent(`<!doctype html><html><head><style>body{margin:0;background:#0b1220;color:#dbeafe;font:16px ui-monospace,SFMono-Regular,Menlo,monospace}main{box-sizing:border-box;width:1280px;min-height:853px;padding:60px 90px}h1{font:700 28px system-ui;color:#67e8f9;margin:0 0 10px}p{font:14px system-ui;color:#94a3b8;margin:0 0 28px}pre{padding:28px;border:1px solid #334155;border-radius:14px;background:#111827;line-height:1.6;white-space:pre-wrap}</style></head><body><main><h1>HALI AI ensemble statistics</h1><p>Live Railway admin endpoint · /api/admin/ai-stats</p><pre>${JSON.stringify(stats, null, 2)}</pre></main></body></html>`);
await statsPage.screenshot({ path: `${out}/14-admin-ai-stats.png` });
await browser.close();
console.log('done');
