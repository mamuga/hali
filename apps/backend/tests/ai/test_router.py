"""Test AI router fallback and ensemble logic."""
from unittest.mock import patch

import pytest

from hali.ai.models import ModelProvider, TranslationOutput
from hali.ai.router import AIRouter


@pytest.fixture
def router():
    return AIRouter()


@pytest.mark.asyncio
async def test_router_returns_cached_when_all_fail(router):
    """If all providers fail, return a CACHED marker, never raise."""
    failed_claude = TranslationOutput(provider=ModelProvider.CLAUDE, model_name="test", language="sw", headline="", body="", error="failed")
    failed_gemini = TranslationOutput(provider=ModelProvider.GEMINI, model_name="test", language="sw", headline="", body="", error="failed")
    failed_groq = TranslationOutput(provider=ModelProvider.GROQ, model_name="test", language="sw", headline="", body="", error="failed")

    async def _claude(*a, **k):
        return failed_claude

    async def _gemini(*a, **k):
        return failed_gemini

    async def _groq(*a, **k):
        return failed_groq

    with patch.object(router, "_call_claude", side_effect=_claude), patch.object(router, "_call_gemini", side_effect=_gemini), patch.object(router, "_call_groq", side_effect=_groq):
        result = await router._ensemble_translate("sys", "user", "sw")

    assert result.provider == ModelProvider.CACHED
    assert result.error is not None


@pytest.mark.asyncio
async def test_router_picks_highest_scored(router):
    """Ensemble should return the output with the highest clarity score."""
    low_score = TranslationOutput(
        provider=ModelProvider.GEMINI, model_name="g", language="sw",
        headline="Alert", body="There is an alert.", clarity_score=0.2,
    )
    high_score = TranslationOutput(
        provider=ModelProvider.CLAUDE, model_name="c", language="sw",
        headline="Flood coming. Move livestock now.",
        body="Heavy flood expected tomorrow. Move cattle to high ground. Avoid rivers. Contact local officials.",
        clarity_score=0.75,
    )
    failed_groq = TranslationOutput(provider=ModelProvider.GROQ, model_name="g", language="sw", headline="", body="", error="failed")

    async def _claude(*a, **k):
        return high_score

    async def _gemini(*a, **k):
        return low_score

    async def _groq(*a, **k):
        return failed_groq

    with patch.object(router, "_call_claude", side_effect=_claude), patch.object(router, "_call_gemini", side_effect=_gemini), patch.object(router, "_call_groq", side_effect=_groq):
        result = await router._ensemble_translate("sys", "user", "sw")

    assert result.provider == ModelProvider.CLAUDE
    assert result.clarity_score == 0.75
