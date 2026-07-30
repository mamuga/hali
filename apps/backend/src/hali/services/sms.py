"""SMS delivery via Africa's Talking.

The africastalking SDK is synchronous, so every call is pushed to a worker
thread to keep the event loop free during broadcast fan-out.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from hali.config import settings

logger = structlog.get_logger(__name__)

# A single SMS segment is 160 GSM-7 characters; staying inside one segment keeps
# cost predictable when broadcasting to a large subscriber list. A character
# outside GSM-7 forces the message into UCS-2, where a segment holds only 70 —
# so a 160-character body then costs three segments, not one.
SMS_MAX_LENGTH = 160

# Deliberately ASCII, for the reason above: a "…" here would be the single
# character that tips an otherwise GSM-7 message into UCS-2, tripling the cost
# of the broadcast this limit exists to contain.
TRUNCATION_MARKER = "..."

_sms_client: Any = None


def _get_client() -> Any:
    """Initialise the AT SDK once, lazily."""
    global _sms_client
    if _sms_client is not None:
        return _sms_client
    import africastalking

    africastalking.initialize(settings.africastalking_username, settings.africastalking_api_key)
    _sms_client = africastalking.SMS
    return _sms_client


def truncate(text: str, limit: int = SMS_MAX_LENGTH) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER


async def send_sms(phone_number: str, message: str) -> bool:
    """Send one SMS. Returns False rather than raising so fan-out continues."""
    if not settings.sms_enabled:
        logger.warning("sms.not_configured", to=_mask(phone_number))
        return False

    body = truncate(message)
    try:
        client = _get_client()
        response = await asyncio.to_thread(client.send, body, [phone_number])
    except Exception as exc:
        logger.error("sms.send_failed", to=_mask(phone_number), error=str(exc))
        return False

    recipients = (response or {}).get("SMSMessageData", {}).get("Recipients", [])
    # AT reports per-recipient status; 101 = Sent, 100 = Processed, 102 = Queued.
    ok = bool(recipients) and str(recipients[0].get("statusCode")) in {"100", "101", "102"}
    if ok:
        logger.info("sms.sent", to=_mask(phone_number), length=len(body))
    else:
        logger.error("sms.rejected", to=_mask(phone_number), response=str(response)[:300])
    return ok


def _mask(phone_number: str) -> str:
    """Never log a full subscriber number."""
    return f"{phone_number[:6]}****" if len(phone_number) > 6 else "****"
