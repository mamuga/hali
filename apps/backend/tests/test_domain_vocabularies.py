"""The domain vocabularies are defined in six places that must agree.

Languages, livelihoods and hazards each appear in the prompt library, the
processor's work lists, the scorer's lexicons, the Pydantic Literals that gate
the API, the ingestion enum, and a CHECK constraint in the database. A value
present in some but not all of them fails at a different layer depending on the
request — a 422 here, a CheckViolationError there, a silently unscored
translation somewhere else. These tests keep them in lockstep.
"""
import typing

import pytest

from hali.ai.processor import (
    LANGUAGES,
    LIVELIHOODS,
    PREGENERATED_CARD_LANGUAGES,
    PREGENERATED_CARD_LIVELIHOODS,
)
from hali.ai.prompts import (
    LANGUAGE_NAMES,
    LIVELIHOOD_CONTEXT,
    LOW_RESOURCE_LANGUAGES,
    NON_LATIN_SCRIPTS,
    script_requirement,
)
from hali.ai.scorer import ACTION_VERBS, HAZARD_KEYWORDS
from hali.ingestion.models import HazardType
from hali.ingestion.normaliser import GDACS_HAZARD_MAP
from hali.schemas import alert as schemas

EXPECTED_LANGUAGES = {"sw", "so", "am", "om", "ar", "en", "fr", "ti", "lg", "aa"}
EXPECTED_LIVELIHOODS = {
    "farmer",
    "pastoralist",
    "agropastoralist",
    "fisherfolk",
    "urban",
    "trader",
    "displaced",
}
EXPECTED_HAZARDS = {
    "flood",
    "drought",
    "locust",
    "cyclone",
    "heatwave",
    "landslide",
    "wildfire",
    "epidemic",
    "health",
    "other",
}


def _literal_values(annotation) -> set[str]:
    return set(typing.get_args(annotation))


class TestLanguages:
    def test_all_sources_agree(self):
        assert set(LANGUAGE_NAMES) == EXPECTED_LANGUAGES
        assert set(LANGUAGES) == EXPECTED_LANGUAGES
        assert _literal_values(schemas.Language) == EXPECTED_LANGUAGES

    @pytest.mark.parametrize("lang", sorted(EXPECTED_LANGUAGES))
    def test_scorer_has_a_lexicon(self, lang):
        """A missing lexicon silently zeroes 45% of the clarity rubric."""
        assert ACTION_VERBS.get(lang), f"no action verbs for {lang}"
        assert HAZARD_KEYWORDS.get(lang), f"no hazard keywords for {lang}"

    def test_low_resource_set_is_a_subset(self):
        assert LOW_RESOURCE_LANGUAGES <= EXPECTED_LANGUAGES
        assert "en" not in LOW_RESOURCE_LANGUAGES, "English is the fallback target"

    def test_english_is_present_as_the_fallback_target(self):
        assert "en" in LANGUAGES


class TestScriptEnforcement:
    @pytest.mark.parametrize("lang", ["am", "ti", "ar"])
    def test_non_latin_languages_get_a_script_instruction(self, lang):
        note = script_requirement(lang)
        assert note and "transliterate" in note.lower()

    @pytest.mark.parametrize("lang", ["sw", "en", "fr", "lg", "aa", "so", "om"])
    def test_latin_languages_get_no_instruction(self, lang):
        assert script_requirement(lang) == ""

    def test_tigrinya_is_pinned_to_geez_like_amharic(self):
        assert NON_LATIN_SCRIPTS["ti"] == NON_LATIN_SCRIPTS["am"]

    def test_unknown_language_does_not_raise(self):
        assert script_requirement("zz") == ""


class TestLivelihoods:
    def test_all_sources_agree(self):
        assert set(LIVELIHOOD_CONTEXT) == EXPECTED_LIVELIHOODS
        assert set(LIVELIHOODS) == EXPECTED_LIVELIHOODS
        assert _literal_values(schemas.Livelihood) == EXPECTED_LIVELIHOODS

    @pytest.mark.parametrize("livelihood", sorted(EXPECTED_LIVELIHOODS))
    def test_context_is_descriptive_enough_to_differentiate_advice(self, livelihood):
        context = LIVELIHOOD_CONTEXT[livelihood]
        assert len(context) > 40, f"{livelihood} context is too thin to steer the model"


class TestHazards:
    def test_all_sources_agree(self):
        assert {h.value for h in HazardType} == EXPECTED_HAZARDS
        assert _literal_values(schemas.HazardType) == EXPECTED_HAZARDS

    def test_gdacs_wildfire_and_landslide_are_no_longer_collapsed_to_other(self):
        assert GDACS_HAZARD_MAP["WF"] is HazardType.WILDFIRE
        assert GDACS_HAZARD_MAP["LS"] is HazardType.LANDSLIDE

    def test_every_gdacs_code_maps_to_a_real_hazard(self):
        for code, hazard in GDACS_HAZARD_MAP.items():
            assert hazard.value in EXPECTED_HAZARDS, code

    def test_epidemic_is_distinct_from_health(self):
        assert HazardType.EPIDEMIC != HazardType.HEALTH


class TestPregenerationBudget:
    def test_pregenerated_sets_are_subsets(self):
        assert set(PREGENERATED_CARD_LANGUAGES) <= set(LANGUAGES)
        assert set(PREGENERATED_CARD_LIVELIHOODS) <= set(LIVELIHOODS)

    def test_budget_stays_far_below_the_full_matrix(self):
        """70 cards per alert exhausts any free-tier quota; keep it bounded."""
        pregenerated = len(PREGENERATED_CARD_LANGUAGES) * len(PREGENERATED_CARD_LIVELIHOODS)
        assert pregenerated <= 15, f"{pregenerated} cards per alert is too many"

    def test_swahili_and_english_are_always_pregenerated(self):
        assert {"sw", "en"} <= set(PREGENERATED_CARD_LANGUAGES)
