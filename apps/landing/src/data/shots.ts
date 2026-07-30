/**
 * Screenshots used on this page. Every entry is marked "captured live" in
 * screenshots/MANIFEST.md, against the deployed Railway services on 2026-07-30.
 * Slot #10 (WhatsApp) needs a manual platform session and is not captured, so
 * it is absent here. Slot #12 is a designed diagram, not a screenshot, and its
 * caption says so.
 *
 * Imported through astro:assets so each one is emitted as responsive webp
 * rather than a full-resolution PNG.
 */
import districtChoropleth from '../assets/screenshots/01-district-choropleth.png';
import ipcFoodInsecurity from '../assets/screenshots/02-ipc-food-insecurity.png';
import icpacWms from '../assets/screenshots/03-alert-zones-icpac-wms.png';
import compoundRisk from '../assets/screenshots/04-compound-risk-choropleth.png';
import emergingHotspot from '../assets/screenshots/05-emerging-hotspot-popup.png';
import aoiPolygon from '../assets/screenshots/06-aoi-polygon-query.png';
import actionCards from '../assets/screenshots/07-action-card-comparison.png';
import languageDropdown from '../assets/screenshots/08a-language-dropdown-open.png';
import alertSwahili from '../assets/screenshots/08b-alert-in-swahili-or-amharic.png';
import alertFeedMobile from '../assets/screenshots/09-alert-feed-mobile-dark.png';
import ussdMenu from '../assets/screenshots/11a-ussd-main-menu.png';
import ussdLivelihood from '../assets/screenshots/11b-ussd-alert-livelihood-menu.png';
import architecture from '../assets/screenshots/12-architecture-diagram.png';
import reportToast from '../assets/screenshots/13-report-submit-toast.png';
import adminAiStats from '../assets/screenshots/14-admin-ai-stats.png';

export {
  districtChoropleth,
  ipcFoodInsecurity,
  icpacWms,
  compoundRisk,
  emergingHotspot,
  aoiPolygon,
  actionCards,
  languageDropdown,
  alertSwahili,
  alertFeedMobile,
  ussdMenu,
  ussdLivelihood,
  architecture,
  reportToast,
  adminAiStats,
};
