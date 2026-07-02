from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

HazardType = Literal["flood", "drought", "locust", "cyclone", "health", "other"]
Severity = Literal["green", "orange", "red"]
Language = Literal["sw", "so", "am", "om", "ar", "en"]
Livelihood = Literal["farmer", "pastoralist", "fisherfolk", "urban"]


class Alert(BaseModel):
    id: UUID
    hazard_type: HazardType
    severity: Severity
    affected_countries: list[str]
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    processed_at: datetime | None = None
    is_new: bool = False
    headline: str | None = None
    body: str | None = None
    audio_url: str | None = None


class ActionCard(BaseModel):
    alert_id: UUID
    livelihood: Livelihood
    language: Language
    steps: str


class CommunityReportCreate(BaseModel):
    lat: float = Field(ge=-12, le=24)
    lng: float = Field(ge=21, le=52)
    hazard_type: HazardType
    description: str = Field(min_length=3, max_length=1000)


class CommunityReportResponse(CommunityReportCreate):
    id: UUID
    labels: list[str]
    reported_at: datetime
