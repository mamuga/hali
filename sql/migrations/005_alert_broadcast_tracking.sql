-- Tracks which alerts have already been broadcast to subscribers.
--
-- Without this, any re-run of the AI backlog would re-send SMS for alerts that
-- subscribers already received. SMS costs money and duplicate emergency alerts
-- erode trust in the channel, so the send is claimed exactly once.
ALTER TABLE alerts
  ADD COLUMN IF NOT EXISTS broadcast_at TIMESTAMPTZ;

-- Alerts that already existed before broadcasting was implemented were never
-- sent, but they are historical - backfilling them as "already broadcast"
-- prevents a mass send to every subscriber on the first deploy of this feature.
UPDATE alerts
SET broadcast_at = COALESCE(processed_at, created_at)
WHERE broadcast_at IS NULL;

CREATE INDEX IF NOT EXISTS alerts_broadcast_pending_idx
  ON alerts (severity) WHERE broadcast_at IS NULL;
