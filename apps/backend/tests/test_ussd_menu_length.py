"""Every USSD page must fit the gateway's 182-character limit.

Africa's Talking truncates silently past that, so a menu that overflows loses
its last options with no error anywhere. Expanding to 10 languages, 7
livelihoods and 9 hazards took all three menus close enough to the limit that
this needs to be enforced rather than eyeballed.
"""
import pytest

from hali.routers import ussd


def _page(prefix: str, options: list[tuple[str, str]]) -> str:
    return f"CON {prefix}\n{ussd._numbered(options)}"


MENUS = [
    ("language", "Choose language", ussd.LANGUAGES),
    ("livelihood", "Your livelihood", ussd.LIVELIHOODS),
    ("hazard", "Choose hazard type", ussd.HAZARDS),
    ("country", "Where are you?", ussd.IGAD_COUNTRIES),
]


@pytest.mark.parametrize(("name", "prompt", "options"), MENUS, ids=[m[0] for m in MENUS])
def test_menu_fits_one_page(name, prompt, options):
    page = _page(prompt, options)
    assert len(page) <= ussd.USSD_MAX_CHARS, (
        f"{name} menu is {len(page)} chars, over the {ussd.USSD_MAX_CHARS} limit"
    )


@pytest.mark.parametrize(("name", "prompt", "options"), MENUS, ids=[m[0] for m in MENUS])
def test_menu_labels_are_gsm7_safe(name, prompt, options):
    """A non-ASCII character forces UCS-2, halving the usable page length."""
    for _, label in options:
        assert label.isascii(), f"{name} label {label!r} is not ASCII"


def test_page_helper_truncates_rather_than_overflowing():
    assert len(ussd._page("CON " + "x" * 500)) == ussd.USSD_MAX_CHARS


def test_truncation_marker_does_not_itself_force_ucs2():
    """Regression: the marker used to be "…", which is outside GSM-7.

    Trimming an all-ASCII page to 182 characters with a non-GSM-7 marker pushed
    the page into UCS-2, whose real limit is 80 — so "fitting" the page was what
    made the gateway cut it in half.
    """
    trimmed = ussd._page("END " + "a" * 500)
    assert ussd.GSM7_ALPHABET.issuperset(trimmed)
    assert len(trimmed) <= ussd.page_limit(trimmed)


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("amharic", "ቤተሰብዎን እና ልጆችን ጨምሮ ሁሉንም ከፍ ወዳለ እና ደህንነቱ የተጠበቀ ቦታ ያንቀሳቅሱ።" * 5),
        ("arabic", "فيضان قادم في إريتريا وإثيوبيا والسودان" * 5),
        ("tigrinya", "ኣብ ኤርትራ ከቢድ movements ጎርፍ ይመጽእ ኣሎ" * 5),
    ],
)
def test_non_gsm7_pages_are_clamped_to_the_ucs2_limit(name, body):
    """A translated alert gets 80 characters, not 182."""
    page = ussd._page(f"END {body}")
    assert len(page) <= ussd.USSD_MAX_CHARS_UCS2, (
        f"{name} page is {len(page)} chars, over the UCS-2 limit"
    )


def test_gsm7_page_still_gets_the_full_length():
    """The UCS-2 clamp must not penalise Latin-script content."""
    page = ussd._page("END " + "Move your animals to higher ground. " * 20)
    assert len(page) == ussd.USSD_MAX_CHARS


def test_short_pages_are_returned_untouched():
    for body in ("CON Welcome to HALI", "END ጎርፍ ይመጽእ ኣሎ"):
        assert ussd._page(body) == body


def test_every_menu_option_is_reachable_by_index():
    """_pick is 1-indexed; a 10-option menu must not need a two-digit entry
    that collides with the '1' prefix of another option."""
    for _, _, options in MENUS:
        for index, expected in enumerate(options, start=1):
            assert ussd._pick(options, str(index)) == expected
        assert ussd._pick(options, str(len(options) + 1)) is None
        assert ussd._pick(options, "0") is None


def test_alert_menu_keeps_its_options_when_the_headline_is_not_gsm7():
    """An Amharic headline must not push the livelihood options off the page.

    The options alone exceed the 80 characters a UCS-2 page allows, so a
    translated headline can never share this page with them; the caller would
    otherwise get a CON prompt with nothing selectable.
    """
    menu = f"Actions for:\n{ussd._numbered(ussd.LIVELIHOODS)}"
    page = ussd._con(f"RED FLOOD alert.\n{menu}")
    assert len(page) <= ussd.page_limit(page)
    # Every option survives intact.
    for index, (_, label) in enumerate(ussd.LIVELIHOODS, start=1):
        assert f"{index}. {label}" in page
