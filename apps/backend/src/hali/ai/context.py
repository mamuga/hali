"""
Context enricher - derives additional context from an alert's timestamp
and affected countries to make translations more specific.

Derives:
  - season: long_rains | short_rains | dry
  - dominant_livelihood: majority livelihood in the affected countries
"""
from __future__ import annotations

from datetime import UTC, datetime

# Simplified East Africa seasonal calendar: month -> season name.
SEASONAL_CALENDAR: dict[int, str] = {
    1: "dry",
    2: "dry",
    3: "long_rains",
    4: "long_rains",
    5: "long_rains",
    6: "dry",
    7: "dry",
    8: "dry",
    9: "dry",
    10: "short_rains",
    11: "short_rains",
    12: "short_rains",
}

# Dominant livelihood by IGAD country ISO2.
COUNTRY_LIVELIHOOD: dict[str, str] = {
    "KE": "farmer",       # Mix - default to farmer
    "ET": "pastoralist",  # Large pastoral regions
    "SO": "pastoralist",  # Predominantly pastoral
    "UG": "farmer",
    "DJ": "pastoralist",
    "ER": "farmer",
    "SD": "farmer",
    "SS": "pastoralist",
}


def get_season(dt: datetime | None) -> str:
    """Return the East Africa season for a given datetime."""
    if dt is None:
        dt = datetime.now(UTC)
    return SEASONAL_CALENDAR.get(dt.month, "dry")


def get_dominant_livelihood(countries: list[str]) -> str:
    """Return the dominant livelihood for the first recognised country.

    Falls back to 'farmer' if no mapping is found.
    """
    for iso2 in countries:
        if iso2.upper() in COUNTRY_LIVELIHOOD:
            return COUNTRY_LIVELIHOOD[iso2.upper()]
    return "farmer"
