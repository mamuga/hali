-- Recomputes alerts.affected_countries against the real boundaries from 006.
--
-- Existing rows were attributed while countries.geom held bounding boxes, which
-- overlapped heavily. The single active alert at the time of this migration was
-- stored as {ET,ER,SD,SS} but genuinely intersects only {ET,SD} — so subscribers
-- in Eritrea and South Sudan would have been messaged about a flood that does
-- not reach them.
--
-- This matters beyond tidiness: broadcast targeting matches subscribers on
-- preferred_iso2 = ANY(affected_countries), so a stale attribution sends real
-- SMS to the wrong country.
--
-- Alerts whose geometry intersects no IGAD state keep their existing value
-- rather than being blanked, since that is more likely a coverage gap than a
-- genuine "affects nobody".
UPDATE alerts a
SET affected_countries = COALESCE(
    (SELECT array_agg(c.iso2 ORDER BY c.iso2)
     FROM countries c
     WHERE ST_Intersects(a.geom, c.geom)),
    a.affected_countries
);
