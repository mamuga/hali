import L from 'leaflet';
import '@geoman-io/leaflet-geoman-free';
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css';

/**
 * Area-of-interest drawing.
 *
 * Imported lazily by HaliMap: geoman plus its stylesheet is ~140 KB, and the
 * map is fully usable without ever drawing anything.
 */

/** Only shapes that enclose an area — the backend rejects lines and points. */
export const DRAW_CONTROLS = {
  position: 'topleft',
  drawPolygon: true,
  drawRectangle: true,
  drawMarker: false,
  drawCircle: false,
  drawPolyline: false,
  drawText: false,
  drawCircleMarker: false,
  editMode: true,
  dragMode: true,
  removalMode: true,
  rotateMode: false,
  cutPolygon: false,
} as const;

export const AOI_STYLE: L.PathOptions = {
  color: '#0ea5e9',
  weight: 2,
  dashArray: '6 4',
  fillColor: '#0ea5e9',
  fillOpacity: 0.08,
};

/** Minimal shape of the geoman map API we actually call. */
interface PmApi {
  addControls: (options: unknown) => void;
  setGlobalOptions: (options: unknown) => void;
}

export function enableDrawControls(map: L.Map): void {
  // Geoman registers itself through L.Map.addInitHook, which only runs for maps
  // constructed *after* the plugin is loaded. Because this module is imported
  // lazily the map already exists, so `map.pm` is undefined and every call on
  // it throws. Attaching the same instance the init hook would have created
  // fixes that without giving up the lazy chunk.
  const holder = map as unknown as { pm?: PmApi };

  if (!holder.pm) {
    const PM = (L as unknown as { PM?: { Map: new (m: L.Map) => PmApi } }).PM;
    if (!PM?.Map) throw new Error('leaflet-geoman loaded but L.PM.Map is unavailable');
    holder.pm = new PM.Map(map);
  }

  holder.pm.addControls(DRAW_CONTROLS);
  // pathOptions styles the shape while it is being drawn as well as after,
  // so the outline does not jump from geoman's default green to ours on finish.
  holder.pm.setGlobalOptions({ pathOptions: AOI_STYLE, snappable: false });
}
