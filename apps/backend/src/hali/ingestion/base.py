from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AdapterStatus:
    source: str
    enabled: bool
    status: str
    detail: str


@dataclass(frozen=True)
class NormalizedAlert:
    source: str
    external_id: str
    hazard_type: str
    severity: str
    affected_countries: list[str]
    geometry_geojson: dict
    valid_from: str | None
    valid_to: str | None
    payload: dict


class HazardAdapter(Protocol):
    source: str

    async def status(self) -> AdapterStatus: ...
    async def fetch(self) -> list[NormalizedAlert]: ...
