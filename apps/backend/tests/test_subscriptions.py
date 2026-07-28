"""Subscriber normalisation, broadcast fan-out, and WhatsApp security tests."""
from datetime import UTC, datetime, timedelta

import pytest

from hali.config import settings
from hali.repositories.subscriptions import normalise_phone
from hali.routers import whatsapp
from hali.services import broadcast, sms

# ── Phone normalisation ───────────────────────────────────────────────────────


def test_normalise_phone_unifies_channel_formats():
    # AT sends +254..., the WhatsApp Cloud API sends 254... — the same person
    # must not end up with two subscriptions and two messages.
    assert normalise_phone("+254700000000") == "+254700000000"
    assert normalise_phone("254700000000") == "+254700000000"
    assert normalise_phone("+254 700 000 000") == "+254700000000"
    assert normalise_phone("+254-700-000-000") == "+254700000000"
    assert normalise_phone("") == ""


# ── SMS helpers ───────────────────────────────────────────────────────────────


def test_truncate_keeps_one_sms_segment():
    assert sms.truncate("short") == "short"
    long_message = "a" * 300
    assert len(sms.truncate(long_message)) == sms.SMS_MAX_LENGTH
    assert sms.truncate(long_message).endswith("…")


def test_mask_hides_subscriber_number():
    assert sms._mask("+254700000000") == "+25470****"
    assert "000000" not in sms._mask("+254700000000")


# ── Broadcast ─────────────────────────────────────────────────────────────────


def test_first_step_strips_list_markers():
    assert broadcast._first_step("1. Move livestock to higher ground\n2. Store water") == "Move livestock to higher ground"
    assert broadcast._first_step("- Clear drainage") == "Clear drainage"
    assert broadcast._first_step("• Evacuate early") == "Evacuate early"
    assert broadcast._first_step("\n\nFirst real line") == "First real line"
    assert broadcast._first_step("") == ""


class FakeConn:
    def __init__(self, alert, claim=True):
        self._alert = alert
        self._claim = claim
        self.updates = 0

    async def fetchrow(self, sql, *args):
        return self._alert

    async def fetchval(self, sql, *args):
        self.updates += 1
        return "claimed" if self._claim else None

    async def fetch(self, sql, *args):
        return []


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Ctx(self._conn)


class _Ctx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


def _alert(severity="red", hours_ahead=24, broadcast_at=None):
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "hazard_type": "flood",
        "severity": severity,
        "affected_countries": ["KE"],
        "valid_to": datetime.now(UTC) + timedelta(hours=hours_ahead),
        "broadcast_at": broadcast_at,
    }


async def test_green_alerts_are_not_broadcast():
    pool = FakePool(FakeConn(_alert(severity="green")))
    result = await broadcast.broadcast_alert("id", pool)
    assert result["status"] == "skipped_low_severity"
    assert result["sent"] == 0


async def test_expired_alerts_are_not_broadcast():
    pool = FakePool(FakeConn(_alert(hours_ahead=-1)))
    result = await broadcast.broadcast_alert("id", pool)
    assert result["status"] == "skipped_expired"


async def test_already_broadcast_alert_is_not_resent():
    # Re-running the AI backlog must not re-send SMS people already received.
    conn = FakeConn(_alert(), claim=False)
    result = await broadcast.broadcast_alert("id", FakePool(conn))
    assert result["status"] == "already_broadcast"
    assert result["sent"] == 0


async def test_missing_alert_is_handled():
    pool = FakePool(FakeConn(None))
    assert (await broadcast.broadcast_alert("id", pool))["status"] == "alert_not_found"


# ── WhatsApp signature verification ───────────────────────────────────────────


def test_signature_fails_closed_in_production(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    monkeypatch.setattr(settings, "environment", "production")
    # No app secret in production means anyone who finds the URL could post
    # fabricated alerts, so the webhook must reject rather than trust.
    assert whatsapp._verify_signature(b"{}", "") is False


def test_signature_permitted_in_development(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_app_secret", "")
    monkeypatch.setattr(settings, "environment", "development")
    assert whatsapp._verify_signature(b"{}", "") is True


def test_signature_validates_when_secret_configured(monkeypatch):
    import hashlib
    import hmac

    monkeypatch.setattr(settings, "whatsapp_app_secret", "s3cret")
    body = b'{"hello":"world"}'
    good = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()

    assert whatsapp._verify_signature(body, f"sha256={good}") is True
    assert whatsapp._verify_signature(body, f"sha256={'0' * 64}") is False
    assert whatsapp._verify_signature(body, good) is False  # missing prefix


def test_hub_challenge_echoes_non_numeric(monkeypatch):
    """Meta does not promise a numeric challenge; int() would 500 the handshake."""
    from fastapi.testclient import TestClient

    from hali.main import app

    monkeypatch.setattr(settings, "whatsapp_verify_token", "tok")
    client = TestClient(app)
    response = client.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "abc123"})
    assert response.status_code == 200
    assert response.text.strip('"') == "abc123"


def test_hub_challenge_rejects_wrong_token(monkeypatch):
    from fastapi.testclient import TestClient

    from hali.main import app

    monkeypatch.setattr(settings, "whatsapp_verify_token", "tok")
    client = TestClient(app)
    response = client.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"})
    assert response.status_code == 403


# ── WhatsApp intent helpers ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("maji yamefika mtaa wangu", "flood"),
        ("there is a flood on the road", "flood"),
        ("ukame mbaya hapa", "drought"),
        ("nzige wamevamia shamba", "locust"),
        ("cholera outbreak in the camp", "health"),
        ("something odd happened", "other"),
    ],
)
def test_hazard_keyword_guess(text, expected):
    assert whatsapp._guess_hazard(text) == expected


def test_pick_index_bounds():
    assert whatsapp._pick_index("1", 8) == 0
    assert whatsapp._pick_index("8", 8) == 7
    assert whatsapp._pick_index("9", 8) is None
    assert whatsapp._pick_index("0", 8) is None
    assert whatsapp._pick_index("abc", 8) is None
