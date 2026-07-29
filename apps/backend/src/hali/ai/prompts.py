"""
Prompt library for the HALI AI layer.

All prompts are functions - parameterised and testable. Prompts are
designed for humanitarian communications best practices:
  - Grade 5 reading level
  - Action-first language
  - Location-specific
  - No invented facts
  - Culturally sensitive framing
"""
from __future__ import annotations

LANGUAGE_NAMES = {
    "sw": "Kiswahili",
    "so": "Soomaali",
    "am": "Amharic (አማርኛ)",
    "om": "Afaan Oromo",
    "ar": "Arabic (العربية)",
    "en": "English",
    "fr": "French (Français)",
    "ti": "Tigrinya (ትግርኛ)",
    "lg": "Luganda",
    "aa": "Afar (Qafar af)",
}

# Languages whose training data is thin enough that a fluent-looking output can
# still be wrong. The router holds these to the clarity floor and falls back to
# English rather than shipping a confident mistranslation of a life-safety
# instruction. See ai/router.py.
LOW_RESOURCE_LANGUAGES = frozenset({"ti", "lg", "aa"})

# Languages that must be written in a non-Latin script. Models drift into
# transliteration for these, which is unreadable to the intended audience.
NON_LATIN_SCRIPTS = {
    "am": "Ethiopic (Ge'ez) script",
    "ti": "Ethiopic (Ge'ez) script",
    "ar": "Arabic script",
}

LIVELIHOOD_CONTEXT = {
    "farmer": (
        "subsistence farmers who grow maize, sorghum, or beans "
        "and depend on seasonal rains for their harvest"
    ),
    "pastoralist": (
        "nomadic or semi-nomadic pastoralists who move livestock "
        "(cattle, camels, goats) across grazing lands"
    ),
    "agropastoralist": (
        "mixed crop-and-livestock households who farm a small plot and also "
        "keep livestock, common across the IGAD borderlands; they must choose "
        "between protecting the harvest and moving the herd"
    ),
    "fisherfolk": (
        "fishing communities on lakes, rivers, or coastal areas "
        "who depend on daily fishing for food and income"
    ),
    "urban": (
        "urban residents in informal settlements near rivers "
        "or low-lying flood-prone areas"
    ),
    "trader": (
        "market vendors, shopkeepers, and transporters whose income depends on "
        "roads and markets staying open, and who hold perishable stock they "
        "can lose in a day"
    ),
    "displaced": (
        "people living in displacement camps or informal settlements, "
        "dependent on aid distribution, without land or livestock, with "
        "limited freedom of movement and no property to secure"
    ),
}

SEASON_CONTEXT = {
    "long_rains": "This is the long rains season (March-May). Soils are already saturated.",
    "short_rains": "This is the short rains season (October-December). Rivers are rising.",
    "dry": "This is the dry season. Flash floods from upstream are unexpected but possible.",
}


def script_requirement(language_code: str) -> str:
    """A one-line instruction pinning the writing system, or '' for Latin scripts."""
    script = NON_LATIN_SCRIPTS.get(language_code)
    if not script:
        return ""
    name = LANGUAGE_NAMES.get(language_code, language_code)
    return (
        f"Write in {script}. Do NOT transliterate into Latin letters — "
        f"a {name} reader cannot read transliterated text."
    )


def translation_system_prompt() -> str:
    return """You are a humanitarian communications expert translating early warning alerts
for communities in East Africa. Your translations save lives.

Rules you must follow:
1. Write at Grade 5 reading level - simple, direct, short sentences.
2. Start with the most important information: what will happen, where, when.
3. Include one or two specific, concrete actions the reader should take NOW.
4. Do NOT invent details not in the alert. Do NOT add statistics you don't have.
5. Use culturally appropriate, respectful language for the target community.
6. The headline must be <= 20 words. The body must be <= 80 words.
7. Respond ONLY with valid JSON - no markdown, no preamble, no explanation:
   {"headline": "...", "body": "..."}"""


