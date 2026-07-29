"""Pydantic models for the HALI AI layer."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ModelProvider(StrEnum):
    CLAUDE = "claude"
    GEMINI = "gemini"
    GROQ = "groq"
    CACHED = "cached"  # last-resort: return cached translation


class ProcessingRequest(BaseModel):
    alert_id: UUID
    hazard_type: str
    severity: str
    affected_countries: list[str]
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    centroid_lat: float | None = None
    centroid_lng: float | None = None
    season: str | None = None  # 'long_rains' | 'short_rains' | 'dry'


class TranslationOutput(BaseModel):
    """One model's attempt at translation + humanitarian clarity score."""

    provider: ModelProvider
    model_name: str
    language: str
    headline: str
    body: str
    clarity_score: float = 0.0
    latency_ms: float = 0.0
    error: str | None = None
    # Set when the text is not actually in `language`: a low-resource
    # translation scored below the clarity floor and English was served in its
    # place. None means the content genuinely is in the requested language.
    fallback_language: str | None = None


class EnsembleResult(BaseModel):
    """Best-scored translation across all providers."""

    language: str
    winning_provider: ModelProvider
    winning_model: str
    headline: str
    body: str
    clarity_score: float
    all_attempts: list[TranslationOutput] = Field(default_factory=list)


class ActionCard(BaseModel):
    alert_id: UUID
    livelihood: str
    language: str
    steps: str
    context_notes: str = ""
    generated_by: ModelProvider = ModelProvider.CLAUDE


class AlertUpgradeSignal(BaseModel):
    """Aggregated community reports suggesting severity upgrade."""

    alert_id: UUID
    current_severity: str
    proposed_severity: str
    report_count: int
    confidence: float
    supporting_descriptions: list[str]
    claude_reasoning: str
    should_upgrade: bool = False


class ProcessingResult(BaseModel):
    """Summary of all AI work done on one alert."""

    alert_id: UUID
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    translations_completed: int = 0
    action_cards_completed: int = 0
    ensemble_winners: dict[str, ModelProvider] = Field(default_factory=dict)
    upgrade_signal: AlertUpgradeSignal | None = None
    errors: list[str] = Field(default_factory=list)
    total_duration_ms: float = 0.0
