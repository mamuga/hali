/**
 * Build-time configuration. Astro frontmatter runs in Node during `astro build`,
 * so plain process.env works and the values are inlined into the static HTML.
 *
 * Set on Railway:
 *   VITE_APP_URL         — the deployed HALI PWA
 *   VITE_GITHUB_URL      — the repository
 *   VITE_DEMO_VIDEO_URL  — embed URL. Unset means the demo section is omitted.
 */
const env = process.env;

export const APP_URL =
  env.VITE_APP_URL || 'https://frontend-production-ba31.up.railway.app';

export const GITHUB_URL = env.VITE_GITHUB_URL || 'https://github.com/mamuga/hali';

/** Empty means "no video yet" — the section is not rendered at all. */
export const DEMO_VIDEO_URL = (env.VITE_DEMO_VIDEO_URL || '').trim();

/** Africa's Talking USSD service code (apps/backend/tests/test_ussd.py). */
export const USSD_CODE = env.VITE_USSD_CODE || '*789#';

/** WhatsApp Cloud API number. Empty means the chip is not rendered. */
export const WHATSAPP_NUMBER = (env.VITE_WHATSAPP_NUMBER || '').trim();
export const WHATSAPP_URL = WHATSAPP_NUMBER
  ? `https://wa.me/${WHATSAPP_NUMBER.replace(/[^0-9]/g, '')}?text=${encodeURIComponent('HALI')}`
  : '';
