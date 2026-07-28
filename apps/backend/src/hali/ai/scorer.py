"""
Humanitarian clarity scorer.

Scores a translation on a 0.0-1.0 scale using a rubric designed for
last-mile early warning communications. Used by the ensemble router to
pick the best-scoring output across providers.

Rubric dimensions (each 0.0-1.0, weighted):
  1. Length appropriateness  (20%) - headline <=20 words, body <=80 words
  2. Actionability           (25%) - contains action verbs
  3. Specificity             (20%) - contains location or hazard references
  4. Reading level           (20%) - short sentences, common words
  5. Completeness            (15%) - both headline and body are non-empty

This is a heuristic scorer - not perfect, but deterministic and fast.
It makes the ensemble selection reproducible and explainable.
"""
from __future__ import annotations

import re
from typing import Protocol

# Per-language lexicons for the actionability and specificity dimensions.
#
# These were previously one flat English/Swahili set, with Amharic entries
# written in Latin transliteration that can never match real Amharic script.
# The effect was systematic: for am, ar, om and so the two lexicon-based
# dimensions scored ~0 no matter how good the translation, so 45% of the rubric
# was dead weight and the ensemble picked winners for four of six languages on
# length and readability alone.
ACTION_VERBS: dict[str, set[str]] = {
    "en": {
        "move", "evacuate", "avoid", "shelter", "prepare", "leave", "go",
        "bring", "take", "protect", "contact", "alert", "stay", "check",
    },
    "sw": {
        "hamia", "hamisha", "ondoka", "epuka", "linda", "tayarisha", "nenda",
        "lete", "chukua", "wasiliana", "kaa", "angalia", "hifadhi", "kimbia",
    },
    "so": {
        "guur", "guuri", "bax", "baxa", "ilaali", "iska", "diyaari", "diyaarso",
        "aad", "ka", "badbaadi", "fiiri",
    },
    "om": {
        "deemi", "socho'i", "sochoosi", "baqadhu", "eeggadhu", "qophaa'i",
        "fudhadhu", "dhaqqabi", "of",
    },
    "am": {
        "ውጡ", "ሂዱ", "ተጠንቀቁ", "አስወግዱ", "ጠብቁ", "አዘጋጁ", "ውሰዱ", "ተንቀሳቀሱ", "ራቁ",
    },
    "ar": {
        "انتقل", "اذهب", "تجنب", "احتم", "استعد", "غادر", "ابتعد", "خذ", "احم",
        "انتقلوا", "اتركوا",
    },
}

HAZARD_KEYWORDS: dict[str, set[str]] = {
    "en": {"flood", "drought", "cyclone", "locust", "health", "flash", "river", "rain", "wind", "wave", "water"},
    "sw": {"mafuriko", "ukame", "kimbunga", "nzige", "afya", "mto", "mvua", "upepo", "wimbi", "maji"},
    "so": {"daad", "fatahaad", "abaar", "duufaan", "ayax", "caafimaad", "webi", "roob", "biyo"},
    "om": {"lolaa", "goggiinsa", "bubbee", "hawwaannisa", "fayyaa", "laga", "roobа", "bishaan", "rooba"},
    "am": {"ጎርፍ", "ድርቅ", "አውሎ", "አንበጣ", "ጤና", "ወንዝ", "ዝናብ", "ውሃ", "ነፋስ"},
    "ar": {"فيضان", "جفاف", "إعصار", "جراد", "صحة", "نهر", "مطر", "مياه", "رياح", "موجة"},
}


class ScorableTranslation(Protocol):
    headline: str
    body: str


def _lexicon(table: dict[str, set[str]], language: str | None) -> set[str]:
    """Lexicon for a language, always including English loanwords.

    Hazard names in particular are frequently borrowed verbatim, so an English
    term appearing in a Swahili alert is a genuine specificity signal.
    """
    words = set(table.get("en", set()))
    if language and language in table:
        words |= table[language]
    return words


def score_translation(output: ScorableTranslation) -> float:
    """Score a translation on the humanitarian clarity rubric, 0.0-1.0."""
    if not output.headline or not output.body:
        return 0.0

    language = getattr(output, "language", None)

    headline_words = output.headline.lower().split()
    body_words = output.body.lower().split()
    body_sentences = [s.strip() for s in re.split(r"[.!?।]", output.body) if s.strip()]

    scores: dict[str, float] = {}

    # 1. Length appropriateness (20%)
    headline_ok = len(headline_words) <= 20
    body_ok = len(body_words) <= 80
    scores["length"] = (0.5 if headline_ok else 0.0) + (0.5 if body_ok else 0.0)

    # 2. Actionability (25%)
    # Strip punctuation so "ondoka." and "فيضان،" still match.
    all_words = {w.strip(".,!?:;\"'()[]«»،؛۔") for w in headline_words + body_words}
    action_hits = len(all_words & _lexicon(ACTION_VERBS, language))
    scores["actionability"] = min(1.0, action_hits / 2.0)

    # 3. Specificity (20%)
    hazard_hits = len(all_words & _lexicon(HAZARD_KEYWORDS, language))
    scores["specificity"] = min(1.0, hazard_hits / 2.0)

    # 4. Reading level proxy (20%): shorter sentences and words score higher.
    avg_sent_len = (
        sum(len(s.split()) for s in body_sentences) / len(body_sentences)
        if body_sentences else 20
    )
    avg_word_len = (
        sum(len(w) for w in body_words) / len(body_words)
        if body_words else 10
    )
    sent_score = min(1.0, max(0.0, 1.0 - (avg_sent_len - 10) / 20))
    word_score = min(1.0, max(0.0, 1.0 - (avg_word_len - 4) / 8))
    scores["readability"] = (sent_score + word_score) / 2

    # 5. Completeness (15%)
    scores["completeness"] = 1.0 if (output.headline and output.body) else 0.0

    weights = {
        "length": 0.20,
        "actionability": 0.25,
        "specificity": 0.20,
        "readability": 0.20,
        "completeness": 0.15,
    }

    return round(sum(scores[k] * weights[k] for k in scores), 4)
