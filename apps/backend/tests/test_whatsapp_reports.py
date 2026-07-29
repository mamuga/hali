"""WhatsApp report intake: location fallback and precision tagging.

A WhatsApp text carries no coordinates. These cover the fallback chain that
decides where the report is stored, and the precision tag that keeps a
country-level point out of the hotspot clustering.
"""
import pytest

from hali.routers import whatsapp


class TestIso2FromPhone:
    @pytest.mark.parametrize(
        ("number", "expected"),
        [
            ("254722000222", "KE"),
            ("+254722000222", "KE"),
            ("251911000000", "ET"),
            ("252612000000", "SO"),
            ("256772000000", "UG"),
            ("253770000000", "DJ"),
            ("291710000000", "ER"),
            ("249912000000", "SD"),
            ("211920000000", "SS"),
        ],
    )
    def test_maps_igad_dialling_codes(self, number, expected):
        assert whatsapp._iso2_from_phone(number) == expected

    @pytest.mark.parametrize("number", ["", None, "447700900000", "12025550100"])
    def test_returns_none_outside_igad(self, number):
        assert whatsapp._iso2_from_phone(number) is None

    def test_south_sudan_is_not_shadowed_by_a_shorter_prefix(self):
        """211 must win even though other codes share leading digits."""
        assert whatsapp._iso2_from_phone("211920000000") == "SS"


class FakeSubscriptionRepo:
    def __init__(self, subscriber):
        self._subscriber = subscriber

    async def get(self, phone):
        return self._subscriber


class FakeReportService:
    def __init__(self, pool):
        self.calls: list[dict] = []

    async def create_from_channel(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "00000000-0000-0000-0000-000000000001"}


@pytest.fixture
def patched(monkeypatch):
    """Wire the router to fakes and hand back the report service that recorded calls."""
    service = FakeReportService(None)
    monkeypatch.setattr(whatsapp.db, "pool", object(), raising=False)
    monkeypatch.setattr(whatsapp, "ReportService", lambda pool: service)
    return service


async def test_non_subscriber_report_is_stored_via_dialling_code(monkeypatch, patched):
    """The original behaviour dropped these reports entirely."""
    monkeypatch.setattr(whatsapp, "SubscriptionRepository", lambda pool: FakeSubscriptionRepo(None))

    class FakeAlertRepo:
        def __init__(self, pool):
            pass

        async def country_point(self, iso2):
            assert iso2 == "KE"
            return (0.02, 37.90)

    monkeypatch.setattr(whatsapp, "AlertRepository", FakeAlertRepo)

    reply = await whatsapp._save_report("254722000222", "mafuriko kwenye daraja")

    assert len(patched.calls) == 1
    call = patched.calls[0]
    assert call["channel"] == "whatsapp"
    assert call["location_precision"] == "country"
    assert (call["lat"], call["lng"]) == (0.02, 37.90)
    assert "imepokelewa" in reply


async def test_subscriber_gps_point_wins_and_is_tagged_gps(monkeypatch, patched):
    subscriber = {"preferred_iso2": "KE", "lat": 3.1191, "lng": 35.5973}
    monkeypatch.setattr(
        whatsapp, "SubscriptionRepository", lambda pool: FakeSubscriptionRepo(subscriber)
    )

    await whatsapp._save_report("254722000222", "maji yamefika nyumbani")

    call = patched.calls[0]
    assert call["location_precision"] == "gps"
    assert (call["lat"], call["lng"]) == (3.1191, 35.5973)


async def test_unlocatable_sender_is_asked_to_subscribe(monkeypatch, patched):
    """A number outside IGAD has no country to fall back to."""
    monkeypatch.setattr(whatsapp, "SubscriptionRepository", lambda pool: FakeSubscriptionRepo(None))

    reply = await whatsapp._save_report("447700900000", "flooding here")

    assert patched.calls == []
    assert "subscribe" in reply.lower()


async def test_short_description_is_rejected_before_any_lookup(patched):
    reply = await whatsapp._save_report("254722000222", "maji")

    assert patched.calls == []
    assert "eleza zaidi" in reply
