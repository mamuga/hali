"""Test context enricher."""
from datetime import datetime, timezone

from hali.ai.context import get_dominant_livelihood, get_season


def test_april_is_long_rains():
    assert get_season(datetime(2026, 4, 15, tzinfo=timezone.utc)) == "long_rains"


def test_january_is_dry():
    assert get_season(datetime(2026, 1, 10, tzinfo=timezone.utc)) == "dry"


def test_november_is_short_rains():
    assert get_season(datetime(2026, 11, 5, tzinfo=timezone.utc)) == "short_rains"


def test_somalia_is_pastoralist():
    assert get_dominant_livelihood(["SO"]) == "pastoralist"


def test_kenya_is_farmer():
    assert get_dominant_livelihood(["KE"]) == "farmer"


def test_empty_countries_falls_back():
    assert get_dominant_livelihood([]) == "farmer"


def test_unknown_country_falls_back():
    assert get_dominant_livelihood(["XX", "ZZ"]) == "farmer"
