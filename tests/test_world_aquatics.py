import pytest

from app.services.normalizer import AthleteRecord
from app.services.world_aquatics import (
    WorldAquaticsSource,
    _infer_course,
    _parse_discipline,
)


class TestParseDiscipline:
    def test_mens_freestyle(self):
        assert _parse_discipline("Men's 100m Freestyle") == ("M", 100, "freestyle")

    def test_womens_backstroke(self):
        assert _parse_discipline("Women's 200m Backstroke") == ("F", 200, "backstroke")

    def test_womens_breaststroke(self):
        assert _parse_discipline("Women's 50m Breaststroke") == ("F", 50, "breaststroke")

    def test_mens_butterfly(self):
        assert _parse_discipline("Men's 100m Butterfly") == ("M", 100, "butterfly")

    def test_medley_maps_to_im(self):
        assert _parse_discipline("Women's 200m Medley") == ("F", 200, "im")

    def test_relay_returns_none(self):
        assert _parse_discipline("Men's 4x100m Freestyle Relay") is None

    def test_womens_relay_returns_none(self):
        assert _parse_discipline("Women's 4x200m Freestyle Relay") is None

    def test_unknown_stroke_returns_none(self):
        assert _parse_discipline("Men's 100m Crawl") is None

    def test_empty_string_returns_none(self):
        assert _parse_discipline("") is None


class TestInferCourse:
    def test_default_is_lcm(self):
        assert _infer_course("World Championships") == "LCM"

    def test_scm_from_25m_suffix(self):
        assert _infer_course("World Championships (25m)") == "SCM"

    def test_scm_from_short_course_text(self):
        assert _infer_course("Short Course World Championships") == "SCM"

    def test_scm_explicit_tag(self):
        assert _infer_course("European Championships (SCM)") == "SCM"

    def test_scy_from_25yd(self):
        assert _infer_course("NCAA Championships (25yd)") == "SCY"

    def test_scy_explicit_tag(self):
        assert _infer_course("US Nationals (SCY)") == "SCY"

    def test_case_insensitive(self):
        assert _infer_course("WORLD CHAMPIONSHIPS (25M)") == "SCM"


class TestParseDate:
    def test_dd_mm_yyyy(self):
        assert WorldAquaticsSource._parse_date("25/07/2022") == "2022-07-25"

    def test_iso_format(self):
        assert WorldAquaticsSource._parse_date("2022-07-25") == "2022-07-25"

    def test_mm_dd_yyyy(self):
        assert WorldAquaticsSource._parse_date("07/25/2022") == "2022-07-25"

    def test_empty_returns_none(self):
        assert WorldAquaticsSource._parse_date("") is None

    def test_unparseable_returns_none(self):
        assert WorldAquaticsSource._parse_date("not-a-date") is None


class TestGetEventTopTimes:
    async def test_scy_returns_empty_without_network_call(self):
        source = WorldAquaticsSource()
        result = await source.get_event_top_times("M", 100, "freestyle", "SCY")
        assert result == []

    async def test_unknown_stroke_returns_empty(self):
        source = WorldAquaticsSource()
        result = await source.get_event_top_times("M", 100, "crawl", "LCM")
        assert result == []


class TestRowsToResults:
    def _source(self):
        return WorldAquaticsSource()

    def _row(self, **overrides):
        base = {
            "full_name_computed": "Caeleb DRESSEL",
            "swim_time": "47.02",
            "meet_name": "World Championships",
            "swim_date": "25/07/2022",
            "team_code": "USA",
            "country_code": "JPN",
            "meet_city": "Budapest",
        }
        base.update(overrides)
        return base

    def test_valid_row_parsed(self):
        results = self._source()._rows_to_results([self._row()], "M", 100, "freestyle", "LCM")
        assert len(results) == 1
        r = results[0]
        assert r.time_seconds == pytest.approx(47.02)
        assert r.athlete.canonical_name == "caeleb dressel"
        assert r.athlete.country_code == "USA"
        assert r.meet.city == "Budapest"
        assert r.meet.country_code == "JPN"
        assert r.swim_date == "2022-07-25"

    def test_missing_name_skipped(self):
        rows = [self._row(full_name_computed="")]
        assert self._source()._rows_to_results(rows, "M", 100, "freestyle", "LCM") == []

    def test_missing_time_skipped(self):
        rows = [self._row(swim_time="")]
        assert self._source()._rows_to_results(rows, "M", 100, "freestyle", "LCM") == []

    def test_invalid_time_skipped(self):
        rows = [self._row(swim_time="NT")]
        assert self._source()._rows_to_results(rows, "M", 100, "freestyle", "LCM") == []

    def test_results_sorted_by_time_ascending(self):
        rows = [
            self._row(full_name_computed="Athlete B", swim_time="48.00"),
            self._row(full_name_computed="Athlete A", swim_time="47.00"),
        ]
        results = self._source()._rows_to_results(rows, "M", 100, "freestyle", "LCM")
        assert results[0].time_seconds < results[1].time_seconds

    def test_country_code_truncated_to_3(self):
        rows = [self._row(team_code="UNITED")]
        results = self._source()._rows_to_results(rows, "M", 100, "freestyle", "LCM")
        assert results[0].athlete.country_code == "UNI"

    def test_empty_country_code_is_none(self):
        rows = [self._row(team_code="")]
        results = self._source()._rows_to_results(rows, "M", 100, "freestyle", "LCM")
        assert results[0].athlete.country_code is None


class TestRawResultsToRecords:
    def _source(self):
        return WorldAquaticsSource()

    def _athlete(self):
        return AthleteRecord(canonical_name="caeleb dressel", source="world_aquatics")

    def _raw(self, **overrides):
        base = {
            "DisciplineName": "Men's 100m Freestyle",
            "Time": "47.02",
            "CompetitionName": "World Championships",
            "CompetitionCity": "Budapest",
            "CompetitionCountry": "HUN",
            "Date": "2022-07-25",
            "NAT": "USA",
            "ClubName": "",
        }
        base.update(overrides)
        return base

    def test_valid_result_parsed(self):
        records = self._source().raw_results_to_records([self._raw()], self._athlete())
        assert len(records) == 1
        r = records[0]
        assert r.event_distance == 100
        assert r.event_stroke == "freestyle"
        assert r.event_gender == "M"
        assert r.time_seconds == pytest.approx(47.02)
        assert r.course == "LCM"

    def test_relay_skipped(self):
        raw = [self._raw(DisciplineName="Men's 4x100m Freestyle Relay")]
        assert self._source().raw_results_to_records(raw, self._athlete()) == []

    def test_missing_time_skipped(self):
        raw = [self._raw(Time="")]
        assert self._source().raw_results_to_records(raw, self._athlete()) == []

    def test_invalid_time_skipped(self):
        raw = [self._raw(Time="DQ")]
        assert self._source().raw_results_to_records(raw, self._athlete()) == []

    def test_scm_competition_inferred(self):
        raw = [self._raw(CompetitionName="World Championships (25m)")]
        records = self._source().raw_results_to_records(raw, self._athlete())
        assert records[0].course == "SCM"

    def test_unknown_discipline_skipped(self):
        raw = [self._raw(DisciplineName="Men's 100m Crawl")]
        assert self._source().raw_results_to_records(raw, self._athlete()) == []
