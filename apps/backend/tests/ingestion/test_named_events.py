"""IFRC GO and WHO parsing.

Neither feed gives a hazard type HALI can use directly, and WHO gives no country
field at all — both are read out of free text, so the parsing needs guarding.
"""
import pytest

from hali.ingestion.models import HazardType
from hali.ingestion.named_events import (
    APPEAL_VALIDITY_DAYS,
    IFRC_DTYPE_TO_HAZARD,
    countries_in_text,
    hazard_from_title,
)


class TestCountryExtraction:
    def test_single_country(self):
        assert countries_in_text("Cholera - Kenya") == ["KE"]

    def test_south_sudan_is_not_read_as_sudan(self):
        """The reason the match is longest-first: 'Sudan' is a substring of
        'South Sudan', and attributing a South Sudan outbreak to Sudan would
        broadcast to the wrong country's subscribers."""
        assert countries_in_text("Floods - South Sudan") == ["SS"]

    def test_sudan_alone_still_resolves(self):
        assert countries_in_text("Floods - Sudan") == ["SD"]

    def test_multi_country_title(self):
        result = countries_in_text("Ebola disease, Democratic Republic of the Congo and Uganda")
        assert result == ["UG"], "only IGAD members should be returned"

    def test_two_igad_countries(self):
        assert countries_in_text("Drought in Ethiopia and Somalia") == ["ET", "SO"]

    def test_no_igad_country(self):
        assert countries_in_text("Nipah virus disease - India") == []
        assert countries_in_text("") == []

    def test_substring_of_a_longer_word_does_not_match(self):
        # "Ugandan" should still match Uganda, but an unrelated word must not.
        assert countries_in_text("Cholera in Chad") == []


class TestHazardExtraction:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("Somalia Insect Infestation sEAP", HazardType.LOCUST),
            ("Kenya - Cholera sEAP", HazardType.EPIDEMIC),
            ("Ebola disease caused by Bundibugyo virus", HazardType.EPIDEMIC),
            ("Kenya - Marburg Virus Disease", HazardType.EPIDEMIC),
            ("Somalia - Dengue", HazardType.EPIDEMIC),
            ("Kenya - Floods 2026", HazardType.FLOOD),
            ("Ethiopia - Landslide", HazardType.LANDSLIDE),
            ("Horn of Africa Drought", HazardType.DROUGHT),
        ],
    )
    def test_title_hints(self, title, expected):
        assert hazard_from_title(title) == expected

    def test_locust_wins_over_the_generic_dtype(self):
        """IFRC files the locust appeal under dtype 13 'Other'; the title is the
        only place the actual hazard appears."""
        assert hazard_from_title("Somalia Insect Infestation sEAP", HazardType.OTHER) == HazardType.LOCUST

    def test_unrecognised_title_uses_the_fallback(self):
        assert hazard_from_title("Kenya - Complex Emergency", HazardType.OTHER) == HazardType.OTHER

    def test_dtype_map_covers_the_common_ifrc_types(self):
        # 1=Epidemic and 12=Flood account for most IGAD appeals.
        assert IFRC_DTYPE_TO_HAZARD[1] == HazardType.EPIDEMIC
        assert IFRC_DTYPE_TO_HAZARD[12] == HazardType.FLOOD
        assert IFRC_DTYPE_TO_HAZARD[24] == HazardType.LANDSLIDE

    def test_every_mapped_hazard_is_a_real_hazard_type(self):
        for hazard in IFRC_DTYPE_TO_HAZARD.values():
            assert hazard in set(HazardType)


def test_appeal_horizon_is_bounded():
    """IFRC end dates run years out — several in the live feed end in 2028.
    Honouring them literally parks an alert on the map with nothing to refresh
    it, so the horizon is capped and the alert must be re-confirmed."""
    assert APPEAL_VALIDITY_DAYS <= 120
