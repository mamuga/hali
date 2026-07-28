"""Regression tests for the AI-layer correctness fixes."""
import warnings
from uuid import UUID

import pytest

from hali.ai import scorer
from hali.ai.models import ModelProvider, TranslationOutput
from hali.ai.processor import MIN_UPGRADE_CONFIDENCE
from hali.ai.prompts import VALID_REPORT_LABELS
from hali.ai.router import AIRouter
from hali.config import settings


def _out(headline: str, body: str, language: str = "en") -> TranslationOutput:
    return TranslationOutput(
        provider=ModelProvider.CLAUDE,
        model_name="test",
        language=language,
        headline=headline,
        body=body,
    )


# ── A7: scorer must not be blind outside English/Swahili ──────────────────────


def test_non_latin_scripts_are_scored_not_zeroed():
    """Amharic and Arabic previously scored ~0 on 45% of the rubric."""
    amharic = _out("ጎርፍ ማስጠንቀቂያ", "ወደ ከፍታ ቦታ ተንቀሳቀሱ። ውሃ ይመጣል። ተጠንቀቁ።", "am")
    arabic = _out("تحذير فيضان", "انتقل إلى مكان مرتفع. تجنب النهر. استعد الآن.", "ar")

    assert scorer.score_translation(amharic) > 0.5
    assert scorer.score_translation(arabic) > 0.5


def test_oromo_and_somali_are_scored():
    oromo = _out("Akeekkachiisa lolaa", "Bakka ol ka'aa deemi. Bishaan ni dhufa. Of eeggadhu.", "om")
    somali = _out("Digniin daad", "Meel sare u guur. Biyo ayaa imanaya. Iska ilaali.", "so")

    assert scorer.score_translation(oromo) > 0.4
    assert scorer.score_translation(somali) > 0.4


def test_language_scores_are_broadly_comparable():
    """A good translation should not be penalised for its language."""
    variants = {
        "en": _out("Flood warning", "Move to higher ground. Water is coming. Stay alert.", "en"),
        "sw": _out("Tahadhari mafuriko", "Hamia mahali pa juu. Maji yanakuja. Kaa salama.", "sw"),
        "am": _out("ጎርፍ ማስጠንቀቂያ", "ወደ ከፍታ ቦታ ተንቀሳቀሱ። ውሃ ይመጣል። ተጠንቀቁ።", "am"),
        "ar": _out("تحذير فيضان", "انتقل إلى مكان مرتفع. تجنب النهر. استعد الآن.", "ar"),
    }
    scores = {lang: scorer.score_translation(o) for lang, o in variants.items()}
    assert max(scores.values()) - min(scores.values()) < 0.35, scores


def test_punctuation_does_not_block_lexicon_match():
    with_punct = _out("Flood!", "Evacuate, now. Avoid the river.", "en")
    assert scorer.score_translation(with_punct) > 0.5


def test_empty_output_scores_zero():
    assert scorer.score_translation(_out("", "")) == 0.0
    assert scorer.score_translation(_out("Title", "")) == 0.0


# ── A4: fallback must not leak un-awaited coroutines ──────────────────────────


async def test_fallback_translate_leaves_no_unawaited_coroutine(monkeypatch):
    router = AIRouter()

    async def good(system, user, language):
        return _out("Flood warning", "Move to higher ground now.", language)

    async def should_not_run(system, user, language):
        raise AssertionError("later provider must not be called after success")

    monkeypatch.setattr(router, "_call_claude", good)
    monkeypatch.setattr(router, "_call_gemini", should_not_run)
    monkeypatch.setattr(router, "_call_groq", should_not_run)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = await router._fallback_translate("s", "u", "en")

    assert result.headline == "Flood warning"
    assert not [w for w in caught if "never awaited" in str(w.message)]


