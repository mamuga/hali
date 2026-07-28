"""Outbound alert fan-out to SMS and WhatsApp subscribers.

Triggered after an alert finishes AI processing, so translations and action
cards exist by the time subscribers are messaged.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from hali.repositories.alerts import AlertRepository
from hali.repositories.subscriptions import SubscriptionRepository
from hali.services.sms import send_sms, truncate

logger = structlog.get_logger(__name__)

# Only these severities justify an unsolicited message.
BROADCASTABLE_SEVERITIES = {"orange", "red"}
# Bounded fan-out: both AT and Meta rate-limit, and an unbounded gather over a
# large subscriber list would trip them.
MAX_CONCURRENT_SENDS = 5


async def broadcast_alert(alert_id: UUID, pool: asyncpg.Pool, force: bool = False) -> dict[str, Any]:
    """Send one alert to every matching opted-in subscriber.

    Guarded so an alert is broadcast once: re-running the AI backlog must not
    re-send SMS that subscribers already paid attention to.
    """
    alerts = AlertRepository(pool)
    subscriptions = SubscriptionRepository(pool)

    async with pool.acquire() as conn:
        alert = await conn.fetchrow(
            "SELECT id, hazard_type, severity, affected_countries, valid_to, broadcast_at FROM alerts WHERE id = $1",
            alert_id,
        )

    if alert is None:
        return {"status": "alert_not_found", "sent": 0}

    if alert["severity"] not in BROADCASTABLE_SEVERITIES:
        return {"status": "skipped_low_severity", "severity": alert["severity"], "sent": 0}

    if alert["valid_to"] is not None and alert["valid_to"] <= _now(alert["valid_to"]):
        return {"status": "skipped_expired", "sent": 0}

    # Claim the send with a conditional UPDATE so two concurrent callers cannot
    # both fan out the same alert.
    if not force:
        async with pool.acquire() as conn:
            claimed = await conn.fetchval(
                "UPDATE alerts SET broadcast_at = NOW() WHERE id = $1 AND broadcast_at IS NULL RETURNING id",
                alert_id,
            )
        if claimed is None:
            return {"status": "already_broadcast", "sent": 0}

    subscribers = await subscriptions.matching_subscribers(alert_id)
    if not subscribers:
        logger.info("broadcast.no_subscribers", alert_id=str(alert_id))
        return {"status": "no_subscribers", "sent": 0}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SENDS)

    async def deliver(subscriber: dict[str, Any]) -> dict[str, bool]:
        async with semaphore:
            return await _deliver_to(subscriber, alert, alerts)

    # return_exceptions keeps one bad number from aborting the whole broadcast.
    results = await asyncio.gather(*(deliver(sub) for sub in subscribers), return_exceptions=True)

    sms_sent = 0
    whatsapp_sent = 0
    failed = 0
    for result in results:
        if isinstance(result, BaseException):
            failed += 1
            logger.error("broadcast.delivery_crashed", error=str(result))
            continue
        sms_sent += int(result.get("sms", False))
        whatsapp_sent += int(result.get("whatsapp", False))
        if not result.get("sms") and not result.get("whatsapp"):
            failed += 1

    summary = {
        "status": "ok",
        "alert_id": str(alert_id),
        "severity": alert["severity"],
        "subscribers": len(subscribers),
        "sms_sent": sms_sent,
        "whatsapp_sent": whatsapp_sent,
        "failed": failed,
        "sent": sms_sent + whatsapp_sent,
    }
    logger.info("broadcast.complete", **summary)
    return summary


async def _deliver_to(subscriber: dict[str, Any], alert: Any, alerts: AlertRepository) -> dict[str, bool]:
    language = subscriber["language"]
    livelihood = subscriber["livelihood"]
    phone = subscriber["phone_number"]
    channel = subscriber["channel"]

    headline = (await alerts.translation(alert["id"], language))["headline"]

    card = await alerts.action_card(alert["id"], livelihood, language)
    if card is None:
        card = await alerts.action_card(alert["id"], livelihood, "en")
    first_step = _first_step(card["steps"]) if card else ""

    outcome = {"sms": False, "whatsapp": False}

    if channel in ("sms", "both"):
        body = f"HALI {alert['severity'].upper()}: {headline}"
        if first_step:
            body = f"{body} - {first_step}"
        outcome["sms"] = await send_sms(phone, truncate(body))

    if channel in ("whatsapp", "both"):
        from hali.routers.whatsapp import send_alert_template

        outcome["whatsapp"] = await send_alert_template(phone, alert, headline, first_step, language)

    return outcome


def _now(reference: datetime) -> datetime:
    """Current time matching the reference's tz-awareness, for safe comparison."""
    return datetime.now(reference.tzinfo) if reference.tzinfo else datetime.now()


def _first_step(steps: str) -> str:
    for line in (steps or "").splitlines():
        cleaned = line.strip().lstrip("-•*0123456789. ").strip()
        if cleaned:
            return cleaned
    return ""


async def broadcast_new_alerts(pool: asyncpg.Pool, alert_ids: list[UUID]) -> list[dict[str, Any]]:
    """Broadcast several alerts in sequence, isolating failures per alert."""
    summaries = []
    for alert_id in alert_ids:
        try:
            summaries.append(await broadcast_alert(alert_id, pool))
        except Exception as exc:
            logger.error("broadcast.alert_failed", alert_id=str(alert_id), error=str(exc))
            summaries.append({"status": "error", "alert_id": str(alert_id), "error": str(exc), "sent": 0})
    return summaries
