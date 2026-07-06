-- Hackathon seed boundaries use simple bounding boxes. Replace with Natural Earth data via:
-- ogr2ogr -f PostgreSQL PG:"$MIGRATION_DATABASE_URL" ne_10m_admin_0_countries.shp -nln countries_import -t_srs EPSG:4326
-- Then transform/merge real country geometries into countries.geom as MultiPolygon records.
INSERT INTO countries (iso2, name, geom) VALUES
('KE','Kenya', ST_Multi(ST_MakeEnvelope(33.5, -4.9, 41.9, 5.2, 4326))),
('ET','Ethiopia', ST_Multi(ST_MakeEnvelope(32.9, 3.4, 48.1, 14.9, 4326))),
('SO','Somalia', ST_Multi(ST_MakeEnvelope(40.9, -1.8, 51.5, 12.2, 4326))),
('UG','Uganda', ST_Multi(ST_MakeEnvelope(29.5, -1.6, 35.1, 4.3, 4326))),
('DJ','Djibouti', ST_Multi(ST_MakeEnvelope(41.7, 10.9, 43.4, 12.8, 4326))),
('ER','Eritrea', ST_Multi(ST_MakeEnvelope(36.4, 12.3, 43.1, 18.1, 4326))),
('SD','Sudan', ST_Multi(ST_MakeEnvelope(21.8, 8.6, 38.6, 22.2, 4326))),
('SS','South Sudan', ST_Multi(ST_MakeEnvelope(24.1, 3.4, 35.9, 12.3, 4326)))
ON CONFLICT (iso2) DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom;
