"""USSD menu tree tests.

The router is exercised through the real endpoint; db.pool is None in test mode,
so these cover navigation, the character limit, and graceful degradation when
the database is unavailable.
"""
from fastapi.testclient import TestClient

from hali.main import app
from hali.routers import ussd

client = TestClient(app)


def dial(text: str, phone: str = "+254700000000") -> str:
    response = client.post(
        "/ussd",
        data={"sessionId": "s1", "serviceCode": "*789#", "phoneNumber": phone, "text": text},
    )
    assert response.status_code == 200
    return response.text


def test_main_menu_lists_four_options():
    body = dial("")
    assert body.startswith("CON")
    for item in ("1. Latest alert", "2. Report hazard", "3. Get SMS alerts", "4. About HALI"):
        assert item in body


def test_about_terminates_session():
    assert dial("4").startswith("END")


def test_invalid_root_choice_is_rejected():
    assert dial("9").startswith("END Invalid choice")


def test_report_flow_asks_hazard_then_country():
    hazard_menu = dial("2")
    assert hazard_menu.startswith("CON")
    assert "Flood" in hazard_menu and "Locust" in hazard_menu

    country_menu = dial("2*1")
    assert country_menu.startswith("CON")
    assert "Kenya" in country_menu and "Ethiopia" in country_menu


def test_report_invalid_hazard_index_rejected():
    assert dial("2*99").startswith("END Invalid choice")


def test_subscribe_flow_walks_language_livelihood_country():
    lang_menu = dial("3")
    assert "Kiswahili" in lang_menu and "Somali" in lang_menu

    livelihood_menu = dial("3*1")
    assert "Farmer" in livelihood_menu and "Pastoralist" in livelihood_menu

    country_menu = dial("3*1*2")
    assert "Kenya" in country_menu


def test_subscribe_all_four_livelihoods_offered():
    """Spec requires fisherfolk and urban, which the old menu omitted."""
    menu = dial("3*1")
    for label in ("Farmer", "Pastoralist", "Fisherfolk", "Urban"):
        assert label in menu


def test_pages_never_exceed_gateway_limit():
    # AT rejects anything longer than 182 characters.
    for text in ("", "1", "2", "2*1", "3", "3*1", "3*1*2", "4", "9"):
        assert len(dial(text)) <= ussd.USSD_MAX_CHARS


def test_page_truncates_long_body():
    long_text = "x" * 500
    assert len(ussd._page(long_text)) == ussd.USSD_MAX_CHARS
    # ASCII marker: "…" is outside GSM-7 and would force the page into UCS-2,
    # where the real limit is 80 rather than 182.
    assert ussd._page(long_text).endswith(ussd.TRUNCATION_MARKER)


def test_degrades_when_database_unavailable():
    # db.pool is None in test mode; the caller must get a usable message.
    assert dial("1").startswith("END")
    assert dial("2*1*1").startswith("END")


def test_pick_bounds():
    options = [("a", "A"), ("b", "B")]
    assert ussd._pick(options, "1") == ("a", "A")
    assert ussd._pick(options, "2") == ("b", "B")
    assert ussd._pick(options, "3") is None
    assert ussd._pick(options, "0") is None
    assert ussd._pick(options, "x") is None
