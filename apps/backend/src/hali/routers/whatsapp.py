"""
WhatsApp Cloud API router.

Two endpoints:
  GET  /whatsapp  — webhook verification (Meta handshake on setup)
  POST /whatsapp  — incoming message handler

Message flow:
  User sends WhatsApp message -> Meta POSTs to /whatsapp
  -> parse intent -> query latest alert -> reply via Cloud API

Menu (text-based, no USSD character limits):
  "alerts"    -> latest active alert for East Africa
  "help"      -> what HALI can do
  "report X"  -> acknowledge a hazard report (same as USSD: acknowledgement only,
                 no DB write, since a text message carries no coordinates)
  anything else -> gentle prompt
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request

from hali.config import settings
from hali.database import db
from hali.services.alerts import AlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

GRAPH_API_BASE = "https://graph.facebook.com"


# ── Webhook verification (Meta handshake) ─────────────────────────────────────


@router.get("")
async def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ── Incoming message handler ──────────────────────────────────────────────────


@router.post("")
async def whatsapp_webhook(request: Request):
    body_bytes = await request.body()

    if not _verify_signature(body_bytes, request.headers.get("X-Hub-Signature-256", "")):
        logger.warning("WhatsApp webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Status update (delivered, read) — acknowledge and ignore
            return {"status": "ok"}

        message = messages[0]
        from_number = message.get("from")
        msg_type = message.get("type", "text")

        if msg_type == "text":
            text = message.get("text", {}).get("body", "").strip().lower()
        else:
            await _send_whatsapp_message(
                from_number,
                "HALI inasimamia maandishi tu kwa sasa. Andika *alerts* kupata tahadhari, au *help* kwa msaada.",
            )
            return {"status": "ok"}

    except (IndexError, KeyError, TypeError) as exc:
        logger.error(f"WhatsApp payload parse error: {exc}")
        return {"status": "ok"}  # Always 200 to Meta or they retry indefinitely

    reply = await _handle_intent(text)
    if reply:
        await _send_whatsapp_message(from_number, reply)

    return {"status": "ok"}


# ── Intent routing ────────────────────────────────────────────────────────────


async def _handle_intent(text: str) -> str:
    if text in ("alerts", "tahadhari", "alert"):
        return await _get_latest_alert()

    if text.startswith("report ") or text.startswith("ripoti "):
        description = text.split(" ", 1)[1].strip()
        if len(description) < 5:
            return "Tafadhali eleza zaidi. Mfano: _report maji yamefika mtaa wangu_"
        logger.info("WhatsApp hazard report acknowledged (not persisted): %s", description[:200])
        return "✅ *Ripoti yako imepokelewa. Asante!*\n\nWataalamu wataichunguza na kuchukua hatua zinazohitajika.\nEndelea kutuarifu hali unavyoiona."

    if text in ("help", "msaada", "hi", "hello", "halo", "habari", "start"):
        return (
            "🌍 *HALI — Mfumo wa Tahadhari za Mapema*\n\n"
            "Ninaweza kukusaidia na:\n\n"
            "• Andika *alerts* — tahadhari za hivi karibuni\n"
            "• Andika *report [maelezo]* — ripoti hatari\n"
            "• Mfano: _report mafuriko kwenye barabara kuu_\n\n"
            "Tumia USSD kwa simu yoyote bila intaneti."
        )

    return "Samahani, sijaelewa. Jaribu:\n• *alerts* — tahadhari za sasa\n• *report [maelezo]* — ripoti hatari\n• *help* — msaada zaidi"


async def _get_latest_alert() -> str:
    if db.pool is None:
        return "✅ Hakuna tahadhari za sasa kwa Afrika Mashariki.\nTutakujulisha mabadiliko yoyote."

    alerts = await AlertService(db.pool).list_alerts("sw", None, None, 1)
    if not alerts:
        return "✅ Hakuna tahadhari za sasa kwa Afrika Mashariki.\nTutakujulisha mabadiliko yoyote."

    alert = alerts[0]
    severity_emoji = {"red": "🔴", "orange": "🟠", "green": "🟢"}.get(alert["severity"], "⚠️")
    hazard_emoji = {"flood": "🌊", "drought": "☀️", "locust": "🦗", "cyclone": "🌀", "health": "🏥"}.get(alert["hazard_type"], "⚠️")
    countries = ", ".join(alert["affected_countries"] or [])
    valid_to = alert["valid_to"].strftime("%d %b %H:%M UTC") if alert["valid_to"] else "—"

    return (
        f"{severity_emoji} *TAHADHARI: {alert['headline']}*\n\n"
        f"{hazard_emoji} Aina: {alert['hazard_type'].upper()}\n"
        f"📍 Nchi: {countries}\n"
        f"⏰ Hadi: {valid_to}\n\n"
        f"{alert['body']}"
    )


# ── WhatsApp send helper ──────────────────────────────────────────────────────


async def _send_whatsapp_message(to: str, text: str) -> bool:
    if not settings.whatsapp_enabled:
        logger.warning("WhatsApp not configured — message not sent")
        return False

    url = f"{GRAPH_API_BASE}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            logger.info(f"WhatsApp message sent to {to[:6]}****")
            return True
    except httpx.HTTPStatusError as exc:
        logger.error(f"WhatsApp send failed: {exc.response.status_code} {exc.response.text}")
        return False
    except Exception as exc:
        logger.error(f"WhatsApp send error: {exc}")
        return False


# ── Signature verification ────────────────────────────────────────────────────


def _verify_signature(body: bytes, signature_header: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 header, keyed with the Meta App Secret
    (not the access token — those are different credentials)."""
    if not settings.whatsapp_app_secret:
        return True  # Dev mode — no app secret configured

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(settings.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
    received = signature_header[7:]

    return hmac.compare_digest(expected, received)
