"""Pydantic models defining the ETL contract between layers."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class HazardType(StrEnum):
    FLOOD = "flood"
    DROUGHT = "drought"
    LOCUST = "locust"
    CYCLONE = "cyclone"
    HEALTH = "health"
    OTHER = "other"


class Severity(StrEnum):
    GREEN = "green"
    ORANGE = "orange"
    RED = "red"


class SourceName(StrEnum):
    GDACS = "gdacs"
    CHIRPS = "chirps"
    GFS = "gfs"
    GLOFAS = "glofas"
    ICPAC = "icpac"


class IngestionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class RawPayload(BaseModel):
    """Raw source data produced by extract()."""

    source: SourceName
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_data: dict[str, Any]
    source_event_id: str


class GeoJSONGeometry(BaseModel):
    """Minimal supported GeoJSON geometry shape."""

    type: str
    coordinates: Any

    @field_validator("type")
    @classmethod
    def must_be_supported_type(cls, value: str) -> str:
        if value not in {"Polygon", "MultiPolygon", "Point"}:
            raise ValueError(f"Geometry type {value!r} not supported")
        return value


class ValidatedAlert(BaseModel):
    """Boundary-validated source alert."""

    source: SourceName
    source_event_id: str
    hazard_type: HazardType
    severity: Severity
    geometry: GeoJSONGeometry
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    affected_countries: list[str] = Field(default_factory=list)
    raw_payload_id: UUID | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("affected_countries", mode="before")
    @classmethod
    def clean_countries(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [country.strip().upper() for country in value.split(",") if country.strip()]
        if isinstance(value, list):
            return [str(country).strip().upper() for country in value if str(country).strip()]
        return []


class NormalisedAlert(BaseModel):
    """HALI alert ready for PostGIS insert."""

    source: SourceName
    source_event_id: str
    hazard_type: HazardType
    severity: Severity
    geojson_geometry: dict[str, Any]
    affected_countries: list[str]
    valid_from: datetime | None
    valid_to: datetime | None
    dedup_hash: str
    raw_payload_id: UUID | None = None
    source_url: str | None = None

    @classmethod
    def build_dedup_hash(cls, source: str, event_id: str, severity: str) -> str:
        return hashlib.md5(f"{source}:{event_id}:{severity}".encode()).hexdigest()


class IngestionResult(BaseModel):
    """Summary returned by each adapter run."""

    source: SourceName
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_count: int = 0
    validated_count: int = 0
    inserted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
