-- Keep the emerging-hotspot table in sync with the community report domain.
-- New report hazard types were added in migration 009, but the original
-- hotspot constraint still rejected them during DBSCAN persistence.
ALTER TABLE emerging_hotspots
  DROP CONSTRAINT IF EXISTS emerging_hotspots_dominant_hazard_check;

ALTER TABLE emerging_hotspots
  ADD CONSTRAINT emerging_hotspots_dominant_hazard_check
  CHECK (dominant_hazard IN (
    'flood', 'drought', 'locust', 'cyclone', 'health', 'heatwave',
    'landslide', 'wildfire', 'epidemic', 'other'
  ));
