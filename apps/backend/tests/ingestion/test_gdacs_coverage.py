"""Why GDACS was contributing zero alerts for East Africa.

Three compounding bugs meant the live Orange drought over Ethiopia, Kenya and
Somalia was never ingested:

  1. One combined query for all six hazard types hit the API's 100-result cap,
     which is filled globally by whatever is most frequent worldwide.
  2. Country matching read only `iso3`, so a regional event filed under its
     primary country hid the other members.
  3. `todate` was taken literally for events GDACS still flags `iscurrent`,
     filing an ongoing emergency as already expired.
"""
from datetime import UTC, datetime, timedelta

from hali.ingestion.gdacs import ONGOING_EVENT_EXTENSION, _igad_countries, _valid_to


class TestIgadCountryMatching:
    def test_single_igad_country(self):
        assert _igad_countries({"iso3": "KEN"}) == ["KE"]

    def test_regional_event_returns_every_member_it_affects(self):
        """The live drought: filed under ETH, but Kenya and Somalia are in
        `affectedcountries`. Reading iso3 alone would leave Kenyan and Somali
        subscribers unmatched, because broadcast targets affected_countries."""
        props = {
            "iso3": "ETH",
            "affectedcountries": [{"iso3": "ETH"}, {"iso3": "KEN"}, {"iso3": "SOM"}],
        }
        assert _igad_countries(props) == ["ET", "KE", "SO"]

    def test_igad_member_only_in_affectedcountries(self):
        props = {"iso3": "EGY", "affectedcountries": [{"iso3": "EGY"}, {"iso3": "SDN"}]}
        assert _igad_countries(props) == ["SD"]

    def test_non_igad_event_is_excluded(self):
        assert _igad_countries({"iso3": "CHN"}) == []

    def test_no_country_information(self):
        assert _igad_countries({}) == []
        assert _igad_countries({"iso3": None}) == []
        assert _igad_countries({"iso3": ""}) == []

    def test_prefix_lookalikes_are_not_matched(self):
        """The old code took iso3[:2], which maps TCD (Chad) to 'TC' and SDS to
        'SD'. It gave the right answer for all eight IGAD states only by
        coincidence."""
        assert _igad_countries({"iso3": "TCD"}) == []
        assert _igad_countries({"iso3": "ERG"}) == []
        assert _igad_countries({"iso3": "UGX"}) == []

    def test_lowercase_and_padded_codes(self):
        assert _igad_countries({"iso3": " ken "}) == ["KE"]

    def test_malformed_affectedcountries_entries_are_skipped(self):
        props = {"iso3": "KEN", "affectedcountries": ["SOM", None, {"iso3": "UGA"}]}
        assert _igad_countries(props) == ["KE", "UG"]

    def test_result_is_deduplicated_and_sorted(self):
        props = {"iso3": "KEN", "affectedcountries": [{"iso3": "KEN"}, {"iso3": "ETH"}]}
        assert _igad_countries(props) == ["ET", "KE"]


class TestOngoingEventExpiry:
    def test_current_event_with_a_past_todate_is_extended(self):
        past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        result = _valid_to({"todate": past, "iscurrent": "true"})

        assert result > datetime.now(UTC), "an ongoing emergency must not be filed as expired"

    def test_extension_is_bounded(self):
        past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        result = _valid_to({"todate": past, "iscurrent": True})

        assert result <= datetime.now(UTC) + ONGOING_EVENT_EXTENSION + timedelta(minutes=1)

    def test_current_event_with_a_future_todate_keeps_it(self):
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        result = _valid_to({"todate": future, "iscurrent": "true"})

        assert result.date() == (datetime.now(UTC) + timedelta(days=30)).date()

    def test_finished_event_keeps_its_past_todate(self):
        past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        result = _valid_to({"todate": past, "iscurrent": "false"})

        assert result < datetime.now(UTC), "a closed event must stay closed"

    def test_missing_todate_on_a_current_event_still_gets_an_expiry(self):
        result = _valid_to({"iscurrent": "true"})
        assert result > datetime.now(UTC)

    def test_missing_todate_on_a_closed_event_is_left_to_the_caller(self):
        assert _valid_to({}) is None
