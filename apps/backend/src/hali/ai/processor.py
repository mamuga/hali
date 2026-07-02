from uuid import UUID

import asyncpg
import structlog

from hali.ai.claude import LANGUAGES, LIVELIHOODS, ClaudeService
from hali.config import get_settings

log = structlog.get_logger()


async def translate_alert(alert_id: UUID, hazard_type: str, severity: str, affected_countries: list[str], pool: asyncpg.Pool) -> None:
    claude = ClaudeService(get_settings())
    fallback = {
        lang: {"headline": f"{severity.title()} {hazard_type} alert", "body": f"{hazard_type.title()} alert affecting {', '.join(affected_countries) or 'East Africa'}. Follow local guidance."}
        for lang in LANGUAGES
    }
    data = await claude.json_prompt(
        "Return JSON keyed by sw, so, am, om, ar, en. Each value has headline max 20 words and body max 80 words at Grade 5 reading level. "
        f"Do not invent details. Hazard={hazard_type}, severity={severity}, countries={affected_countries}."
    ) or fallback
    async with pool.acquire() as conn:
        for lang in LANGUAGES:
            item = data.get(lang, fallback[lang])
            await conn.execute(
                """
                INSERT INTO alert_translations (alert_id, language, headline, body)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (alert_id, language) DO UPDATE SET headline = EXCLUDED.headline, body = EXCLUDED.body
                """,
                alert_id,
                lang,
                str(item.get("headline", fallback[lang]["headline"]))[:240],
                str(item.get("body", fallback[lang]["body"]))[:1200],
            )


async def generate_action_cards(alert_id: UUID, hazard_type: str, severity: str, affected_countries: list[str], pool: asyncpg.Pool) -> None:
    claude = ClaudeService(get_settings())
    fallback = {livelihood: "1. Check official updates.\n2. Move people and key items away from danger.\n3. Share information with neighbours.\n4. Call local responders if help is needed." for livelihood in LIVELIHOODS}
    data = await claude.json_prompt(
        "Return JSON keyed by farmer, pastoralist, fisherfolk, urban. Each value is exactly 4 numbered plain-language actions. "
        f"Hazard={hazard_type}, severity={severity}, countries={affected_countries}."
    ) or fallback
    async with pool.acquire() as conn:
        for livelihood in LIVELIHOODS:
            await conn.execute(
                """
                INSERT INTO action_cards (alert_id, livelihood, language, steps)
                VALUES ($1, $2, 'en', $3)
                ON CONFLICT (alert_id, livelihood, language) DO UPDATE SET steps = EXCLUDED.steps
                """,
                alert_id,
                livelihood,
                str(data.get(livelihood, fallback[livelihood])),
            )


async def classify_community_report(report_id: UUID, description: str, hazard_type: str, pool: asyncpg.Pool) -> list[str]:
    claude = ClaudeService(get_settings())
    data = await claude.json_prompt(
        "Classify this community report into short labels from flooded-road, livestock-risk, crop-risk, water-shortage, disease-risk, infrastructure-damage, needs-verification. "
        f"Return JSON with labels array. Do not overclaim certainty. Hazard={hazard_type}. Description={description}"
    )
    labels = [str(label) for label in data.get("labels", [])][:6] if data else []
    async with pool.acquire() as conn:
        await conn.execute("UPDATE community_reports SET labels = $2 WHERE id = $1", report_id, labels)
    return labels


async def process_new_alert(alert_id: UUID, pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT hazard_type, severity, affected_countries FROM alerts WHERE id = $1", alert_id)
    if row is None:
        log.warning("alert_processing_skipped", alert_id=str(alert_id), reason="not_found")
        return
    await translate_alert(alert_id, row["hazard_type"], row["severity"], list(row["affected_countries"]), pool)
    await generate_action_cards(alert_id, row["hazard_type"], row["severity"], list(row["affected_countries"]), pool)
