"""
HALI AI Processor - orchestrates the full AI pipeline per alert.

For each alert:
  1. Enrich context (season, dominant livelihood)
  2. Run ensemble translation into all supported languages
  3. Generate livelihood-specific action cards
  4. Assess severity upgrade signals from community ground-truth reports
  5. Classify community reports (background, per-report)

Alerts are considered "AI-processed" once they have a translation stored
(there is no dedicated processed-by-AI column on `alerts`), so the backlog
scan looks for alerts missing a translation row rather than a status flag.
"""
from __future__ import annotations

import asyncio
import json
import time
from uuid import UUID

import asyncpg
import structlog

from hali.config import settings
from hali.services.broadcast import broadcast_alert

from .context import get_dominant_livelihood, get_season
from .models import (
    ActionCard,
    AlertUpgradeSignal,
    ProcessingResult,
    TranslationOutput,
)
from .prompts import (
    LOW_RESOURCE_LANGUAGES,
    VALID_REPORT_LABELS,
    action_card_system_prompt,
    action_card_user_prompt,
    report_label_system_prompt,
    report_label_user_prompt,
    severity_assessment_system_prompt,
    severity_assessment_user_prompt,
    translation_system_prompt,
    translation_user_prompt,
)
from .router import AIRouter

logger = structlog.get_logger(__name__)

# Every language we can serve. Translations are pre-generated for all of them:
# an alert nobody can read is worthless, and the alert table stores no headline
# of its own, so 'en' is generated like any other — it is also the fallback
# target when a low-resource translation fails the clarity floor.
LANGUAGES = ["sw", "so", "am", "om", "ar", "en", "fr", "ti", "lg", "aa"]

# Every livelihood an action card can be requested for.
LIVELIHOODS = [
    "farmer",
    "pastoralist",
    "agropastoralist",
    "fisherfolk",
    "urban",
    "trader",
    "displaced",
]

# Action cards are the expensive axis: pre-generating the full matrix would be
# 7 livelihoods x 10 languages = 70 model calls per alert, which no free-tier
# quota survives. Pre-generate the combinations a first-time visitor is most
# likely to hit and serve the remaining 58 on demand — the endpoint already
# generates and caches a missing card on request.
PREGENERATED_CARD_LIVELIHOODS = ["farmer", "pastoralist", "fisherfolk", "urban"]
PREGENERATED_CARD_LANGUAGES = ["sw", "en", "fr"]

SEVERITY_RANK = {"green": 0, "orange": 1, "red": 2}

# Spec §3.6: community ground truth may only raise an official alert's severity
# when the model is reasonably sure. An upgrade now also triggers a real SMS
# broadcast, so the bar matters.
MIN_UPGRADE_CONFIDENCE = 0.6


