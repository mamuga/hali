"""Africa's Talking USSD gateway.

Zero registration, any handset, no internet. The whole session state lives in
the `text` field AT sends back (`1*2*3`), so nothing is stored between requests.

Menu tree:
    ""          main menu
    1           latest alert for the caller's area
      1*N       action steps for livelihood N
    2           report a hazard
      2*N       hazard N chosen -> pick country
      2*N*M     report stored, END
    3           subscribe to SMS alerts
      3*L       language L chosen -> pick livelihood
      3*L*V     livelihood V chosen -> pick country
      3*L*V*M   subscription stored, END
    4           about HALI

Two hard constraints from the AT gateway: a page may not exceed 182 GSM-7
characters (only 80 once any character forces the page into UCS-2, which every
non-Latin translation does), and the session is killed at 3 seconds. Every
database call is therefore given a 2-second budget with a static fallback.
"""
from __future__ import annotations

import asyncio
import time
from contextvars import ContextVar

import structlog
from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

from hali.database import db
from hali.repositories.alerts import AlertRepository
from hali.repositories.subscriptions import SubscriptionRepository, normalise_phone
from hali.services.reports import ReportService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ussd"])

# A USSD page carries 160 octets. GSM-7 packs seven bits per character, so 182
# of them fit. A single character outside the GSM-7 alphabet forces the *whole*
# page into UCS-2 at two octets per character, and only 80 then fit — so the
# usable length depends on the content, not just on the channel.
USSD_MAX_CHARS = 182
USSD_MAX_CHARS_UCS2 = 80

# GSM 03.38: the basic table plus the characters reachable through the escape
# table. Anything not in here forces UCS-2.
GSM7_ALPHABET = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅå"
    "Δ_ΦΓΛΩΠΨΣΘΞÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "^{}\\[~]|€"
)

# Deliberately ASCII. A "…" here would itself be the character that forces the
# page into UCS-2, so the act of trimming a page to fit would halve the space
# available to it — the failure this constant exists to prevent.
TRUNCATION_MARKER = "..."
# AT terminates the session at 3s. The budget below covers ALL database work in
# one request, not each call: a handler makes up to three sequential queries, so
# a per-call timeout would allow 3x the budget and blow the session anyway.
USSD_BUDGET_SECONDS = 2.5
# Below this there is no point starting another round trip.
MIN_CALL_SECONDS = 0.1

_deadline: ContextVar[float] = ContextVar("ussd_deadline", default=0.0)

IGAD_COUNTRIES = [
    ("KE", "Kenya"),
    ("ET", "Ethiopia"),
    ("SO", "Somalia"),
    ("UG", "Uganda"),
    ("DJ", "Djibouti"),
    ("ER", "Eritrea"),
    ("SD", "Sudan"),
    ("SS", "S.Sudan"),
]
# Labels stay ASCII: USSD gateways encode in GSM-7, and an accented character
# silently forces UCS-2, which halves the usable page length. "Francais" rather
# than "Français" is deliberate. All three menus were measured against
# USSD_MAX_CHARS with the full option list — see tests/test_ussd_menu_length.py.
LANGUAGES = [
    ("sw", "Kiswahili"),
    ("so", "Somali"),
    ("am", "Amharic"),
    ("om", "Oromo"),
    ("ar", "Arabic"),
    ("en", "English"),
    ("fr", "Francais"),
    ("ti", "Tigrinya"),
    ("lg", "Luganda"),
    ("aa", "Afar"),
]
LIVELIHOODS = [
    ("farmer", "Farmer"),
    ("pastoralist", "Pastoralist"),
    ("agropastoralist", "Agro-pastoralist"),
    ("fisherfolk", "Fisherfolk"),
    ("urban", "Urban"),
    ("trader", "Trader"),
    ("displaced", "Displaced"),
]
HAZARDS = [
    ("flood", "Flood"),
    ("drought", "Drought"),
    ("locust", "Locust"),
    ("cyclone", "Cyclone"),
    ("heatwave", "Heatwave"),
    ("landslide", "Landslide"),
    ("wildfire", "Wildfire"),
    ("epidemic", "Epidemic"),
    ("other", "Other"),
]

