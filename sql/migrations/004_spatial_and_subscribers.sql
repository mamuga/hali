-- Phase 0 schema for the spatial analysis layer (spec §4) and the subscriber /
-- broadcast layer (spec §5, §7). Safe to re-run: every statement is guarded.

-- ── Spec §4.4 — WorldPop population exposure, cached per alert ────────────────
-- Deviates from the spec's `INTEGER DEFAULT 0`: left nullable so "WorldPop has
-- not answered yet / the call failed" stays distinguishable from "zero people
-- in this zone". Rendering "~0 people affected" for an unknown would be a
-- materially misleading thing for a humanitarian alert to say, so the UI omits
-- the line on NULL instead.
ALTER TABLE alerts
  ADD COLUMN IF NOT EXISTS population_exposed INTEGER;

-- ── Spec §6.3 — which channel a community report arrived on ───────────────────
ALTER TABLE community_reports
  ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'pwa';

DO $$
BEGIN
  ALTER TABLE community_reports
    ADD CONSTRAINT community_reports_channel_check
    CHECK (channel IN ('pwa', 'ussd', 'whatsapp'));
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- ── Spec §4.5 — DBSCAN-detected emerging hotspots ─────────────────────────────
-- Rewritten wholesale by each detection run; no FK to community_reports so a
-- report deletion can never orphan or block a refresh.
CREATE TABLE IF NOT EXISTS emerging_hotspots (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  location geometry(Point, 4326) NOT NULL,
  report_count INTEGER NOT NULL CHECK (report_count > 0),
  dominant_hazard TEXT NOT NULL CHECK (dominant_hazard IN ('flood', 'drought', 'locust', 'cyclone', 'health', 'other')),
  confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  first_reported TIMESTAMPTZ NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Spec §7.1 — SMS / WhatsApp subscribers ────────────────────────────────────
-- convo_state / convo_data back the WhatsApp opt-in state machine (spec §5.2).
-- Keeping conversation state on this row avoids introducing Redis for what is
-- ultimately a write to this same table.
CREATE TABLE IF NOT EXISTS user_subscriptions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  phone_number TEXT NOT NULL UNIQUE,
  channel TEXT NOT NULL DEFAULT 'sms' CHECK (channel IN ('sms', 'whatsapp', 'both')),
  language TEXT NOT NULL DEFAULT 'sw' CHECK (language IN ('sw', 'so', 'am', 'om', 'ar', 'en')),
  livelihood TEXT NOT NULL DEFAULT 'farmer' CHECK (livelihood IN ('farmer', 'pastoralist', 'fisherfolk', 'urban')),
  location geometry(Point, 4326),
  -- Deliberately not a FK to countries(iso2): opt-in is the critical USSD path
  -- and must not fail because the countries seed is missing or stale.
  preferred_iso2 CHAR(2),
  opted_in BOOLEAN NOT NULL DEFAULT TRUE,
  opted_in_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  opted_in_via TEXT CHECK (opted_in_via IN ('ussd', 'whatsapp', 'pwa')),
  min_severity TEXT NOT NULL DEFAULT 'orange' CHECK (min_severity IN ('green', 'orange', 'red')),
  last_active TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  convo_state TEXT,
  convo_data JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS emerging_hotspots_geom_idx ON emerging_hotspots USING GIST (location);
CREATE INDEX IF NOT EXISTS user_subscriptions_loc_idx ON user_subscriptions USING GIST (location);
-- Broadcast fan-out always filters on opted_in first; partial index keeps it small.
CREATE INDEX IF NOT EXISTS user_subscriptions_optin_idx ON user_subscriptions (opted_in) WHERE opted_in;
CREATE INDEX IF NOT EXISTS user_subscriptions_iso2_idx ON user_subscriptions (preferred_iso2);
