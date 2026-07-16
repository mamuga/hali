import React, { useState, useEffect } from 'react';
import { MapContainer, GeoJSON, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// We import the exact, verified methods directly from the package
import { tileLayerOffline, savetiles } from 'leaflet.offline';

// 1. Alert severity styles from your partner's exact requirements
const severityStyle = (feature) => ({
  color: { red: '#E24B4A', orange: '#EF9F27', green: '#639922' }[feature.properties.severity],
  fillOpacity: 0.4,
  weight: 1.5
});

// 2. This sub-component safely hooks up the offline caching to the active map instance
function OfflineTileLayer() {
  const map = useMap();

  useEffect(() => {
    if (!map) return;

    // Create the offline tile layer
    const tileLayer = tileLayerOffline(
      'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        attribution: '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors',
        minZoom: 1,
        maxZoom: 18,
      }
    );

    // Add the tile layer to the map
    tileLayer.addTo(map);

    // Set up the save controls (Save / Delete buttons)
    const saveControl = savetiles(tileLayer, {
      zoomlevels: [5, 6, 7, 8], // Caches East Africa overview levels cleanly
      confirm(layer, successCallback) {
        if (window.confirm(`Save ${layer._tilesToSave.length} map tiles for offline use?`)) {
          successCallback();
        }
      },
      confirmDelete(layer, successCallback) {
        if (window.confirm('Delete saved tiles?')) {
          successCallback();
        }
      }
    });

    // Add the control buttons to the map UI
    saveControl.addTo(map);

    // CLEANUP: If React re-renders, this cleanly removes the layers so Leaflet never crashes
    return () => {
      map.removeLayer(tileLayer);
      map.removeControl(saveControl);
    };
  }, [map]);

  return null;
}

// 3. Main Map Component
export default function HaliMap() {
  const [alerts, setAlerts] = useState(null);

  useEffect(() => {
    fetch('/api/alerts/geojson?bbox=21,-12,52,24&lang=sw')
      .then((r) => r.json())
      .then(setAlerts)
      .catch((err) => console.error("Could not fetch alert data:", err));
  }, []);

  return (
    <MapContainer center={[2, 38]} zoom={5} style={{ height: '100vh', width: '100%' }}>
      {/* Renders our custom offline tile loader and download button */}
      <OfflineTileLayer />

      {alerts && (
        <GeoJSON
          data={alerts}
          style={severityStyle}
          onEachFeature={(feature, layer) => {
            layer.bindPopup(`
              <strong>${feature.properties.headline}</strong><br/>
              ${feature.properties.hazard_type} · ${feature.properties.severity}
            `);
          }}
        />
      )}
    </MapContainer>
  );
}