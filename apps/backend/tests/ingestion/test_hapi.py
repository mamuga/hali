"""HAPI rainfall-anomaly classification and series reduction.

This adapter is what makes HALI subnational: it turns "Kilifi is at 41% of
normal rainfall" into a drought alert shaped like Kilifi. The logic worth
testing is the thresholding and the reduction of a noisy multi-year series to
one current observation per district.
"""
from datetime import UTC, datetime, timedelta

import pytest

from hali.ingestion.hapi import (
    ALERT_VALIDITY,
    DROUGHT_CONSECUTIVE_DEKADS,
    DROUGHT_ORANGE_MAX,
    DROUGHT_RED_MAX,
    FLOOD_ORANGE_MIN,
    FLOOD_RED_MIN,
    HapiError,
    app_identifier,
    classify,
    latest_observations,
    run_ingest,
)
from hali.ingestion.models import HazardType, Severity


def _row(pcode, anomaly, end, admin1="Coast", admin2="Ganze"):
    return {
        "admin2_code": pcode,
        "admin1_name": admin1,
        "admin2_name": admin2,
        "rainfall_anomaly_pct": anomaly,
        "rainfall": 10.0,
        "rainfall_long_term_average": 25.0,
        "reference_period_start": (end - timedelta(days=10)).isoformat(),
        "reference_period_end": end.isoformat(),
    }


BASE = datetime(2026, 7, 10, tzinfo=UTC)


class TestClassification:
    def test_severe_deficit_is_red_drought(self):
        assert classify(41.0, dry_run_length=3) == (HazardType.DROUGHT, Severity.RED)

    def test_moderate_deficit_is_orange_drought(self):
        assert classify(60.0, dry_run_length=2) == (HazardType.DROUGHT, Severity.ORANGE)

    def test_normal_rainfall_raises_nothing(self):
        assert classify(100.0, dry_run_length=0) is None
        assert classify(95.0, dry_run_length=5) is None

    def test_a_single_dry_dekad_is_weather_not_drought(self):
        """One dry ten-day window must not raise a drought alert across a country."""
        assert classify(41.0, dry_run_length=1) is None
        assert DROUGHT_CONSECUTIVE_DEKADS >= 2

    def test_heavy_rainfall_is_flood(self):
        assert classify(FLOOD_ORANGE_MIN, dry_run_length=0) == (HazardType.FLOOD, Severity.ORANGE)
        assert classify(FLOOD_RED_MIN + 50, dry_run_length=0) == (HazardType.FLOOD, Severity.RED)

    def test_flood_does_not_require_persistence(self):
        """A single dekad of double the normal rain is already a flood signal."""
        assert classify(250.0, dry_run_length=0) is not None

    @pytest.mark.parametrize(
        ("anomaly", "expected"),
        [
            (DROUGHT_RED_MAX, Severity.RED),
            (DROUGHT_RED_MAX + 0.1, Severity.ORANGE),
            (DROUGHT_ORANGE_MAX, Severity.ORANGE),
        ],
    )
    def test_threshold_boundaries(self, anomaly, expected):
        assert classify(anomaly, dry_run_length=3)[1] == expected

    def test_just_above_the_drought_threshold_is_clear(self):
        assert classify(DROUGHT_ORANGE_MAX + 0.1, dry_run_length=5) is None


class TestSeriesReduction:
    def test_keeps_only_the_most_recent_dekad_per_unit(self):
        rows = [
            _row("KE001003", 95.0, BASE - timedelta(days=30)),
            _row("KE001003", 41.0, BASE),
            _row("KE001003", 80.0, BASE - timedelta(days=10)),
        ]
        current = latest_observations(rows)

        assert set(current) == {"KE001003"}
        assert current["KE001003"]["anomaly_pct"] == 41.0
        assert current["KE001003"]["period_end"] == BASE

    def test_duplicate_rows_for_one_dekad_are_collapsed(self):
        """HAPI can return several provider revisions of the same dekad."""
        rows = [_row("KE001003", 41.0, BASE), _row("KE001003", 41.0, BASE)]
        current = latest_observations(rows)

        assert current["KE001003"]["dry_run_dekads"] == 1

    def test_counts_consecutive_dry_dekads_backwards(self):
        rows = [
            _row("KE001003", 40.0, BASE),
            _row("KE001003", 55.0, BASE - timedelta(days=10)),
            _row("KE001003", 60.0, BASE - timedelta(days=20)),
            _row("KE001003", 120.0, BASE - timedelta(days=30)),
            _row("KE001003", 30.0, BASE - timedelta(days=40)),
        ]
        # The run stops at the wet dekad, so 3 — not 4.
        assert latest_observations(rows)["KE001003"]["dry_run_dekads"] == 3

    def test_a_wet_current_dekad_ends_the_run_immediately(self):
        rows = [
            _row("KE001003", 130.0, BASE),
            _row("KE001003", 30.0, BASE - timedelta(days=10)),
        ]
        assert latest_observations(rows)["KE001003"]["dry_run_dekads"] == 0

    def test_units_are_tracked_independently(self):
        rows = [
            _row("KE001003", 41.0, BASE, admin2="Ganze"),
            _row("KE002010", 140.0, BASE, admin2="Kitui South"),
        ]
        current = latest_observations(rows)

        assert current["KE001003"]["anomaly_pct"] == 41.0
        assert current["KE002010"]["anomaly_pct"] == 140.0

    def test_rows_without_an_anomaly_are_ignored(self):
        rows = [_row("KE001003", None, BASE), _row("KE001003", 41.0, BASE - timedelta(days=10))]
        current = latest_observations(rows)

        assert current["KE001003"]["anomaly_pct"] == 41.0

    def test_rows_without_a_pcode_are_ignored(self):
        row = _row(None, 41.0, BASE)
        assert latest_observations([row]) == {}

    def test_empty_input(self):
        assert latest_observations([]) == {}


class TestConfiguration:
    def test_app_identifier_is_base64_of_app_and_email(self):
        import base64

        decoded = base64.b64decode(app_identifier()).decode()
        assert decoded.startswith("hali:")

    def test_alert_outlives_one_publication_cycle(self):
        """HAPI publishes a dekad well after it closes; validity must cover the
        gap or every alert is born expired."""
        assert ALERT_VALIDITY >= timedelta(days=11)

    async def test_unsupported_country_is_rejected(self):
        with pytest.raises(HapiError, match="unsupported country codes"):
            await run_ingest(pool=None, only=["KE", "ZZ"])

    def test_eritrea_is_not_claimed_as_supported(self):
        """HAPI has no rainfall series for Eritrea; pretending otherwise would
        produce a country that silently never alerts."""
        from hali.ingestion.hapi import ISO2_TO_ISO3

        assert "ER" not in ISO2_TO_ISO3
