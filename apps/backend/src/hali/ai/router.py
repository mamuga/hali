"""
AI Router - multi-model fallback chain for HALI.

Priority order:
  1. Claude (claude-sonnet-4-6)      - primary, best quality
  2. Gemini Flash (gemini-2.5-flash) - free tier, 1500 req/day
  3. Groq / Llama                    - free tier, fast inference
  4. Cached translation              - last resort, never fails

The router tries providers in order. On success it returns immediately
(no ensemble). For ensemble mode (AI_ENSEMBLE_ENABLED=true), it runs all
available providers in parallel and returns the best-scored output.

Rate limit awareness:
  - Tracks per-provider request counts in memory
  - Logs which provider won for observability
"""
from __future__ import annotations

import asyncio
import json
import time

import structlog

from hali.config import settings

from .models import ModelProvider, TranslationOutput
from .scorer import score_translation

logger = structlog.get_logger(__name__)


def _strip_markdown_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


class AIRouter:
    """Manages the multi-model fallback chain.

    Instantiate once and reuse across all alerts.
    """

    def __init__(self) -> None:
        self._claude_client = None
        self._gemini_client = None
        self._groq_client = None
        self._request_counts: dict[ModelProvider, int] = dict.fromkeys(ModelProvider, 0)

    # -- Client initialisation (lazy) -----------------------------------------

    def _get_claude(self):
        if not self._claude_client and settings.anthropic_api_key:
            import anthropic

            self._claude_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._claude_client

    def _get_gemini(self):
        if not self._gemini_client and settings.gemini_api_key:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            self._gemini_client = genai.GenerativeModel(settings.ai_gemini_model)
        return self._gemini_client

    def _get_groq(self):
        if not self._groq_client and settings.groq_api_key:
            from groq import AsyncGroq

            self._groq_client = AsyncGroq(api_key=settings.groq_api_key)
        return self._groq_client

    # -- Single-provider translation calls -------------------------------------

    async def _call_claude(self, system: str, user: str, language: str) -> TranslationOutput:
        start = time.perf_counter()
        client = self._get_claude()
        if not client:
            return TranslationOutput(
                provider=ModelProvider.CLAUDE,
                model_name=settings.ai_primary_model,
                language=language,
                headline="",
                body="",
                error="Claude API key not configured",
            )
        try:
            response = await client.messages.create(
                model=settings.ai_primary_model,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            raw = "".join(block.text for block in response.content if hasattr(block, "text"))
            parsed = json.loads(_strip_markdown_fence(raw))
            latency = (time.perf_counter() - start) * 1000
            self._request_counts[ModelProvider.CLAUDE] += 1
            output = TranslationOutput(
                provider=ModelProvider.CLAUDE,
                model_name=settings.ai_primary_model,
                language=language,
                headline=parsed.get("headline", ""),
                body=parsed.get("body", ""),
                latency_ms=latency,
            )
            output.clarity_score = score_translation(output)
            return output
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            logger.warning("router.claude_failed", error=str(exc), lang=language)
            return TranslationOutput(
                provider=ModelProvider.CLAUDE,
                model_name=settings.ai_primary_model,
                language=language,
                headline="",
                body="",
                latency_ms=latency,
                error=str(exc),
            )

    async def _call_gemini(self, system: str, user: str, language: str) -> TranslationOutput:
        start = time.perf_counter()
        client = self._get_gemini()
        if not client:
            return TranslationOutput(
                provider=ModelProvider.GEMINI,
                model_name=settings.ai_gemini_model,
                language=language,
                headline="",
                body="",
                error="Gemini API key not configured",
            )
        try:
            prompt = f"{system}\n\n{user}"
            response = await asyncio.to_thread(client.generate_content, prompt)
            parsed = json.loads(_strip_markdown_fence(response.text))
            latency = (time.perf_counter() - start) * 1000
            self._request_counts[ModelProvider.GEMINI] += 1
            output = TranslationOutput(
                provider=ModelProvider.GEMINI,
                model_name=settings.ai_gemini_model,
                language=language,
                headline=parsed.get("headline", ""),
                body=parsed.get("body", ""),
                latency_ms=latency,
            )
            output.clarity_score = score_translation(output)
            return output
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            logger.warning("router.gemini_failed", error=str(exc), lang=language)
            return TranslationOutput(
                provider=ModelProvider.GEMINI,
                model_name=settings.ai_gemini_model,
                language=language,
                headline="",
                body="",
                latency_ms=latency,
                error=str(exc),
            )

    async def _call_groq(self, system: str, user: str, language: str) -> TranslationOutput:
        start = time.perf_counter()
        client = self._get_groq()
        if not client:
            return TranslationOutput(
                provider=ModelProvider.GROQ,
                model_name=settings.ai_groq_model,
                language=language,
                headline="",
                body="",
                error="Groq API key not configured",
            )
        try:
            response = await client.chat.completions.create(
                model=settings.ai_groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=600,
                temperature=0.3,
            )
            raw = response.choices[0].message.content
            parsed = json.loads(_strip_markdown_fence(raw))
            latency = (time.perf_counter() - start) * 1000
            self._request_counts[ModelProvider.GROQ] += 1
            output = TranslationOutput(
                provider=ModelProvider.GROQ,
                model_name=settings.ai_groq_model,
                language=language,
                headline=parsed.get("headline", ""),
                body=parsed.get("body", ""),
                latency_ms=latency,
            )
            output.clarity_score = score_translation(output)
            return output
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            logger.warning("router.groq_failed", error=str(exc), lang=language)
            return TranslationOutput(
                provider=ModelProvider.GROQ,
                model_name=settings.ai_groq_model,
                language=language,
                headline="",
                body="",
                latency_ms=latency,
                error=str(exc),
            )

    # -- Public interface -------------------------------------------------------

    async def translate(self, system_prompt: str, user_prompt: str, language: str) -> TranslationOutput:
        """Ensemble mode: run all configured providers in parallel, return the
        best-scoring output. Falls back through the chain sequentially if
        ensemble mode is disabled.
        """
        if settings.ai_ensemble_enabled:
            return await self._ensemble_translate(system_prompt, user_prompt, language)
        return await self._fallback_translate(system_prompt, user_prompt, language)

    async def _ensemble_translate(self, system: str, user: str, language: str) -> TranslationOutput:
        """Run all providers concurrently, score each, return the winner.

        If no output is valid, returns a CACHED marker rather than raising.
        """
        results = await asyncio.gather(
            self._call_claude(system, user, language),
            self._call_gemini(system, user, language),
            self._call_groq(system, user, language),
        )

        valid = [r for r in results if not r.error and r.headline]

        if not valid:
            logger.error("router.ensemble_all_failed", language=language)
            return TranslationOutput(
                provider=ModelProvider.CACHED,
                model_name="none",
                language=language,
                headline="",
                body="",
                error="All providers failed",
            )

        winner = max(valid, key=lambda r: r.clarity_score)
        # AI_MIN_CLARITY_SCORE is a floor, not a preference: an output nobody can
        # act on is worse than none. It is still returned (a rough translation
        # beats silence in an emergency) but flagged so it is visible in logs and
        # stats rather than passing as a clean win.
        below_floor = winner.clarity_score < settings.ai_min_clarity_score
        if below_floor:
            logger.warning(
                "router.below_clarity_floor",
                language=language,
                provider=winner.provider.value,
                score=round(winner.clarity_score, 3),
                floor=settings.ai_min_clarity_score,
            )
        else:
            logger.info(
                "router.ensemble_winner",
                language=language,
                provider=winner.provider.value,
                score=round(winner.clarity_score, 3),
                latency_ms=round(winner.latency_ms, 1),
            )
        return winner

    async def _fallback_translate(self, system: str, user: str, language: str) -> TranslationOutput:
        """Sequential fallback: Claude -> Gemini -> Groq -> cached."""
        # Built lazily. Creating all three coroutines up front and awaiting them
        # in a loop left the unused ones un-awaited whenever an earlier provider
        # succeeded, which raises "coroutine was never awaited" at GC time.
        for call in (self._call_claude, self._call_gemini, self._call_groq):
            result = await call(system, user, language)
            if not result.error and result.headline:
                return result

        return TranslationOutput(
            provider=ModelProvider.CACHED,
            model_name="none",
            language=language,
            headline="",
            body="",
            error="All providers exhausted",
        )

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """General-purpose completion (not translation)."""
        text, _provider = await self.complete_with_provider(system_prompt, user_prompt)
        return text

    async def complete_with_provider(self, system_prompt: str, user_prompt: str) -> tuple[str, ModelProvider]:
        """Like complete(), but also reports which provider actually answered.

        Callers previously had to guess, and action cards were recorded as
        Claude-generated regardless of which model produced them, which made
        /api/admin/ai-stats misreport the ensemble.
        """
        for provider, fn in (
            (ModelProvider.CLAUDE, self._call_raw_claude),
            (ModelProvider.GEMINI, self._call_raw_gemini),
            (ModelProvider.GROQ, self._call_raw_groq),
        ):
            try:
                result = await fn(system_prompt, user_prompt)
                if result:
                    self._request_counts[provider] = self._request_counts.get(provider, 0) + 1
                    return result, provider
            except Exception as exc:
                logger.warning("router.complete_failed", provider=provider.value, error=str(exc))
        return "", ModelProvider.CACHED

    async def _call_raw_claude(self, system: str, user: str) -> str:
        client = self._get_claude()
        if not client:
            return ""
        response = await client.messages.create(
            model=settings.ai_primary_model,
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if hasattr(block, "text")).strip()

    async def _call_raw_gemini(self, system: str, user: str) -> str:
        client = self._get_gemini()
        if not client:
            return ""
        prompt = f"{system}\n\n{user}"
        response = await asyncio.to_thread(client.generate_content, prompt)
        return response.text.strip()

    async def _call_raw_groq(self, system: str, user: str) -> str:
        client = self._get_groq()
        if not client:
            return ""
        response = await client.chat.completions.create(
            model=settings.ai_groq_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()

    def stats(self) -> dict:
        return {p.value: c for p, c in self._request_counts.items()}