def translation_user_prompt(
    hazard_type: str,
    severity: str,
    countries: list[str],
    valid_from: str,
    valid_to: str,
    language_code: str,
    season: str | None = None,
    livelihood_hint: str | None = None,
) -> str:
    lang_name = LANGUAGE_NAMES.get(language_code, language_code)
    season_note = SEASON_CONTEXT.get(season or "", "")
    livelihood_note = (
        f"Primary audience: {LIVELIHOOD_CONTEXT.get(livelihood_hint, '')}."
        if livelihood_hint else ""
    )
    script_note = script_requirement(language_code)

    return f"""Translate this early warning alert into {lang_name}.
{script_note}

ALERT DETAILS:
  Hazard: {hazard_type}
  Severity: {severity.upper()}
  Affected countries: {', '.join(countries) or 'East Africa'}
  Valid from: {valid_from}
  Valid until: {valid_to}

CONTEXT:
  {season_note}
  {livelihood_note}

Translate into {lang_name}. Output JSON only."""


def action_card_system_prompt() -> str:
    return """You are an early warning response advisor for East Africa.
Generate practical, life-saving action steps for the next 48 hours.

Rules:
1. Exactly 4 numbered steps. Each step is one plain sentence.
2. Each step must be concrete and immediately actionable - not generic advice.
3. Steps must differ meaningfully from other livelihood groups.
4. No jargon. No technical terms. Plain spoken language.
5. Do not invent information about the hazard that was not provided.
6. After the 4 steps, add one sentence of context explaining WHY these steps matter for this livelihood.
7. Format: numbered list followed by a blank line and the context sentence."""


def action_card_user_prompt(
    hazard_type: str,
    severity: str,
    countries: list[str],
    livelihood: str,
    season: str | None = None,
    language: str = "en",
) -> str:
    livelihood_desc = LIVELIHOOD_CONTEXT.get(livelihood, livelihood)
    season_note = SEASON_CONTEXT.get(season or "", "")
    lang_name = LANGUAGE_NAMES.get(language, "English")

    return f"""Create a 48-hour action plan for this community.

ALERT:
  Hazard: {hazard_type} (severity: {severity})
  Region: {', '.join(countries) or 'East Africa'}
  {season_note}

AUDIENCE: {livelihood_desc}

LANGUAGE: Write your response entirely in {lang_name}.
{script_requirement(language)}
If writing in a Latin-script African language (Swahili, Somali, Oromo,
Luganda, Afar), use that language's vocabulary - do NOT translate to English.

What are the 4 most important things this community should do in the next 48 hours?
Write for people who may be illiterate - steps must be simple enough to be read aloud
in {lang_name}."""


def severity_assessment_system_prompt() -> str:
    return """You are a humanitarian risk analyst assessing whether community reports
warrant upgrading an existing alert's severity level.

You will receive:
- Current alert severity and hazard type
- A list of community reports from people in the affected area
- The number of reports received

Assess whether the reports provide credible evidence of escalating conditions.

Respond with JSON only:
{
  "should_upgrade": true/false,
  "proposed_severity": "green"|"orange"|"red",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence explaining the decision"
}"""


def severity_assessment_user_prompt(
    current_severity: str,
    hazard_type: str,
    report_count: int,
    descriptions: list[str],
) -> str:
    report_text = "\n".join(f"- {d}" for d in descriptions[:10])
    return f"""Current alert: {hazard_type} / severity={current_severity}
Community reports received: {report_count}

Report descriptions:
{report_text}

Should this alert be upgraded? Respond with JSON only."""


# The closed label vocabulary from spec §3.5. Exported so the classifier can
# reject anything a model invents outside this set — free-text labels would leak
# straight into the map's report breakdown and the analyse endpoint.
VALID_REPORT_LABELS = frozenset(
    {
        "flood",
        "drought",
        "locust",
        "cyclone",
        "health_emergency",
        "road_blocked",
        "bridge_damaged",
        "crop_loss",
        "livestock_at_risk",
        "displacement",
        "shelter_needed",
        "water_shortage",
        "food_shortage",
        "medical_needed",
        "communication_down",
        "power_outage",
        "other",
    }
)


def report_label_system_prompt() -> str:
    return """You are a disaster response information classifier.
Label the community report with 2-5 tags from this list:

flood, drought, locust, cyclone, health_emergency,
road_blocked, bridge_damaged, crop_loss, livestock_at_risk,
displacement, shelter_needed, water_shortage, food_shortage,
medical_needed, communication_down, power_outage, other

Rules:
- Return only tags that are clearly supported by the report text.
- Do not add tags that are implied but not stated.
- Respond with JSON only: {"labels": ["tag1", "tag2"]}"""


def report_label_user_prompt(description: str, hazard_type: str) -> str:
    return f"""Community report (hazard context: {hazard_type}):
"{description}"

Classify this report. JSON only."""
