"""Test prompt generation functions."""
from hali.ai.prompts import (
    action_card_user_prompt,
    report_label_user_prompt,
    severity_assessment_user_prompt,
    translation_system_prompt,
    translation_user_prompt,
)


def test_translation_system_has_grade5():
    system = translation_system_prompt()
    assert "Grade 5" in system
    assert "JSON" in system


def test_translation_user_includes_context():
    user = translation_user_prompt(
        hazard_type="flood",
        severity="red",
        countries=["KE", "ET"],
        valid_from="2026-07-01",
        valid_to="2026-07-04",
        language_code="sw",
        season="long_rains",
        livelihood_hint="pastoralist",
    )
    assert "Kiswahili" in user
    assert "flood" in user
    assert "saturated" in user


def test_action_card_has_livelihood():
    user = action_card_user_prompt("flood", "red", ["KE"], "pastoralist", "long_rains")
    assert "pastoralist" in user.lower()
    assert "48" in user


def test_severity_assessment_includes_reports():
    user = severity_assessment_user_prompt("orange", "flood", 5, ["Roads flooded", "Village submerged"])
    assert "Roads flooded" in user
    assert "5" in user


def test_report_label_includes_description():
    user = report_label_user_prompt("Water is up to my knees on the main road", "flood")
    assert "Water is up to my knees" in user