# Fallback interior points, used only if the countries table is unreachable
# within the timeout budget. USSD carries no GPS, so a country-level point is
# the best resolution available on this channel either way.
COUNTRY_FALLBACK_POINT = {
    "KE": (0.02, 37.90),
    "ET": (9.15, 40.50),
    "SO": (5.15, 46.20),
    "UG": (1.37, 32.29),
    "DJ": (11.75, 42.60),
    "ER": (15.18, 39.05),
    "SD": (15.50, 30.22),
    "SS": (7.31, 30.32),
}


def page_limit(text: str) -> int:
    """How many characters this particular page may hold.

    Translated alerts (Amharic, Arabic, Tigrinya) are outside GSM-7 and so get
    less than half the room a Latin-script page gets.
    """
    if GSM7_ALPHABET.issuperset(text):
        return USSD_MAX_CHARS
    return USSD_MAX_CHARS_UCS2


def _page(text: str) -> str:
    """Clamp a response to the gateway's per-page character limit.

    The limit is measured against the untrimmed text: dropping the tail of a
    UCS-2 page may leave only GSM-7 characters behind, and re-deriving a longer
    limit from that would let the page grow back past what the gateway accepts.
    """
    limit = page_limit(text)
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER


def _con(body: str) -> str:
    return _page(f"CON {body}")


def _end(body: str) -> str:
    return _page(f"END {body}")


def _numbered(options: list[tuple[str, str]]) -> str:
    return "\n".join(f"{i}. {label}" for i, (_, label) in enumerate(options, start=1))


def _pick(options: list[tuple[str, str]], choice: str) -> tuple[str, str] | None:
    if not choice.isdigit():
        return None
    index = int(choice) - 1
    return options[index] if 0 <= index < len(options) else None


async def _guarded(coro, fallback):
    """Run a DB coroutine inside whatever remains of the request's budget.

    A slow query must degrade to a usable message rather than hang and drop
    the caller.
    """
    remaining = _deadline.get() - time.monotonic()
    if remaining < MIN_CALL_SECONDS:
        coro.close()  # never awaited, so close it explicitly
        logger.warning("ussd.budget_exhausted")
        return fallback
    try:
        return await asyncio.wait_for(coro, timeout=remaining)
    except TimeoutError:
        logger.warning("ussd.db_timeout", remaining_ms=round(remaining * 1000))
        return fallback
    except Exception as exc:
        logger.error("ussd.db_error", error=str(exc))
        return fallback


@router.post("/ussd", response_class=PlainTextResponse)
async def ussd(
    sessionId: str = Form(""),
    serviceCode: str = Form(""),
    phoneNumber: str = Form(""),
    text: str = Form(""),
) -> str:
    _deadline.set(time.monotonic() + USSD_BUDGET_SECONDS)
    parts = text.split("*") if text else []

    # Normalise on read as well as on write: a subscriber stored as
    # +254700000000 must still be found when the gateway presents the number in
    # any other formatting, otherwise they silently get the anonymous default.
    phone = normalise_phone(phoneNumber)

    if not parts:
        return _con("Welcome to HALI\n1. Latest alert\n2. Report hazard\n3. Get SMS alerts\n4. About HALI")

    root = parts[0]
    if root == "1":
        return await _handle_alert(phone, parts)
    if root == "2":
        return await _handle_report(phone, parts)
    if root == "3":
        return await _handle_subscribe(phone, parts)
    if root == "4":
        return _end("HALI turns satellite and community warnings into local action for East African communities.")
    return _end("Invalid choice. Dial again to start over.")


# ── 1. Latest alert ───────────────────────────────────────────────────────────