def _parse_json_block(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


class AlertProcessor:
    """Processes one alert at a time through the full AI pipeline.

    Reuse one instance per pool - the AIRouter manages client connections.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self.router = AIRouter()

    async def process_alert(self, alert_id: UUID) -> ProcessingResult:
        """Full pipeline for one alert. Never raises - errors are captured
        in result.errors.
        """
        start = time.perf_counter()
        result = ProcessingResult(alert_id=alert_id)
        log = logger.bind(alert_id=str(alert_id))
        log.info("processor.start")

        try:
            alert = await self._fetch_alert(alert_id)
            if not alert:
                result.errors.append(f"Alert {alert_id} not found")
                return result
        except Exception as exc:
            result.errors.append(f"DB fetch failed: {exc}")
            return result

        season = get_season(alert.get("valid_from"))
        countries = list(alert.get("affected_countries") or [])
        dominant_livelihood = get_dominant_livelihood(countries)
        log.info("processor.context", season=season, dominant_livelihood=dominant_livelihood)

        valid_from_str = alert["valid_from"].strftime("%Y-%m-%d %H:%M UTC") if alert.get("valid_from") else "now"
        valid_to_str = alert["valid_to"].strftime("%Y-%m-%d %H:%M UTC") if alert.get("valid_to") else "72 hours from now"

        # Step 1: ensemble translations, all languages in parallel.
        translations = await asyncio.gather(
            *[
                self._translate_one(
                    alert_id=alert_id,
                    hazard_type=alert["hazard_type"],
                    severity=alert["severity"],
                    countries=countries,
                    valid_from=valid_from_str,
                    valid_to=valid_to_str,
                    language=lang,
                    season=season,
                    livelihood_hint=dominant_livelihood,
                )
                for lang in LANGUAGES
            ]
        )

        for t in translations:
            if t and not t.error:
                result.translations_completed += 1
                result.ensemble_winners[t.language] = t.provider
            elif t:
                result.errors.append(f"Translation {t.language} failed: {t.error}")

        log.info("processor.translations_done", completed=result.translations_completed, total=len(LANGUAGES))

        # Step 2: action cards, one per livelihood x language.
        # Bounded concurrency rather than fully sequential: 24 serial LLM calls
        # dominated per-alert latency. The semaphore keeps the burst inside
        # free-tier rate limits (Gemini allows 5 requests/minute).
        card_semaphore = asyncio.Semaphore(settings.ai_max_concurrent_alerts)

        async def build_card(livelihood: str, lang: str) -> None:
            async with card_semaphore:
                try:
                    card = await self._generate_action_card(
                        alert_id=alert_id,
                        hazard_type=alert["hazard_type"],
                        severity=alert["severity"],
                        countries=countries,
                        livelihood=livelihood,
                        season=season,
                        language=lang,
                    )
                    if card:
                        await self._store_action_card(card)
                        result.action_cards_completed += 1
                    else:
                        # Without this the pipeline reported errors=0 while
                        # producing zero action cards, so a total provider
                        # outage looked like a clean run.
                        result.errors.append(f"Action card {livelihood}/{lang}: no card generated")
                except Exception as exc:
                    result.errors.append(f"Action card {livelihood}/{lang}: {exc}")

        await asyncio.gather(
            *(
                build_card(lv, lang)
                for lv in PREGENERATED_CARD_LIVELIHOODS
                for lang in PREGENERATED_CARD_LANGUAGES
            )
        )

        log.info("processor.action_cards_done", completed=result.action_cards_completed)

        # Step 3: community report severity assessment (ground-truth upgrade).
        try:
            upgrade = await self._assess_severity_upgrade(
                alert_id=alert_id,
                current_severity=alert["severity"],
                hazard_type=alert["hazard_type"],
            )
            if upgrade and upgrade.should_upgrade:
                result.upgrade_signal = upgrade
                await self._apply_severity_upgrade(alert_id, upgrade)
                log.info(
                    "processor.severity_upgraded",
                    from_=alert["severity"],
                    to=upgrade.proposed_severity,
                    confidence=upgrade.confidence,
                )
                # Everything generated above states the old severity, and
                # _apply_severity_upgrade has just deleted it. Regenerate now,
                # before the broadcast below, so subscribers are not told "orange"
                # about an alert that is now red — or sent nothing at all.
                alert["severity"] = upgrade.proposed_severity
                await self._regenerate_content(
                    alert_id=alert_id,
                    alert=alert,
                    countries=countries,
                    season=season,
                    dominant_livelihood=dominant_livelihood,
                    valid_from=valid_from_str,
                    valid_to=valid_to_str,
                    result=result,
                    log=log,
                )
        except Exception as exc:
            result.errors.append(f"Severity assessment: {exc}")

        # Step 4: fan out to subscribers. Runs last so translations and action
        # cards already exist — subscribers must never receive an untranslated
        # alert. broadcast_alert itself skips green, expired, and already-sent
        # alerts, so re-running the backlog is safe.
        if settings.enable_broadcast:
            try:
                summary = await broadcast_alert(alert_id, self.pool)
                log.info("processor.broadcast", **{k: v for k, v in summary.items() if k != "alert_id"})
            except Exception as exc:
                result.errors.append(f"Broadcast: {exc}")

        result.total_duration_ms = (time.perf_counter() - start) * 1000
        log.info(
            "processor.complete",
            translations=result.translations_completed,
            action_cards=result.action_cards_completed,
            duration_ms=round(result.total_duration_ms, 1),
            errors=len(result.errors),
        )
        return result

    async def _translate_one(
        self,
        alert_id: UUID,
        hazard_type: str,
        severity: str,
        countries: list[str],
        valid_from: str,
        valid_to: str,
        language: str,
        season: str | None,
        livelihood_hint: str | None,
    ) -> TranslationOutput | None:
        try:
            system = translation_system_prompt()
            user = translation_user_prompt(
                hazard_type=hazard_type,
                severity=severity,
                countries=countries,
                valid_from=valid_from,
                valid_to=valid_to,
                language_code=language,
                season=season,
                livelihood_hint=livelihood_hint,
            )
            output = await self.router.translate(system, user, language)
            output = await self._english_fallback_if_unusable(
                output,
                hazard_type=hazard_type,
                severity=severity,
                countries=countries,
                valid_from=valid_from,
                valid_to=valid_to,
                season=season,
                livelihood_hint=livelihood_hint,
            )
            if output.headline:
                await self._store_translation(alert_id, output)
            return output
        except Exception as exc:
            logger.error("processor.translate_error", language=language, error=str(exc))
            return None

    async def _english_fallback_if_unusable(
        self,
        output: TranslationOutput,
        *,
        hazard_type: str,
        severity: str,
        countries: list[str],
        valid_from: str,
        valid_to: str,
        season: str | None,
        livelihood_hint: str | None,
    ) -> TranslationOutput:
        """Serve English when a low-resource translation is below the clarity floor.

        Tigrinya, Luganda and Afar have thin training data, and a fluent-looking
        but wrong instruction is more dangerous here than an English one the
        reader may have to ask someone to interpret. The row keeps the requested
        language so lookups still hit, with `fallback_language` recording that
        the text is not in it.
        """
        language = output.language
        if language not in LOW_RESOURCE_LANGUAGES or language == "en":
            return output

        usable = bool(output.headline) and output.clarity_score >= settings.ai_min_clarity_score
        if usable:
            return output

        logger.warning(
            "processor.low_resource_fallback",
            language=language,
            score=round(output.clarity_score, 3),
            floor=settings.ai_min_clarity_score,
        )
        english = await self.router.translate(
            translation_system_prompt(),
            translation_user_prompt(
                hazard_type=hazard_type,
                severity=severity,
                countries=countries,
                valid_from=valid_from,
                valid_to=valid_to,
                language_code="en",
                season=season,
                livelihood_hint=livelihood_hint,
            ),
            "en",
        )
        if not english.headline:
            # English failed too — the original is still better than nothing.
            return output

        return english.model_copy(update={"language": language, "fallback_language": "en"})

    async def _generate_action_card(
        self,
        alert_id: UUID,
        hazard_type: str,
        severity: str,
        countries: list[str],
        livelihood: str,
        season: str | None,
        language: str = "en",
    ) -> ActionCard | None:
        system = action_card_system_prompt()
        user = action_card_user_prompt(
            hazard_type=hazard_type,
            severity=severity,
            countries=countries,
            livelihood=livelihood,
            season=season,
            language=language,
        )
        steps, provider = await self.router.complete_with_provider(system, user)
        if not steps:
            return None
        return ActionCard(
            alert_id=alert_id,
            livelihood=livelihood,
            language=language,
            steps=steps,
            generated_by=provider,
        )

    async def translate_on_demand(self, alert_id: UUID, language: str) -> TranslationOutput | None:
        """Generate and store one alert translation that the backlog has not reached."""
        alert = await self._fetch_alert(alert_id)
        if not alert:
            return None

        countries = list(alert.get("affected_countries") or [])
        valid_from = alert["valid_from"].strftime("%Y-%m-%d %H:%M UTC") if alert.get("valid_from") else "now"
        valid_to = alert["valid_to"].strftime("%Y-%m-%d %H:%M UTC") if alert.get("valid_to") else "72 hours from now"

        return await self._translate_one(
            alert_id=alert_id,
            hazard_type=alert["hazard_type"],
            severity=alert["severity"],
            countries=countries,
            valid_from=valid_from,
            valid_to=valid_to,
            language=language,
            season=get_season(alert.get("valid_from")),
            livelihood_hint=get_dominant_livelihood(countries),
        )

    async def generate_action_card_on_demand(
        self, alert_id: UUID, livelihood: str, language: str
    ) -> ActionCard | None:
        """Generate and store a single action card, used when the API is asked
        for a livelihood/language combination that hasn't been backfilled yet.
        """
        alert = await self._fetch_alert(alert_id)
        if not alert:
            return None

        season = get_season(alert.get("valid_from"))
        countries = list(alert.get("affected_countries") or [])

        card = await self._generate_action_card(
            alert_id=alert_id,
            hazard_type=alert["hazard_type"],
            severity=alert["severity"],
            countries=countries,
            livelihood=livelihood,
            season=season,
            language=language,
        )
        if card:
            await self._store_action_card(card)
        return card

    async def _assess_severity_upgrade(
        self,
        alert_id: UUID,
        current_severity: str,
        hazard_type: str,
    ) -> AlertUpgradeSignal | None:
        """Innovation 3: check if community reports support severity escalation.

        Only runs if enough reports exist (GROUND_TRUTH_UPGRADE_THRESHOLD).
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT description FROM community_reports
                WHERE reported_at > NOW() - INTERVAL '24 hours'
                  AND ST_Intersects(
                    location,
                    (SELECT geom FROM alerts WHERE id = $1)
                  )
                LIMIT 20
                """,
                alert_id,
            )

        if len(rows) < settings.ground_truth_upgrade_threshold:
            logger.debug(
                "processor.upgrade_below_threshold",
                alert_id=str(alert_id),
                reports=len(rows),
                threshold=settings.ground_truth_upgrade_threshold,
            )
            return None

        descriptions = [r["description"] for r in rows if r["description"]]

        logger.info(
            "processor.upgrade_assessment_started",
            alert_id=str(alert_id),
            reports=len(rows),
            current_severity=current_severity,
        )

        system = severity_assessment_system_prompt()
        user = severity_assessment_user_prompt(
            current_severity=current_severity,
            hazard_type=hazard_type,
            report_count=len(rows),
            descriptions=descriptions,
        )

        raw = await self.router.complete(system, user)
        if not raw:
            # Distinguishable from "the model considered it and said no". Without
            # this, an exhausted provider quota and a genuine no-upgrade verdict
            # both surfaced as upgrade_signal: null with nothing in the log, so a
            # silently dead escalation path looked exactly like a working one.
            logger.warning(
                "processor.upgrade_assessment_unavailable",
                alert_id=str(alert_id),
                reports=len(rows),
                reason="all AI providers failed",
            )
            return None

        try:
            parsed = _parse_json_block(raw)
            current_rank = SEVERITY_RANK.get(current_severity, 0)
            proposed = parsed.get("proposed_severity", current_severity)
            proposed_rank = SEVERITY_RANK.get(proposed, 0)
            confidence = float(parsed.get("confidence", 0.0))
            # Confidence gate per spec §3.6. It was previously parsed and stored
            # but never compared, so a low-confidence model guess could raise an
            # official alert to red — and now trigger a real SMS broadcast.
            should_upgrade = (
                bool(parsed.get("should_upgrade", False))
                and proposed_rank > current_rank
                and confidence > MIN_UPGRADE_CONFIDENCE
            )
            if bool(parsed.get("should_upgrade", False)) and proposed_rank > current_rank and not should_upgrade:
                logger.info(
                    "processor.upgrade_below_confidence",
                    alert_id=str(alert_id),
                    confidence=confidence,
                    floor=MIN_UPGRADE_CONFIDENCE,
                )

            return AlertUpgradeSignal(
                alert_id=alert_id,
                current_severity=current_severity,
                proposed_severity=proposed,
                report_count=len(rows),
                confidence=confidence,
                supporting_descriptions=descriptions[:5],
                claude_reasoning=parsed.get("reasoning", ""),
                should_upgrade=should_upgrade,
            )
        except Exception as exc:
            logger.warning("processor.upgrade_parse_failed", error=str(exc))
            return None

    async def _regenerate_content(
        self,
        *,
        alert_id: UUID,
        alert: dict,
        countries: list[str],
        season: str,
        dominant_livelihood: str,
        valid_from: str,
        valid_to: str,
        result: ProcessingResult,
        log,
    ) -> None:
        """Re-run translations and action cards after a severity upgrade."""
        translations = await asyncio.gather(
            *[
                self._translate_one(
                    alert_id=alert_id,
                    hazard_type=alert["hazard_type"],
                    severity=alert["severity"],
                    countries=countries,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    language=lang,
                    season=season,
                    livelihood_hint=dominant_livelihood,
                )
                for lang in LANGUAGES
            ]
        )
        regenerated = sum(1 for t in translations if t and not t.error)

        cards = 0
        for livelihood in PREGENERATED_CARD_LIVELIHOODS:
            for lang in PREGENERATED_CARD_LANGUAGES:
                try:
                    card = await self._generate_action_card(
                        alert_id=alert_id,
                        hazard_type=alert["hazard_type"],
                        severity=alert["severity"],
                        countries=countries,
                        livelihood=livelihood,
                        season=season,
                        language=lang,
                    )
                    if card:
                        await self._store_action_card(card)
                        cards += 1
                except Exception as exc:
                    result.errors.append(f"Regenerated action card {livelihood}/{lang}: {exc}")

        log.info("processor.content_regenerated", translations=regenerated, action_cards=cards)

    # -- DB operations ------------------------------------------------------------

    async def _fetch_alert(self, alert_id: UUID) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, hazard_type, severity, affected_countries, valid_from, valid_to
                FROM alerts WHERE id = $1
                """,
                alert_id,
            )
        return dict(row) if row else None

    async def _store_translation(self, alert_id: UUID, output: TranslationOutput) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO alert_translations (alert_id, language, headline, body, fallback_language)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (alert_id, language) DO UPDATE
                  SET headline = EXCLUDED.headline,
                      body = EXCLUDED.body,
                      fallback_language = EXCLUDED.fallback_language
                """,
                alert_id,
                output.language,
                output.headline[:240],
                output.body[:1200],
                output.fallback_language,
            )

    async def _store_action_card(self, card: ActionCard) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO action_cards (alert_id, livelihood, language, steps)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (alert_id, livelihood, language) DO UPDATE
                  SET steps = EXCLUDED.steps
                """,
                card.alert_id,
                card.livelihood,
                card.language,
                card.steps,
            )

    async def _apply_severity_upgrade(self, alert_id: UUID, upgrade: AlertUpgradeSignal) -> None:
        """Apply the upgrade and invalidate everything derived from the old severity.

        Translations and action cards state the severity in their text, so they
        must be regenerated — otherwise an alert upgraded to red keeps telling
        people, in six languages, that it is orange. Clearing broadcast_at lets
        the alert be sent again at its new severity, which is the whole point of
        the escalation.
        """
        async with self.pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE alerts SET severity = $1, processed_at = NOW(), broadcast_at = NULL WHERE id = $2",
                upgrade.proposed_severity,
                alert_id,
            )
            await conn.execute("DELETE FROM alert_translations WHERE alert_id = $1", alert_id)
            await conn.execute("DELETE FROM action_cards WHERE alert_id = $1", alert_id)

        logger.info(
            "processor.upgrade_invalidated_content",
            alert_id=str(alert_id),
            new_severity=upgrade.proposed_severity,
        )

    async def classify_report(self, report_id: UUID, description: str, hazard_type: str) -> list[str]:
        """Classify a community report description into labels.

        Called asynchronously after report submission.
        """
        system = report_label_system_prompt()
        user = report_label_user_prompt(description, hazard_type)

        raw = await self.router.complete(system, user)
        if not raw:
            return []

        try:
            parsed = _parse_json_block(raw)
            # Constrain to the closed vocabulary. Anything the model invents
            # would otherwise flow into the map legend and the analyse panel.
            seen: list[str] = []
            for label in parsed.get("labels", []):
                normalised = str(label).strip().lower().replace(" ", "_")
                if normalised in VALID_REPORT_LABELS and normalised not in seen:
                    seen.append(normalised)
            rejected = len(parsed.get("labels", [])) - len(seen)
            if rejected > 0:
                logger.info("processor.labels_rejected", report_id=str(report_id), rejected=rejected)
            labels = seen[:6]
        except Exception:
            labels = []

        if labels:
            async with self.pool.acquire() as conn:
                await conn.execute("UPDATE community_reports SET labels = $1 WHERE id = $2", labels, report_id)

        return labels


