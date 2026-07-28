"""The USSD latency budget must cover a whole request, not each query.

Africa's Talking kills the session at 3 seconds. A handler issues up to three
sequential queries, so a per-call timeout would permit 3x the budget.
"""
import asyncio
import time

import pytest

from hali.routers import ussd


async def _slow(seconds: float, value: str = "done"):
    await asyncio.sleep(seconds)
    return value


async def test_total_time_stays_within_budget_across_calls(monkeypatch):
    monkeypatch.setattr(ussd, "USSD_BUDGET_SECONDS", 0.4)
    ussd._deadline.set(time.monotonic() + 0.4)

    started = time.monotonic()
    # Three sequential slow calls, as the report flow makes.
    results = [
        await ussd._guarded(_slow(5), "fallback"),
        await ussd._guarded(_slow(5), "fallback"),
        await ussd._guarded(_slow(5), "fallback"),
    ]
    elapsed = time.monotonic() - started

    assert results == ["fallback", "fallback", "fallback"]
    # Without a shared deadline this would be ~3x the budget.
    assert elapsed < 0.8, f"three guarded calls took {elapsed:.2f}s, budget was 0.4s"


async def test_fast_call_returns_its_value():
    ussd._deadline.set(time.monotonic() + 2.0)
    assert await ussd._guarded(_slow(0.01, "value"), "fallback") == "value"


async def test_exhausted_budget_skips_the_call_entirely():
    ussd._deadline.set(time.monotonic() - 1)  # already past
    started = time.monotonic()
    assert await ussd._guarded(_slow(5), "fallback") == "fallback"
    # Should short-circuit rather than wait.
    assert time.monotonic() - started < 0.1


async def test_database_errors_degrade_to_fallback():
    async def boom():
        raise RuntimeError("connection reset")

    ussd._deadline.set(time.monotonic() + 2.0)
    assert await ussd._guarded(boom(), "fallback") == "fallback"


async def test_no_unawaited_coroutine_warning(recwarn):
    """A skipped coroutine must be closed, not leaked."""
    ussd._deadline.set(time.monotonic() - 1)
    await ussd._guarded(_slow(5), "fallback")
    assert not [w for w in recwarn if "never awaited" in str(w.message)]


@pytest.mark.parametrize("budget", [0.2, 0.5])
async def test_budget_is_respected_for_various_values(budget, monkeypatch):
    ussd._deadline.set(time.monotonic() + budget)
    started = time.monotonic()
    await ussd._guarded(_slow(5), "fallback")
    assert time.monotonic() - started < budget + 0.25
