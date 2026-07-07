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
    "fisherfolk": (
        "fishing communities on lakes, rivers, or coastal areas "
        "who depend on daily fishing for food and income"
    ),
    "urban": (
        "urban residents in informal settlements near rivers "
        "or low-lying flood-prone areas"
    ),
}

SEASON_CONTEXT = {
    "long_rains": "This is the long rains season (March-May). Soils are already saturated.",
    "short_rains": "This is the short rains season (October-December). Rivers are rising.",
    "dry": "This is the dry season. Flash floods from upstream are unexpected but possible.",
}


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

    return f"""Translate this early warning alert into {lang_name}.

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

LANGUAGE: Write your response entirely in {lang_name}. If writing in a
non-Latin script language (Amharic, Arabic), use the correct script. If
writing in a Latin-script African language (Swahili, Somali, Oromo), use
that language's vocabulary - do NOT translate to English.

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
