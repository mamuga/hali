import L from 'leaflet';
import type { CountriesGeoJSON } from '@hali/types';

/**
 * The IGAD region: Djibouti, Eritrea, Ethiopia, Kenya, Somalia, South Sudan,
 * Sudan, Uganda. HALI only issues alerts here, so the map should not invite
 * panning to Brazil.
 */
export const IGAD_BOUNDS = L.latLngBounds([-5, 20], [25, 52]);

/** Room to drag past the edge without the viewport snapping back mid-gesture. */
export const IGAD_BOUNDS_PADDING = 0.15;

/**
 * Starting floor, raised at runtime to whatever zoom actually fits IGAD in the
 * current viewport (see HaliMap's clampToRegion). Below this the whole
 * continent fits, which defeats the point of the lock.
 */
export const IGAD_MIN_ZOOM = 4;

/** Outer ring covering the whole world, in Leaflet [lat, lng] order. */
const WORLD_RING: L.LatLngTuple[] = [
  [-90, -180],
  [-90, 180],
  [90, 180],
  [90, -180],
];

type Ring = L.LatLngTuple[];

/**
 * Build the polygon rings for the "everything outside IGAD is dimmed" mask.
 *
 * Returns the world ring followed by one ring per country landmass. Leaflet
 * renders polygons with `fill-rule: evenodd`, so every enclosed sub-region
 * becomes a hole regardless of winding order — the countries are punched out of
 * the dark overlay and the map beneath shows through.
 *
 * Only each polygon's exterior ring is used. Interior rings (lakes) would
 * otherwise be re-dimmed, and a dark Lake Victoria reads as a rendering bug.
 */
export function igadMaskRings(countries: CountriesGeoJSON): Ring[] {
  const holes: Ring[] = [];

  for (const feature of countries.features) {
    const geometry = feature.geometry;
    const polygons =
      geometry.type === 'MultiPolygon'
        ? geometry.coordinates
        : [(geometry as GeoJSON.Polygon).coordinates];

    for (const polygon of polygons) {
      const exterior = polygon[0];
      if (!exterior || exterior.length < 4) continue; // not a closed ring
      holes.push(exterior.map(([lng, lat]) => [lat, lng] as L.LatLngTuple));
    }
  }

  return [WORLD_RING, ...holes];
}

export const MASK_STYLE: L.PolylineOptions = {
  stroke: false,
  fillColor: '#0b1220',
  fillOpacity: 0.55,
  // Must not intercept clicks: the mask covers the entire world, so an
  // interactive one would block click-to-analyse everywhere.
  interactive: false,
};

/**
 * Outlines only — no fill.
 *
 * The original seeded boundaries were filled bounding boxes, which painted
 * opaque rectangles over every ICPAC overlay and the choropleth beneath. Real
 * geometry alone does not fix that; the fill has to go too.
 */
export const BOUNDARY_STYLE: L.PathOptions = {
  fill: false,
  color: '#38bdf8',
  weight: 1.5,
  opacity: 0.9,
  interactive: false,
};
