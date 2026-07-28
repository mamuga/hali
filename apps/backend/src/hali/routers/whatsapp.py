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
from fastapi.responses import PlainTextResponse

from hali.config import settings
from hali.database import db
from hali.repositories.alerts import AlertRepository
from hali.repositories.reports import ReportRepository
from hali.repositories.subscriptions import SubscriptionRepository
from hali.services.alerts import AlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

GRAPH_API_BASE = "https://graph.facebook.com"
# Meta-approved template used for proactive (outside 24h window) alert messages.
ALERT_TEMPLATE_NAME = "hali_alert_v1"

IGAD_COUNTRIES = [
    ("KE", "Kenya"),
    ("ET", "Ethiopia"),
    ("SO", "Somalia"),
    ("UG", "Uganda"),
    ("DJ", "Djibouti"),
    ("ER", "Eritrea"),
    ("SD", "Sudan"),
    ("SS", "South Sudan"),
]
LIVELIHOODS = [("farmer", "Mkulima"), ("pastoralist", "Mfugaji"), ("fisherfolk", "Mvuvi"), ("urban", "Mjini")]


# ── Webhook verification (Meta handshake) ─────────────────────────────────────


@router.get("")
async def whatsapp_verify(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("WhatsApp webhook verified successfully")
        # Echo the challenge verbatim. Meta does not promise it is numeric, and
        # int() would 500 the handshake on anything else.
        return PlainTextResponse(hub_challenge)
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

    reply = await _handle_intent(from_number, text)
    if reply:
        await _send_whatsapp_message(from_number, reply)

    return {"status": "ok"}


# ── Intent routing ────────────────────────────────────────────────────────────


async def _handle_intent(from_number: str, text: str) -> str:
    # An opt-in conversation in progress consumes the reply, so "1" means
    # "Kenya" mid-flow rather than falling through to the unknown-command help.
    if db.pool is not None:
        pending = await _continue_subscribe_flow(from_number, text)
        if pending is not None:
            return pending

    if text in ("alerts", "tahadhari", "alert"):
        return await _get_latest_alert()

    if text in ("subscribe", "jiunge", "sajili"):
        return await _start_subscribe_flow(from_number)

    if text in ("stop", "acha", "unsubscribe", "sitisha"):
        return await _opt_out(from_number)

    if text.startswith("report ") or text.startswith("ripoti "):
        return await _save_report(from_number, text.split(" ", 1)[1].strip())

    if text in ("help", "msaada", "hi", "hello", "halo", "habari", "start"):
        return (
            "🌍 *HALI — Mfumo wa Tahadhari za Mapema*\n\n"
            "Ninaweza kukusaidia na:\n\n"
            "• Andika *alerts* — tahadhari za hivi karibuni\n"
            "• Andika *subscribe* — pokea tahadhari kwa simu yako\n"
            "• Andika *report [maelezo]* — ripoti hatari\n"
            "• Andika *stop* — acha kupokea tahadhari\n\n"
            "Tumia USSD kwa simu yoyote bila intaneti."
        )

    return "Samahani, sijaelewa. Jaribu:\n• *alerts* — tahadhari za sasa\n• *subscribe* — jiunge\n• *report [maelezo]* — ripoti hatari\n• *help* — msaada zaidi"


# ── Conversational opt-in (region → livelihood → confirm) ─────────────────────

STATE_COUNTRY = "await_country"
STATE_LIVELIHOOD = "await_livelihood"


async def _start_subscribe_flow(from_number: str) -> str:
    if db.pool is None:
        return "Samahani, huduma haipatikani kwa sasa. Jaribu tena baadaye."
    await SubscriptionRepository(db.pool).set_convo_state(from_number, STATE_COUNTRY, {})
    options = "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(IGAD_COUNTRIES, start=1))
    return f"Asante! Niambie eneo lako:\n{options}"


async def _continue_subscribe_flow(from_number: str, text: str) -> str | None:
    """Advance the opt-in flow. Returns None when no flow is in progress."""
    repo = SubscriptionRepository(db.pool)
    subscriber = await repo.get(from_number)
    state = (subscriber or {}).get("convo_state")
    if not state:
        return None

    # Let the user escape a half-finished flow.
    if text in ("stop", "acha", "cancel", "ghairi"):
        await repo.set_convo_state(from_number, None, {})
        return "Sawa, tumesitisha. Andika *subscribe* wakati wowote kuanza upya."

    data = dict((subscriber or {}).get("convo_data") or {})

    if state == STATE_COUNTRY:
        choice = _pick_index(text, len(IGAD_COUNTRIES))
        if choice is None:
            options = "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(IGAD_COUNTRIES, start=1))
            return f"Tafadhali chagua namba kati ya 1-{len(IGAD_COUNTRIES)}:\n{options}"
        data["iso2"] = IGAD_COUNTRIES[choice][0]
        await repo.set_convo_state(from_number, STATE_LIVELIHOOD, data)
        options = "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(LIVELIHOODS, start=1))
        return f"Maisha yako:\n{options}"

    if state == STATE_LIVELIHOOD:
        choice = _pick_index(text, len(LIVELIHOODS))
        if choice is None:
            options = "\n".join(f"{i}. {name}" for i, (_, name) in enumerate(LIVELIHOODS, start=1))
            return f"Tafadhali chagua namba kati ya 1-{len(LIVELIHOODS)}:\n{options}"
        livelihood = LIVELIHOODS[choice][0]
        iso2 = data.get("iso2")
        await repo.upsert(
            phone_number=from_number,
            channel="whatsapp",
            language="sw",
            livelihood=livelihood,
            preferred_iso2=iso2,
            opted_in_via="whatsapp",
        )
        await repo.set_convo_state(from_number, None, {})
        country = dict(IGAD_COUNTRIES).get(iso2, iso2)
        return f"✅ *Umesajiliwa!* Utapokea tahadhari za Orange na Red kwa {country} kwa Kiswahili.\n\nTuma *STOP* kuacha wakati wowote."

    # Unknown state — clear it rather than trapping the user.
    await repo.set_convo_state(from_number, None, {})
    return None


def _pick_index(text: str, count: int) -> int | None:
    stripped = text.strip()
    if not stripped.isdigit():
        return None
    index = int(stripped) - 1
    return index if 0 <= index < count else None


async def _opt_out(from_number: str) -> str:
    if db.pool is None:
        return "Samahani, huduma haipatikani kwa sasa."
    await SubscriptionRepository(db.pool).opt_out(from_number)
    return "Umeondolewa. Hutapokea tahadhari tena.\nAndika *subscribe* kujiunga tena wakati wowote."


async def _save_report(from_number: str, description: str) -> str:
    if len(description) < 5:
        return "Tafadhali eleza zaidi. Mfano: _report maji yamefika mtaa wangu_"
    if db.pool is None:
        return "Samahani, ripoti haikuhifadhiwa. Jaribu tena baadaye."

    # A WhatsApp text carries no coordinates, so the report is placed at the
    # subscriber's chosen country. Unsubscribed senders have no location at all,
    # and a report without a location cannot be stored.
    subscriber = await SubscriptionRepository(db.pool).get(from_number)
    iso2 = (subscriber or {}).get("preferred_iso2")
    lat, lng = (subscriber or {}).get("lat"), (subscriber or {}).get("lng")

    if lat is None or lng is None:
        if not iso2:
            return "Ili kuhifadhi ripoti yako, tuambie eneo lako kwanza. Andika *subscribe*."
        point = await AlertRepository(db.pool).country_point(iso2)
        if point is None:
            return "Samahani, ripoti haikuhifadhiwa. Jaribu tena baadaye."
        lat, lng = point

    try:
        await ReportRepository(db.pool).create_from_channel(
            hazard_type=_guess_hazard(description),
            description=description[:1000],
            lat=lat,
            lng=lng,
            channel="whatsapp",
            phone_number=from_number,
        )
    except Exception as exc:
        logger.error(f"WhatsApp report save failed: {exc}")
        return "Samahani, ripoti haikuhifadhiwa. Jaribu tena baadaye."

    return "✅ *Ripoti yako imepokelewa. Asante!*\n\nWataalamu wataichunguza na kuchukua hatua zinazohitajika."


def _guess_hazard(description: str) -> str:
    """Coarse keyword match. The AI classifier refines labels asynchronously."""
    lowered = description.lower()
    for hazard, keywords in HAZARD_KEYWORDS.items():
        if any(word in lowered for word in keywords):
            return hazard
    return "other"


HAZARD_KEYWORDS = {
    "flood": ("flood", "mafuriko", "maji", "rain", "mvua"),
    "drought": ("drought", "ukame", "dry", "kiangazi"),
    "locust": ("locust", "nzige"),
    "cyclone": ("cyclone", "storm", "kimbunga", "dhoruba"),
    "health": ("cholera", "disease", "ugonjwa", "kipindupindu", "outbreak"),
}


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

    return await _post_message(url, headers, payload, to)


async def send_alert_template(to: str, alert, headline: str, first_step: str, language: str) -> bool:
    """Send a proactive alert using the Meta-approved template.

    Free-form text only reaches a user inside the 24-hour customer service
    window. A broadcast is unsolicited, so it has to go through an approved
    template or Meta drops it.
    """
    if not settings.whatsapp_enabled:
        logger.warning("WhatsApp not configured — alert template not sent")
        return False

    url = f"{GRAPH_API_BASE}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": ALERT_TEMPLATE_NAME,
            "language": {"code": language},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": alert["hazard_type"]},
                        {"type": "text", "text": alert["severity"].upper()},
                        {"type": "text", "text": headline},
                        {"type": "text", "text": first_step or "Follow local guidance."},
                    ],
                }
            ],
        },
    }
    return await _post_message(url, headers, payload, to)


async def _post_message(url: str, headers: dict, payload: dict, to: str) -> bool:
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
        # Fail closed in production: an unset app secret there means anyone who
        # finds the URL can post fabricated messages. Only dev skips the check.
        if settings.is_production:
            logger.error("WHATSAPP_APP_SECRET is not set — rejecting webhook in production")
            return False
        return True

    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(settings.whatsapp_app_secret.encode(), body, hashlib.sha256).hexdigest()
    received = signature_header[7:]

    return hmac.compare_digest(expected, received)
