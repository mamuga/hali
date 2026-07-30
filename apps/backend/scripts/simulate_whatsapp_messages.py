"""Send every message HALI produces to a test number, for demo rehearsal.

Templates are only required for *unsolicited* messages. Everything here is
free-form — plain text and interactive messages — so it needs no template
approval, but it only reaches a number whose 24-hour customer service window
is open (i.e. they have messaged the test number recently).

Copy and option lists are imported from the router rather than retyped, so a
change to the real flow shows up here instead of silently drifting.

Usage:
    poetry run python scripts/simulate_whatsapp_messages.py --to 2547XXXXXXXX
    poetry run python scripts/simulate_whatsapp_messages.py --to ... --dry-run
    poetry run python scripts/simulate_whatsapp_messages.py --to ... --only interactive
"""
from __future__ import annotations

import argparse
import asyncio
import json

import httpx

from hali.config import settings
from hali.routers.whatsapp import (
    IGAD_COUNTRIES,
    LIVELIHOODS,
    _alert_text,
)

# Meta caps reply buttons at 3 and button titles at 20 characters; anything
# longer is rejected outright rather than truncated.
BUTTON_TITLE_MAX = 20

DEMO_ALERT = {"hazard_type": "Flood", "severity": "red"}
DEMO_HEADLINE = "Severe flooding expected across northern Kenya."
DEMO_FIRST_STEP = "Move livestock to higher ground now."


def _url() -> str:
    return (
        f"https://graph.facebook.com/{settings.whatsapp_api_version}"
        f"/{settings.whatsapp_phone_number_id}/messages"
    )


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }


def text_payload(to: str, body: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": False},
    }


def list_payload(to: str, header: str, body: str, button: str, rows: list[dict]) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": header},
            "body": {"text": body},
            "action": {"button": button, "sections": [{"title": header, "rows": rows}]},
        },
    }


def buttons_payload(to: str, body: str, buttons: list[tuple[str, str]]) -> dict:
    for _, title in buttons:
        if len(title) > BUTTON_TITLE_MAX:
            raise ValueError(f"button title too long ({len(title)}): {title!r}")
    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": bid, "title": title}}
                    for bid, title in buttons
                ]
            },
        },
    }


def build_messages(to: str) -> list[tuple[str, str, dict]]:
    """Return (kind, label, payload) for every message in the demo script."""
    country_rows = [
        {"id": f"country_{iso2}", "title": name} for iso2, name in IGAD_COUNTRIES
    ]
    livelihood_rows = [
        {"id": f"livelihood_{key}", "title": name} for key, name in LIVELIHOODS
    ]
    country_text = "\n".join(f"{i}. {n}" for i, (_, n) in enumerate(IGAD_COUNTRIES, 1))
    livelihood_text = "\n".join(f"{i}. {n}" for i, (_, n) in enumerate(LIVELIHOODS, 1))

    return [
        # ── The conversational flow exactly as HALI sends it today ──
        ("text", "1. help / menu", text_payload(to,
            "🌍 *HALI — Mfumo wa Tahadhari za Mapema*\n\n"
            "Ninaweza kukusaidia na:\n\n"
            "• Andika *alerts* — tahadhari za hivi karibuni\n"
            "• Andika *subscribe* — pokea tahadhari kwa simu yako\n"
            "• Andika *report [maelezo]* — ripoti hatari\n"
            "• Andika *stop* — acha kupokea tahadhari\n\n"
            "Tumia USSD kwa simu yoyote bila intaneti.")),
        ("text", "2. subscribe -> country prompt", text_payload(to,
            f"Asante! Niambie eneo lako:\n{country_text}")),
        ("text", "3. country -> livelihood prompt", text_payload(to,
            f"Maisha yako:\n{livelihood_text}")),
        ("text", "4. subscription confirmed", text_payload(to,
            "✅ *Umesajiliwa!* Utapokea tahadhari za Orange na Red kwa Kenya "
            "kwa Kiswahili.\n\nTuma *STOP* kuacha wakati wowote.")),
        ("text", "5. opt-out", text_payload(to,
            "Umeondolewa. Hutapokea tahadhari tena.\n"
            "Andika *subscribe* kujiunga tena wakati wowote.")),
        ("text", "6. unknown command", text_payload(to,
            "Samahani, sijaelewa. Jaribu:\n• *alerts* — tahadhari za sasa\n"
            "• *subscribe* — jiunge\n• *report [maelezo]* — ripoti hatari\n"
            "• *help* — msaada zaidi")),

        # ── Broadcast payloads, via the text fallback ──
        ("text", "7. alert broadcast (template fallback)",
            text_payload(to, _alert_text(DEMO_ALERT, DEMO_HEADLINE, DEMO_FIRST_STEP))),
        ("text", "8. severity upgrade (template fallback)", text_payload(to,
            "Alert upgraded: Flooding in northern Kenya is now RED.\n"
            "Reason: 8 reports from your community.\n\n"
            f"First action: {DEMO_FIRST_STEP}\n\n"
            "Follow guidance from your local authorities.")),

        # ── Interactive equivalents (not yet wired into the router) ──
        ("interactive", "9. quick-action buttons", buttons_payload(to,
            "🌍 *HALI* — chagua kitendo:",
            [("act_alerts", "Tahadhari"),
             ("act_subscribe", "Jiunge"),
             ("act_report", "Ripoti hatari")])),
        ("interactive", "10. country list picker", list_payload(to,
            "Eneo lako", "Asante! Niambie eneo lako:", "Chagua nchi", country_rows)),
        ("interactive", "11. livelihood list picker", list_payload(to,
            "Maisha yako", "Unafanya kazi gani?", "Chagua", livelihood_rows)),
        ("interactive", "12. confirm buttons", buttons_payload(to,
            "Umechagua *Kenya* na *Mfugaji*. Ni sahihi?",
            [("confirm_yes", "Ndiyo, sajili"), ("confirm_no", "Hapana, badilisha")])),
    ]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--to", required=True, help="recipient, E.164 without '+'")
    parser.add_argument("--dry-run", action="store_true", help="print payloads, send nothing")
    parser.add_argument("--only", choices=["text", "interactive"], help="send one kind only")
    parser.add_argument("--delay", type=float, default=1.5, help="seconds between sends")
    args = parser.parse_args()

    if not settings.whatsapp_enabled:
        raise SystemExit("WhatsApp not configured — set WHATSAPP_TOKEN and PHONE_NUMBER_ID.")

    messages = build_messages(args.to)
    if args.only:
        messages = [m for m in messages if m[0] == args.only]

    if args.dry_run:
        for kind, label, payload in messages:
            print(f"\n── {label}  [{kind}] ──")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\n{len(messages)} message(s) — dry run, nothing sent.")
        return

    ok = failed = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for kind, label, payload in messages:
            resp = await client.post(_url(), json=payload, headers=_headers())
            if resp.status_code < 400:
                ok += 1
                print(f"  ✅ {label}")
            else:
                failed += 1
                err = resp.json().get("error", {})
                print(f"  ❌ {label}: {err.get('code')} {err.get('message')}")
            await asyncio.sleep(args.delay)

    print(f"\n{ok} sent, {failed} failed.")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
