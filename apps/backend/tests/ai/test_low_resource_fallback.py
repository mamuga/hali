"""Low-resource languages fall back to English rather than serving a bad translation.

Tigrinya, Luganda and Afar have thin training data. A fluent-looking but wrong
evacuation instruction is more dangerous than an English one the reader has to
ask someone to interpret, so anything below the clarity floor is replaced —
while the row keeps the requested language code so lookups still resolve.
"""
import pytest

from hali.ai.models import ModelProvider, TranslationOutput
from hali.ai.processor import AlertProcessor
from hali.config import settings


class StubRouter:
    """Returns a queued output per call, recording the language asked for."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.languages: list[str] = []

    async def translate(self, system, user, language):
        self.languages.append(language)
        return self._outputs.pop(0)


def _output(language, score, headline="Headline", body="Body"):
    return TranslationOutput(
        provider=ModelProvider.GEMINI,
        model_name="stub",
        language=language,
        headline=headline,
        body=body,
        clarity_score=score,
    )


@pytest.fixture
def processor():
    proc = AlertProcessor.__new__(AlertProcessor)  # no pool needed
    return proc


CONTEXT = dict(
    hazard_type="flood",
    severity="red",
    countries=["ET"],
    valid_from="now",
    valid_to="later",
    season=None,
    livelihood_hint=None,
)


async def test_weak_tigrinya_is_replaced_by_english(processor):
    floor = settings.ai_min_clarity_score
    processor.router = StubRouter([_output("en", 0.9, headline="Flood warning")])

    weak = _output("ti", floor - 0.2, headline="weak")
    result = await processor._english_fallback_if_unusable(weak, **CONTEXT)

    assert result.language == "ti", "the row must stay findable under the requested language"
    assert result.fallback_language == "en"
    assert result.headline == "Flood warning"


async def test_good_tigrinya_is_kept_untouched(processor):
    good = _output("ti", settings.ai_min_clarity_score + 0.1, headline="ናይ ውሕጅ")
    processor.router = StubRouter([])

    result = await processor._english_fallback_if_unusable(good, **CONTEXT)

    assert result is good
    assert result.fallback_language is None
    assert processor.router.languages == [], "no second call should be made"


@pytest.mark.parametrize("language", ["sw", "am", "ar", "fr", "so", "om", "en"])
async def test_well_resourced_languages_never_fall_back(processor, language):
    """A weak Swahili translation is still Swahili — we do not swap it for English."""
    weak = _output(language, 0.0)
    processor.router = StubRouter([])

    result = await processor._english_fallback_if_unusable(weak, **CONTEXT)

    assert result is weak
    assert processor.router.languages == []


async def test_original_is_kept_when_english_also_fails(processor):
    """Never return an empty translation just because the fallback failed too."""
    weak = _output("lg", 0.0, headline="weak but present")
    processor.router = StubRouter([_output("en", 0.9, headline="")])

    result = await processor._english_fallback_if_unusable(weak, **CONTEXT)

    assert result is weak
    assert result.fallback_language is None


async def test_fallback_requests_english_from_the_router(processor):
    weak = _output("aa", 0.0)
    processor.router = StubRouter([_output("en", 0.95)])

    await processor._english_fallback_if_unusable(weak, **CONTEXT)

    assert processor.router.languages == ["en"]
