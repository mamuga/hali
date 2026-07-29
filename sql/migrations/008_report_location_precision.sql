-- Distinguish GPS-accurate reports from country-level ones.
--
-- USSD and WhatsApp carry no coordinates, so those channels store the
-- reporter's country interior point. That point is a real location, which
-- means DBSCAN happily clusters N reports from one country into a "hotspot"
-- sitting in the middle of nowhere, and the heatmap burns a blob there. Both
-- are artefacts of the channel, not of anything happening on the ground.
--
-- Marking precision lets the spatial layer use only GPS reports while the raw
-- reports stay queryable for counts, classification, and severity escalation.

ALTER TABLE community_reports
  ADD COLUMN IF NOT EXISTS location_precision TEXT NOT NULL DEFAULT 'gps';

ALTER TABLE community_reports
  DROP CONSTRAINT IF EXISTS community_reports_location_precision_check;

ALTER TABLE community_reports
  ADD CONSTRAINT community_reports_location_precision_check
  CHECK (location_precision IN ('gps', 'country'));

-- Existing rows predate the column. Anything that arrived on a channel without
-- GPS was stored at a country interior point, so label it accordingly.
UPDATE community_reports
   SET location_precision = 'country'
 WHERE channel IN ('ussd', 'sms', 'whatsapp')
   AND location_precision = 'gps';

-- DBSCAN reads "recent GPS reports" on every detection run.
CREATE INDEX IF NOT EXISTS community_reports_gps_recent_idx
  ON community_reports (reported_at)
  WHERE location_precision = 'gps';