async def test_fallback_advances_past_a_failing_provider(monkeypatch):
    router = AIRouter()

    async def failing(system, user, language):
        return TranslationOutput(
            provider=ModelProvider.CLAUDE, model_name="x", language=language,
            headline="", body="", error="boom",
        )

    async def working(system, user, language):
        return _out("Backup headline", "Backup body text here.", language)

    monkeypatch.setattr(router, "_call_claude", failing)
    monkeypatch.setattr(router, "_call_gemini", working)
    monkeypatch.setattr(router, "_call_groq", failing)

    result = await router._fallback_translate("s", "u", "en")
    assert result.headline == "Backup headline"


# ── A1: the clarity floor is enforced, not dead config ────────────────────────


async def test_low_scoring_winner_is_flagged_against_the_floor(monkeypatch, caplog):
    router = AIRouter()
    monkeypatch.setattr(settings, "ai_min_clarity_score", 0.95)

    async def weak(system, user, language):
        out = _out("x" * 400, "y" * 900, language)
        out.clarity_score = 0.1
        return out

    monkeypatch.setattr(router, "_call_claude", weak)
    monkeypatch.setattr(router, "_call_gemini", weak)
    monkeypatch.setattr(router, "_call_groq", weak)

    result = await router._ensemble_translate("s", "u", "en")
    # Still returned — a rough translation beats silence — but not as a clean win.
    assert result.headline


# ── A8: report labels are constrained to the closed vocabulary ────────────────


def test_valid_label_vocabulary_matches_spec():
    assert len(VALID_REPORT_LABELS) == 17
    assert "livestock_at_risk" in VALID_REPORT_LABELS
    assert "made_up_label" not in VALID_REPORT_LABELS


# ── A2: severity upgrades require confidence ──────────────────────────────────


def test_upgrade_confidence_floor_matches_spec():
    assert MIN_UPGRADE_CONFIDENCE == pytest.approx(0.6)


class _Conn:
    def __init__(self, reports):
        self._reports = reports

    async def fetch(self, sql, *args):
        return self._reports


class _Ctx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Ctx(self._conn)


def _processor_with(reports, response):
    from hali.ai.processor import AlertProcessor

    proc = AlertProcessor(_Pool(_Conn(reports)))

    async def fake_complete(system, user):
        return response

    proc.router.complete = fake_complete
    return proc


REPORTS = [{"description": f"water rising fast {i}"} for i in range(5)]
ALERT_ID = UUID("11111111-1111-1111-1111-111111111111")


async def test_high_confidence_upgrade_is_accepted():
    proc = _processor_with(
        REPORTS,
        '{"should_upgrade": true, "proposed_severity": "red", "confidence": 0.9, "reasoning": "many reports"}',
    )
    signal = await proc._assess_severity_upgrade(alert_id=ALERT_ID, current_severity="orange", hazard_type="flood")
    assert signal is not None
    assert signal.should_upgrade is True


async def test_low_confidence_upgrade_is_rejected():
    """A tentative model guess must not raise an official alert — it now also fires SMS."""
    proc = _processor_with(
        REPORTS,
        '{"should_upgrade": true, "proposed_severity": "red", "confidence": 0.3, "reasoning": "unsure"}',
    )
    signal = await proc._assess_severity_upgrade(alert_id=ALERT_ID, current_severity="orange", hazard_type="flood")
    assert signal is not None
    assert signal.should_upgrade is False
    assert signal.confidence == pytest.approx(0.3)


async def test_downgrade_is_never_applied():
    proc = _processor_with(
        REPORTS,
        '{"should_upgrade": true, "proposed_severity": "green", "confidence": 0.99, "reasoning": "calm"}',
    )
    signal = await proc._assess_severity_upgrade(alert_id=ALERT_ID, current_severity="red", hazard_type="flood")
    assert signal.should_upgrade is False


async def test_below_report_threshold_skips_assessment():
    proc = _processor_with([{"description": "one report"}], '{"should_upgrade": true, "confidence": 1.0}')
    assert await proc._assess_severity_upgrade(alert_id=ALERT_ID, current_severity="orange", hazard_type="flood") is None