async def _handle_alert(phone: str, parts: list[str]) -> str:
    if db.pool is None:
        return _end("Alerts unavailable right now. Please try again shortly.")

    livelihood = None
    if len(parts) > 1:
        chosen = _pick(LIVELIHOODS, parts[1])
        if chosen is None:
            return _end("Invalid choice. Dial again to start over.")
        livelihood = chosen[0]

    # Subscriber, alert and action card in one round trip — see ussd_alert_view.
    view = await _guarded(AlertRepository(db.pool).ussd_alert_view(phone, livelihood), None)
    if view is None:
        return _end("No active alerts for your area right now. Dial again later.")

    if livelihood is None:
        summary = f"{view['severity'].upper()} {view['hazard_type'].upper()}: {view['headline']}"
        return _con(f"{summary}\nActions for:\n{_numbered(LIVELIHOODS)}")

    if not view.get("steps"):
        return _end(f"{view['severity'].upper()} {view['hazard_type']}: follow local guidance and move to safety early.")
    return _end(view["steps"])


# ── 2. Report a hazard ────────────────────────────────────────────────────────


async def _handle_report(phone: str, parts: list[str]) -> str:
    if len(parts) == 1:
        return _con(f"Choose hazard type\n{_numbered(HAZARDS)}")

    hazard = _pick(HAZARDS, parts[1])
    if hazard is None:
        return _end("Invalid choice. Dial again to start over.")

    if len(parts) == 2:
        return _con(f"Where are you?\n{_numbered(IGAD_COUNTRIES)}")

    country = _pick(IGAD_COUNTRIES, parts[2])
    if country is None:
        return _end("Invalid choice. Dial again to start over.")

    if db.pool is None:
        return _end("Report could not be saved. Please try again shortly.")

    iso2, country_name = country
    hazard_type, hazard_label = hazard
    point = await _resolve_country_point(iso2)
    lat, lng = point

    saved = await _guarded(
        ReportService(db.pool).create_from_channel(
            hazard_type=hazard_type,
            description=f"{hazard_label} reported via USSD from {country_name}",
            lat=lat,
            lng=lng,
            channel="ussd",
            phone_number=phone,
            location_precision="country",
        ),
        None,
    )
    if saved is None:
        return _end("Report could not be saved. Please try again shortly.")

    logger.info("ussd.report_saved", hazard=hazard_type, iso2=iso2)
    return _end(f"{hazard_label} report received for {country_name}. Thank you - HALI will verify it.")


async def _resolve_country_point(iso2: str) -> tuple[float, float]:
    fallback = COUNTRY_FALLBACK_POINT.get(iso2, (0.0, 38.0))
    if db.pool is None:
        return fallback
    point = await _guarded(AlertRepository(db.pool).country_point(iso2), None)
    return point or fallback


# ── 3. Subscribe to SMS alerts ────────────────────────────────────────────────


async def _handle_subscribe(phone: str, parts: list[str]) -> str:
    if len(parts) == 1:
        return _con(f"Choose language\n{_numbered(LANGUAGES)}")

    language = _pick(LANGUAGES, parts[1])
    if language is None:
        return _end("Invalid choice. Dial again to start over.")

    if len(parts) == 2:
        return _con(f"Your livelihood\n{_numbered(LIVELIHOODS)}")

    livelihood = _pick(LIVELIHOODS, parts[2])
    if livelihood is None:
        return _end("Invalid choice. Dial again to start over.")

    if len(parts) == 3:
        return _con(f"Your country\n{_numbered(IGAD_COUNTRIES)}")

    country = _pick(IGAD_COUNTRIES, parts[3])
    if country is None:
        return _end("Invalid choice. Dial again to start over.")

    if not phone:
        return _end("Could not read your number. Please try again.")
    if db.pool is None:
        return _end("Subscription unavailable right now. Please try again shortly.")

    saved = await _guarded(
        SubscriptionRepository(db.pool).upsert(
            phone_number=phone,
            channel="sms",
            language=language[0],
            livelihood=livelihood[0],
            preferred_iso2=country[0],
            opted_in_via="ussd",
        ),
        None,
    )
    if saved is None:
        return _end("Subscription failed. Please try again shortly.")

    logger.info("ussd.subscribed", iso2=country[0], language=language[0], livelihood=livelihood[0])
    return _end(f"Subscribed. You will get Orange and Red alerts for {country[1]} in {language[1]}. Reply STOP anytime to cancel.")