# -- Module-level shared instance ------------------------------------------------

_processor: AlertProcessor | None = None


def get_processor(pool: asyncpg.Pool) -> AlertProcessor:
    global _processor
    if _processor is None:
        _processor = AlertProcessor(pool)
    return _processor


async def process_backlog(pool: asyncpg.Pool) -> dict:
    """Process alerts that don't have translations yet.

    Called on startup and by the admin endpoint. Processes in batches to
    avoid overwhelming API rate limits.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id FROM alerts a
            WHERE (a.valid_to > NOW() OR a.valid_to IS NULL)
              AND (
                NOT EXISTS (
                  SELECT 1 FROM alert_translations t
                  WHERE t.alert_id = a.id AND t.language = 'sw'
                )
                -- Also retry alerts whose translations landed but whose action
                -- cards did not. Checking only translations left such alerts
                -- permanently without cards, so USSD and SMS fell back to
                -- generic guidance instead of livelihood-specific steps.
                OR NOT EXISTS (
                  SELECT 1 FROM action_cards c WHERE c.alert_id = a.id
                )
              )
            ORDER BY
              CASE a.severity WHEN 'red' THEN 0 WHEN 'orange' THEN 1 ELSE 2 END,
              a.created_at DESC
            LIMIT $1
            """,
            settings.ai_backlog_batch_size,
        )

    alert_ids = [r["id"] for r in rows]
    if not alert_ids:
        logger.info("processor.backlog_empty")
        return {"processed": 0, "total_found": 0, "errors": 0}

    logger.info("processor.backlog_start", count=len(alert_ids))
    processor = get_processor(pool)
    sem = asyncio.Semaphore(settings.ai_max_concurrent_alerts)

    async def process_one(aid: UUID) -> ProcessingResult:
        async with sem:
            return await processor.process_alert(aid)

    results = await asyncio.gather(*[process_one(aid) for aid in alert_ids], return_exceptions=True)

    completed = sum(1 for r in results if isinstance(r, ProcessingResult))
    errors = sum(1 for r in results if isinstance(r, Exception))

    logger.info("processor.backlog_complete", total=len(alert_ids), completed=completed, errors=errors)
    return {"total_found": len(alert_ids), "processed": completed, "errors": errors}
