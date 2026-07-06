"""BaseAdapter - typed contract every ingestion source implements."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import asyncpg
import structlog

from .models import IngestionResult, NormalisedAlert, RawPayload, SourceName, ValidatedAlert

logger = structlog.get_logger(__name__)


class BaseAdapter(ABC):
    source: SourceName

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool
        self._log = logger.bind(source=self.source.value)

    @abstractmethod
    async def extract(self) -> list[RawPayload]:
        """Fetch raw source records. Implementations must not write to the DB."""

    @abstractmethod
    def validate(self, raw: RawPayload) -> ValidatedAlert | None:
        """Validate one raw record at the source boundary."""

    @abstractmethod
    def transform(self, validated: ValidatedAlert) -> NormalisedAlert:
        """Transform one validated record to the HALI alert model."""

    async def run(self) -> IngestionResult:
        from .loader import Loader

        result = IngestionResult(source=self.source)
        start = time.perf_counter()
        loader = Loader(self.pool)

        self._log.info("ingestion.start")
        try:
            raw_payloads = await self.extract()
        except Exception as exc:
            result.failed_count += 1
            result.errors.append(f"extract failed: {exc}")
            self._log.error("ingestion.extract_failed", error=str(exc))
            result.duration_ms = (time.perf_counter() - start) * 1000
            return result

        result.raw_count = len(raw_payloads)
        self._log.info("ingestion.extracted", count=result.raw_count)

        for raw in raw_payloads:
            try:
                raw_id = await loader.store_raw(raw)
            except Exception as exc:
                result.failed_count += 1
                result.errors.append(f"raw store failed for {raw.source_event_id}: {exc}")
                self._log.error("ingestion.raw_store_failed", event_id=raw.source_event_id, error=str(exc))
                continue

            try:
                validated = self.validate(raw)
            except Exception as exc:
                validated = None
                result.errors.append(f"validation crashed for {raw.source_event_id}: {exc}")

            if validated is None:
                result.failed_count += 1
                await loader.mark_raw_failed(raw_id, "validation rejected")
                self._log.warning("ingestion.validation_rejected", event_id=raw.source_event_id)
                continue

            result.validated_count += 1
            validated.raw_payload_id = raw_id

            try:
                normalised = self.transform(validated)
            except Exception as exc:
                result.failed_count += 1
                await loader.mark_raw_failed(raw_id, str(exc))
                result.errors.append(f"transform failed for {raw.source_event_id}: {exc}")
                self._log.error("ingestion.transform_failed", event_id=raw.source_event_id, error=str(exc))
                continue

            try:
                inserted = await loader.upsert_alert(normalised)
            except Exception as exc:
                result.failed_count += 1
                await loader.mark_raw_failed(raw_id, str(exc))
                result.errors.append(f"load failed for {raw.source_event_id}: {exc}")
                self._log.error("ingestion.load_failed", event_id=raw.source_event_id, error=str(exc))
                continue

            await loader.mark_raw_processed(raw_id)
            if inserted:
                result.inserted_count += 1
                self._log.info(
                    "ingestion.alert_inserted",
                    event_id=raw.source_event_id,
                    hazard=normalised.hazard_type.value,
                    severity=normalised.severity.value,
                )
            else:
                result.skipped_count += 1
                self._log.debug("ingestion.duplicate_skipped", dedup_hash=normalised.dedup_hash)

        result.duration_ms = (time.perf_counter() - start) * 1000
        self._log.info(
            "ingestion.complete",
            raw=result.raw_count,
            inserted=result.inserted_count,
            skipped=result.skipped_count,
            failed=result.failed_count,
            duration_ms=round(result.duration_ms, 1),
        )
        return result
