CREATE TABLE IF NOT EXISTS raw_ingestion (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source TEXT NOT NULL DEFAULT 'manual',
  external_id TEXT,
  payload JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processed', 'failed')),
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS alerts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  raw_ingestion_id UUID REFERENCES raw_ingestion(id) ON DELETE SET NULL,
  hazard_type TEXT NOT NULL CHECK (hazard_type IN ('flood', 'drought', 'locust', 'cyclone', 'health', 'other')),
  severity TEXT NOT NULL CHECK (severity IN ('green', 'orange', 'red')),
  affected_countries TEXT[] NOT NULL DEFAULT '{}',
  geom geometry(MultiPolygon, 4326) NOT NULL,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  dedup_hash TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL DEFAULT 'manual',
  source_url TEXT,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_translations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  language TEXT NOT NULL CHECK (language IN ('sw', 'so', 'am', 'om', 'ar', 'en')),
  headline TEXT NOT NULL,
  body TEXT NOT NULL,
  audio_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (alert_id, language)
);

CREATE TABLE IF NOT EXISTS action_cards (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  livelihood TEXT NOT NULL CHECK (livelihood IN ('farmer', 'pastoralist', 'fisherfolk', 'urban')),
  language TEXT NOT NULL CHECK (language IN ('sw', 'so', 'am', 'om', 'ar', 'en')),
  steps TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (alert_id, livelihood, language)
);

CREATE TABLE IF NOT EXISTS community_reports (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  hazard_type TEXT NOT NULL CHECK (hazard_type IN ('flood', 'drought', 'locust', 'cyclone', 'health', 'other')),
  description TEXT NOT NULL CHECK (length(description) BETWEEN 3 AND 1000),
  location geometry(Point, 4326) NOT NULL,
  labels TEXT[] NOT NULL DEFAULT '{}',
  phone_number TEXT,
  reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS countries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  iso2 CHAR(2) NOT NULL UNIQUE,
  name TEXT NOT NULL UNIQUE,
  geom geometry(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS alerts_geom_idx ON alerts USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_alerts_valid_to ON alerts (valid_to);
CREATE INDEX IF NOT EXISTS idx_alerts_hazard_severity ON alerts (hazard_type, severity);
CREATE INDEX IF NOT EXISTS community_reports_geom_idx ON community_reports USING GIST (location);
CREATE INDEX IF NOT EXISTS idx_reports_reported_at ON community_reports (reported_at);
CREATE INDEX IF NOT EXISTS countries_geom_idx ON countries USING GIST (geom);
