-- Widen user_subscriptions to the vocabularies the opt-in menus actually offer.
--
-- Migration 009 widened alerts, community_reports, alert_translations and
-- action_cards to 10 languages and 7 livelihoods, but missed
-- user_subscriptions. The USSD and WhatsApp opt-in flows were expanded to the
-- full lists in the same change, so since then the menus have been offering
-- choices the table rejects.
--
-- Verified against the live database on 2026-07-29:
--   INSERT ... VALUES ('+2547...', 'sms', 'ti', 'trader', 'ussd')
--   ERROR: violates check constraint "user_subscriptions_language_check"
--
-- A user pressing "8" for Tigrinya or "6" for Trader had their subscription
-- fail. This is the failure mode most likely to hit a real person during the
-- demo, and the least visible: the alert pipeline is unaffected, only the
-- person trying to sign up is.

ALTER TABLE user_subscriptions
  DROP CONSTRAINT IF EXISTS user_subscriptions_language_check;
ALTER TABLE user_subscriptions
  ADD CONSTRAINT user_subscriptions_language_check
  CHECK (language IN ('sw', 'so', 'am', 'om', 'ar', 'en', 'fr', 'ti', 'lg', 'aa'));

ALTER TABLE user_subscriptions
  DROP CONSTRAINT IF EXISTS user_subscriptions_livelihood_check;
ALTER TABLE user_subscriptions
  ADD CONSTRAINT user_subscriptions_livelihood_check
  CHECK (livelihood IN ('farmer', 'pastoralist', 'agropastoralist', 'fisherfolk',
                        'urban', 'trader', 'displaced'));
