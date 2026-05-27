import pytest

from app.services.usa_swimming import USASwimmingSource, _season_year_to_date


class TestSeasonYearToDate:
    def test_valid_year_maps_to_aug_31(self):
        assert _season_year_to_date("2025") == "2025-08-31"

    def test_another_valid_year(self):
        assert _season_year_to_date("2022") == "2022-08-31"

    def test_invalid_string_returns_none(self):
        assert _season_year_to_date("not-a-year") is None

    def test_empty_string_returns_none(self):
        assert _season_year_to_date("") is None


class TestEventLabel:
    @pytest.mark.parametrize("distance,stroke,course,expected", [
        (50, "freestyle", "SCY", "50 FR SCY"),
        (100, "freestyle", "SCY", "100 FR SCY"),
        (200, "backstroke", "SCY", "200 BK SCY"),
        (100, "breaststroke", "SCY", "100 BR SCY"),
        (200, "breaststroke", "SCY", "200 BR SCY"),
        (50, "butterfly", "SCM", "50 FL SCM"),
        (200, "butterfly", "SCY", "200 FL SCY"),
        (400, "im", "SCY", "400 IM SCY"),
        (100, "im", "SCM", "100 IM SCM"),
        (100, "backstroke", "SCY", "100 BK SCY"),
    ])
    def test_label_format(self, distance, stroke, course, expected):
        assert USASwimmingSource._event_label(distance, stroke, course) == expected


class TestGetEventTopTimesEarlyReturn:
    async def test_unmapped_event_returns_empty(self):
        # 400 FR SCY is not in the event map (SCY uses 500 FR, not 400 FR)
        source = USASwimmingSource()
        result = await source.get_event_top_times("M", 400, "freestyle", "SCY")
        assert result == []

    async def test_lcm_course_returns_empty(self):
        # USAS only covers SCY and SCM
        source = USASwimmingSource()
        result = await source.get_event_top_times("M", 100, "freestyle", "LCM")
        assert result == []

    async def test_unmapped_scm_event_returns_empty(self):
        # 1000 FR SCM doesn't exist (SCM uses 800)
        source = USASwimmingSource()
        result = await source.get_event_top_times("M", 1000, "freestyle", "SCM")
        assert result == []


class TestRowsToRecords:
    def _source(self):
        return USASwimmingSource()

    def _row(self, **overrides):
        base = {
            "rank": "1",
            "time_display": "47.02",
            "name": "Caeleb Dressel",
            "foreign": "No",
            "age": "26",
            "event": "100 FR SCY",
            "lsc": "FL",
            "team": "Gator Swim Club",
            "meet": "US Nationals",
        }
        base.update(overrides)
        return base

    def test_valid_row_produces_record(self):
        records = self._source()._rows_to_records([self._row()], "M", 100, "freestyle", "SCY")
        assert len(records) == 1
        r = records[0]
        assert r.time_seconds == pytest.approx(47.02)
        assert r.time_display == "47.02"
        assert r.event_distance == 100
        assert r.event_stroke == "freestyle"
        assert r.event_gender == "M"
        assert r.course == "SCY"

    def test_domestic_athlete_has_usa_country_code(self):
        records = self._source()._rows_to_records([self._row(foreign="No")], "M", 100, "freestyle", "SCY")
        assert records[0].athlete.country_code == "USA"

    def test_foreign_athlete_has_no_country_code(self):
        records = self._source()._rows_to_records([self._row(foreign="Yes")], "M", 100, "freestyle", "SCY")
        assert records[0].athlete.country_code is None

    def test_invalid_time_skipped(self):
        records = self._source()._rows_to_records([self._row(time_display="NT")], "M", 100, "freestyle", "SCY")
        assert records == []

    def test_empty_time_skipped(self):
        records = self._source()._rows_to_records([self._row(time_display="")], "M", 100, "freestyle", "SCY")
        assert records == []

    def test_team_name_stored_on_athlete(self):
        records = self._source()._rows_to_records([self._row(team="Gator Swim Club")], "M", 100, "freestyle", "SCY")
        assert records[0].athlete.swim_club_name == "Gator Swim Club"

    def test_empty_team_stored_as_none(self):
        records = self._source()._rows_to_records([self._row(team="")], "M", 100, "freestyle", "SCY")
        assert records[0].athlete.swim_club_name is None

    def test_meet_name_stored(self):
        records = self._source()._rows_to_records([self._row(meet="US Open")], "M", 100, "freestyle", "SCY")
        assert records[0].meet.name == "US Open"

    def test_empty_meet_name_defaults(self):
        records = self._source()._rows_to_records([self._row(meet="")], "M", 100, "freestyle", "SCY")
        assert records[0].meet.name == "Unknown Meet"

    def test_name_normalized(self):
        records = self._source()._rows_to_records([self._row(name="DRESSEL, Caeleb")], "M", 100, "freestyle", "SCY")
        assert records[0].athlete.canonical_name == "caeleb dressel"

    def test_multiple_rows_all_converted(self):
        rows = [self._row(), self._row(name="Ryan Held", time_display="47.50")]
        records = self._source()._rows_to_records(rows, "M", 100, "freestyle", "SCY")
        assert len(records) == 2

    def test_mixed_valid_invalid_skips_invalid(self):
        rows = [self._row(time_display="47.02"), self._row(time_display="NT")]
        records = self._source()._rows_to_records(rows, "M", 100, "freestyle", "SCY")
        assert len(records) == 1
        assert records[0].time_seconds == pytest.approx(47.02)

    def test_source_name_set(self):
        records = self._source()._rows_to_records([self._row()], "M", 100, "freestyle", "SCY")
        assert records[0].source == "usa_swimming"

    def test_minutes_time_parsed(self):
        records = self._source()._rows_to_records([self._row(time_display="2:03.65")], "F", 200, "breaststroke", "SCY")
        assert records[0].time_seconds == pytest.approx(123.65)
