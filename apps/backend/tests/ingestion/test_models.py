"""Unit tests for ETL Pydantic models."""
from hali.ingestion.models import IngestionResult, NormalisedAlert, RawPayload, SourceName


def test_dedup_hash_is_stable():
    h1 = NormalisedAlert.build_dedup_hash("gdacs", "evt-001", "red")
    h2 = NormalisedAlert.build_dedup_hash("gdacs", "evt-001", "red")
    assert h1 == h2
    assert len(h1) == 32


def test_dedup_hash_differs_by_source():
    assert NormalisedAlert.build_dedup_hash("gdacs", "evt-001", "red") != NormalisedAlert.build_dedup_hash("chirps", "evt-001", "red")


def test_dedup_hash_differs_by_severity():
    assert NormalisedAlert.build_dedup_hash("gdacs", "evt-001", "red") != NormalisedAlert.build_dedup_hash("gdacs", "evt-001", "orange")


def test_ingestion_result_defaults():
    result = IngestionResult(source=SourceName.GDACS)
    assert result.inserted_count == 0
    assert result.failed_count == 0
    assert result.errors == []


def test_raw_payload_auto_timestamp():
    raw = RawPayload(source=SourceName.GDACS, raw_data={"test": True}, source_event_id="test-001")
    assert raw.fetched_at.tzinfo is not None
