import hashlib
import json


def severity(value: str | None) -> str:
    text = (value or "green").lower()
    if text in {"red", "high", "severe", "extreme"}:
        return "red"
    if text in {"orange", "medium", "moderate"}:
        return "orange"
    return "green"


def hazard(value: str | None) -> str:
    text = (value or "other").lower()
    if "flood" in text:
        return "flood"
    if "drought" in text:
        return "drought"
    if "locust" in text:
        return "locust"
    if "cyclone" in text or "storm" in text:
        return "cyclone"
    if "disease" in text or "health" in text:
        return "health"
    return "other"


def dedup_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
