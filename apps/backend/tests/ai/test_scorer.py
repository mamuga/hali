"""Test humanitarian clarity scorer."""
from hali.ai.models import ModelProvider, TranslationOutput
from hali.ai.scorer import score_translation


def make_output(headline: str, body: str, lang: str = "sw") -> TranslationOutput:
    return TranslationOutput(
        provider=ModelProvider.CLAUDE,
        model_name="test",
        language=lang,
        headline=headline,
        body=body,
    )


def test_empty_output_scores_zero():
    out = make_output("", "")
    assert score_translation(out) == 0.0


def test_good_swahili_alert_scores_higher_than_bad():
    good = make_output(
        headline="Mafuriko makubwa yanakuja kesho. Hamia sasa.",
        body="Mafuriko makubwa yanatarajiwa Pwani kesho asubuhi. Hamia mifugo kwenda maeneo ya juu. Epuka maeneo ya chini ya mto. Wasiliana na majirani.",
    )
    bad = make_output(headline="Alert", body="There is an alert.")
    assert score_translation(good) > score_translation(bad)


def test_long_headline_penalised():
    long_h = make_output(
        headline=" ".join(["word"] * 25),
        body="Short body with flood and move action here.",
    )
    short_h = make_output(
        headline="Flood alert. Move now.",
        body="Short body with flood and move action here.",
    )
    assert score_translation(short_h) >= score_translation(long_h)


def test_score_range():
    out = make_output(
        headline="Flood coming tomorrow. Evacuate livestock now.",
        body="Heavy flood expected in Kenya by morning. Move your cattle to high ground. Avoid river banks. Contact local authorities.",
    )
    score = score_translation(out)
    assert 0.0 <= score <= 1.0
