import L from 'leaflet';

/**
 * ICPAC GeoPortal WMS overlays.
 *
 * The layer names below were verified against the live GetCapabilities document
 * at geoportal.icpac.net and each was confirmed to return a real PNG tile. The
 * names in the original spec (geonode:rainfall_anomaly, geonode:flood_risk,
 * geonode:spi_3month, geonode:ea_hazard_zones) do not exist on that server — all
 * four 404 — so these are the closest genuine equivalents from ICPAC's own
 * catalogue.
 */
export const ICPAC_WMS_URL = 'https://geoportal.icpac.net/geoserver/wms';

export interface IcpacLayerDef {
  /** Label shown in the layer switcher. */
  label: string;
  /** GeoServer layer name, without the geonode: prefix. */
  name: string;
  opacity: number;
  /** Which HALI hazard this corroborates, for the caption. */
  hazard: string;
}

export const ICPAC_LAYERS: IcpacLayerDef[] = [
  { label: 'Flood prone areas', name: 'flood_prone_areas', opacity: 0.65, hazard: 'flood' },
  { label: 'Drought prone areas', name: 'drought_prone_areas', opacity: 0.6, hazard: 'drought' },
  { label: 'Drought hazard index', name: 'Drought_Hazard_Index', opacity: 0.6, hazard: 'drought' },
  { label: 'Desert locust hazard', name: 'desert_locust_hazard', opacity: 0.6, hazard: 'locust' },
  {
    label: 'Multi-hazard risk index',
    name: 'estimated_risk_index_for_multiple_hazards',
    opacity: 0.55,
    hazard: 'multiple',
  },
];

export function createIcpacLayer(def: IcpacLayerDef): L.TileLayer.WMS {
  return L.tileLayer.wms(ICPAC_WMS_URL, {
    layers: `geonode:${def.name}`,
    format: 'image/png',
    transparent: true,
    opacity: def.opacity,
    version: '1.1.1',
    attribution: '© <a href="https://geoportal.icpac.net">ICPAC GeoPortal</a>',
  });
}

export function createIcpacLayers(): Record<string, L.TileLayer.WMS> {
  return Object.fromEntries(ICPAC_LAYERS.map((def) => [def.label, createIcpacLayer(def)]));
}
