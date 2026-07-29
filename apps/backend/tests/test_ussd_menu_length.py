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


def test_every_menu_option_is_reachable_by_index():
    """_pick is 1-indexed; a 10-option menu must not need a two-digit entry
    that collides with the '1' prefix of another option."""
    for _, _, options in MENUS:
        for index, expected in enumerate(options, start=1):
            assert ussd._pick(options, str(index)) == expected
        assert ussd._pick(options, str(len(options) + 1)) is None
        assert ussd._pick(options, "0") is None
