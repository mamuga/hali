-- Widen the closed vocabularies: 10 languages, 7 livelihoods, 10 hazards.
--
-- These columns are TEXT but every one carries a CHECK constraint pinning the
-- original six-value sets. Adding a language or hazard in application code
-- without this migration raises CheckViolationError on the first insert, so
-- this must land before any of the Phase 2 code.
--
-- Constraint names were read from pg_constraint rather than assumed; they are
-- the PostgreSQL defaults. DROP ... IF EXISTS keeps the migration replayable.

-- ── Languages: + fr, ti, lg, aa ──────────────────────────────────────────────
-- fr: Djibouti's official language, and ICPAC's own site offers it.
-- ti: Tigrinya, Eritrea and northern Ethiopia (~9M speakers).
-- lg: Luganda, Uganda's largest local language.
-- aa: Afar, Djibouti and the Afar region of Ethiopia — a drought epicentre.

ALTER TABLE alert_translations
  DROP CONSTRAINT IF EXISTS alert_translations_language_check;
ALTER TABLE alert_translations
  ADD CONSTRAINT alert_translations_language_check
  CHECK (language IN ('sw', 'so', 'am', 'om', 'ar', 'en', 'fr', 'ti', 'lg', 'aa'));

ALTER TABLE action_cards
  DROP CONSTRAINT IF EXISTS action_cards_language_check;
ALTER TABLE action_cards
  ADD CONSTRAINT action_cards_language_check
  CHECK (language IN ('sw', 'so', 'am', 'om', 'ar', 'en', 'fr', 'ti', 'lg', 'aa'));

-- LLM quality for ti/lg/aa is materially weaker than for the others. When a
-- translation scores below the clarity floor we store the English text instead
-- and record that here, so the UI can say so rather than presenting a bad
-- translation as authoritative. NULL means "genuinely in the requested language".
ALTER TABLE alert_translations
  ADD COLUMN IF NOT EXISTS fallback_language TEXT;

ALTER TABLE alert_translations
  DROP CONSTRAINT IF EXISTS alert_translations_fallback_language_check;
ALTER TABLE alert_translations
  ADD CONSTRAINT alert_translations_fallback_language_check
  CHECK (fallback_language IS NULL
         OR fallback_language IN ('sw', 'so', 'am', 'om', 'ar', 'en', 'fr', 'ti', 'lg', 'aa'));

-- ── Livelihoods: + agropastoralist, trader, displaced ────────────────────────
-- agropastoralist: the dominant livelihood across the IGAD borderlands, and its
--   advice genuinely differs from both farmer and pastoralist.
-- trader: market vendors and transporters — road and market closures hit first.
-- displaced: 4M+ people in the region; camp guidance assumes no land, no
--   livestock, aid dependence, and restricted movement.

ALTER TABLE action_cards
  DROP CONSTRAINT IF EXISTS action_cards_livelihood_check;
ALTER TABLE action_cards
  ADD CONSTRAINT action_cards_livelihood_check
  CHECK (livelihood IN ('farmer', 'pastoralist', 'agropastoralist', 'fisherfolk',
                        'urban', 'trader', 'displaced'));

-- ── Hazards: + heatwave, landslide, wildfire, epidemic ───────────────────────
-- heatwave: a killer in Djibouti and Sudan.
-- landslide: Mt Elgon and the Ethiopian highlands — recurring mass-casualty.
-- wildfire: GDACS emits WF, which we were collapsing into 'other'.
-- epidemic: post-flood cholera; 'health' stays for general health advisories.

ALTER TABLE alerts
  DROP CONSTRAINT IF EXISTS alerts_hazard_type_check;
ALTER TABLE alerts
  ADD CONSTRAINT alerts_hazard_type_check
  CHECK (hazard_type IN ('flood', 'drought', 'locust', 'cyclone', 'heatwave',
                         'landslide', 'wildfire', 'epidemic', 'health', 'other'));

ALTER TABLE community_reports
  DROP CONSTRAINT IF EXISTS community_reports_hazard_type_check;
ALTER TABLE community_reports
  ADD CONSTRAINT community_reports_hazard_type_check
  CHECK (hazard_type IN ('flood', 'drought', 'locust', 'cyclone', 'heatwave',
                         'landslide', 'wildfire', 'epidemic', 'health', 'other'));
