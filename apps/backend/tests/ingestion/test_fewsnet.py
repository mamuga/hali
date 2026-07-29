"""FEWS NET IPC ingestion.

The only source that gives HALI finished hazard polygons. The logic worth
testing is the phase threshold, the collapse of livelihood-zone slivers into
districts, and the geometry union — a wrong union silently produces an alert
covering the wrong ground.
"""
from datetime import UTC, datetime

import pytest

from hali.ingestion.fewsnet import (
    FEWSNET_COUNTRIES,
    IPC_ALERT_THRESHOLD,
    IPC_PHASE_SEVERITY,
    MAX_MONTHS_BACK,
    MIN_ARCHIVE_BYTES,
    FewsNetError,
    _collection_date,
    group_units,
    merge_geometry,
    run_ingest,
)
from hali.ingestion.models import Severity


class FakeShape:
    def __init__(self, geo):
        self.__geo_interface__ = geo


class FakeShapeRecord:
    def __init__(self, record, geo):
        self.record = record
        self.shape = FakeShape(geo)


class FakeReader:
    def __init__(self, records):
        self._records = records

    def shapeRecords(self):  # noqa: N802 - mirrors pyshp's API
        return self._records


def _square(x=0.0, y=0.0, size=1.0):
    return {
        "type": "Polygon",
        "coordinates": [
            [[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]
        ],
    }


def _rec(admin1, admin2, cs, geo=None):
    return FakeShapeRecord({"ADMIN1": admin1, "ADMIN2": admin2, "CS": cs}, geo or _square())


class TestPhaseThreshold:
    def test_crisis_and_worse_produce_alerts(self):
        reader = FakeReader([_rec("Garissa", "Dadaab", 3), _rec("Bay", "Baidoa", 4)])
        assert len(group_units(reader)) == 2

    def test_minimal_and_stressed_do_not(self):
        """Phase 1-2 is normal-to-difficult, not an emergency. Alerting on them
        would mark most of the region permanently."""
        reader = FakeReader([_rec("Meru", "Buuri", 1), _rec("Meru", "Igembe", 2)])
        assert group_units(reader) == {}

    def test_threshold_is_the_humanitarian_action_line(self):
        assert IPC_ALERT_THRESHOLD == 3

    def test_emergency_and_famine_are_red(self):
        assert IPC_PHASE_SEVERITY[4] == Severity.RED
        assert IPC_PHASE_SEVERITY[5] == Severity.RED

    def test_crisis_is_orange(self):
        assert IPC_PHASE_SEVERITY[3] == Severity.ORANGE

    def test_missing_or_malformed_phase_is_skipped(self):
        reader = FakeReader([_rec("A", "B", None), _rec("A", "C", ""), _rec("A", "D", "x")])
        assert group_units(reader) == {}


class TestDistrictGrouping:
    def test_livelihood_zones_collapse_into_one_district(self):
        """Kenya's package holds 640 units, 272 at phase 3, which group into 36
        districts. Emitting one alert per sliver would bury the map."""
        reader = FakeReader(
            [
                _rec("Garissa", "Dadaab", 3, _square(0, 0)),
                _rec("Garissa", "Dadaab", 3, _square(1, 0)),
                _rec("Garissa", "Dadaab", 3, _square(2, 0)),
            ]
        )
        groups = group_units(reader)

        assert len(groups) == 1
        assert len(groups[("Garissa", "Dadaab", 3)]) == 3

    def test_different_phases_in_one_district_stay_separate(self):
        reader = FakeReader([_rec("Bay", "Baidoa", 3), _rec("Bay", "Baidoa", 4)])
        assert len(group_units(reader)) == 2

    def test_districts_are_kept_apart(self):
        reader = FakeReader([_rec("Garissa", "Dadaab", 3), _rec("Garissa", "Lagdera", 3)])
        assert len(group_units(reader)) == 2

    def test_missing_admin2_falls_back_to_admin1(self):
        reader = FakeReader([_rec("Karamoja", "", 3)])
        assert ("Karamoja", "Karamoja", 3) in group_units(reader)

    def test_unit_with_no_admin_names_is_skipped(self):
        assert group_units(FakeReader([_rec("", "", 3)])) == {}


class TestGeometryMerge:
    def test_adjacent_squares_merge_into_one_polygon(self):
        merged = merge_geometry([_square(0, 0), _square(1, 0)])
        assert merged is not None
        assert '"type": "Polygon"' in merged

    def test_disjoint_squares_stay_multipolygon(self):
        merged = merge_geometry([_square(0, 0), _square(10, 10)])
        assert '"type": "MultiPolygon"' in merged

    def test_single_shape_passes_through(self):
        assert merge_geometry([_square()]) is not None

    def test_empty_input_returns_none(self):
        assert merge_geometry([]) is None

    def test_invalid_geometry_does_not_raise(self):
        """A self-intersecting ring must not kill the whole country's ingest."""
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]],
        }
        assert merge_geometry([bowtie]) is not None


class TestConfiguration:
    def test_only_countries_with_published_data(self):
        """Djibouti and Eritrea return a 4-byte empty archive; claiming support
        would produce two countries that silently never alert."""
        assert set(FEWSNET_COUNTRIES) == {"KE", "ET", "SO", "UG", "SD", "SS"}

    def test_empty_archive_threshold_is_above_the_empty_response(self):
        assert MIN_ARCHIVE_BYTES > 4

    @pytest.mark.parametrize(
        ("now", "expected"),
        [
            (datetime(2026, 7, 28, tzinfo=UTC), "2026-06-01"),
            (datetime(2026, 1, 15, tzinfo=UTC), "2025-12-01"),
            (datetime(2026, 3, 1, tzinfo=UTC), "2026-02-01"),
        ],
    )
    def test_search_starts_at_the_previous_month(self, now, expected):
        """The current month's classification is published during it, so asking
        for it returns nothing."""
        assert _collection_date(now) == expected

    def test_walks_backwards_across_a_year_boundary(self):
        now = datetime(2026, 2, 10, tzinfo=UTC)
        assert [_collection_date(now, n) for n in range(1, 4)] == [
            "2026-01-01",
            "2025-12-01",
            "2025-11-01",
        ]

    def test_search_window_spans_more_than_one_release_cycle(self):
        """A full CS analysis lands roughly every four months (verified: Feb and
        June 2026 for Kenya, projections only in between). Searching only one or
        two months back finds nothing for most of the year."""
        assert MAX_MONTHS_BACK >= 6

    def test_validity_bridges_the_gap_between_releases(self):
        from hali.ingestion.fewsnet import ALERT_VALIDITY

        assert ALERT_VALIDITY.days >= 120

    async def test_unsupported_country_is_rejected(self):
        with pytest.raises(FewsNetError, match="unsupported country codes"):
            await run_ingest(pool=None, only=["KE", "ZZ"])
