import pytest

from app.services.normalizer import (
    AthleteRecord,
    deduplicate_athletes,
    format_time,
    normalize_gender,
    normalize_name,
    normalize_stroke,
    parse_time,
)


class TestNormalizeName:
    def test_basic(self):
        assert normalize_name("John Smith") == "john smith"

    def test_lowercase(self):
        assert normalize_name("CAELEB DRESSEL") == "caeleb dressel"

    def test_diacritics_stripped(self):
        assert normalize_name("Léon Marchand") == "leon marchand"

    def test_multiple_diacritics(self):
        assert normalize_name("Kristóf Milák") == "kristof milak"

    def test_last_first_swapped(self):
        assert normalize_name("Smith, John") == "john smith"

    def test_last_first_preserves_multipart_first_name(self):
        assert normalize_name("van den Berg, Sharon") == "sharon van den berg"

    def test_extra_whitespace_collapsed(self):
        assert normalize_name("  John   Smith  ") == "john smith"

    def test_already_normalized(self):
        assert normalize_name("john smith") == "john smith"


class TestParseTime:
    def test_seconds_only(self):
        assert parse_time("45.23") == pytest.approx(45.23)

    def test_minutes_and_seconds(self):
        assert parse_time("1:45.23") == pytest.approx(105.23)

    def test_hours_minutes_seconds(self):
        assert parse_time("1:02:03.45") == pytest.approx(3723.45)

    def test_zero_minutes(self):
        assert parse_time("0:47.50") == pytest.approx(47.50)

    def test_leading_and_trailing_whitespace(self):
        assert parse_time("  1:45.23  ") == pytest.approx(105.23)

    def test_integer_seconds(self):
        assert parse_time("50") == pytest.approx(50.0)

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Cannot parse swim time"):
            parse_time("not-a-time")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_time("")

    def test_world_record_100_free(self):
        assert parse_time("46.40") == pytest.approx(46.40)

    def test_long_distance_time(self):
        assert parse_time("14:31.02") == pytest.approx(871.02)


class TestFormatTime:
    def test_none_returns_em_dash(self):
        assert format_time(None) == "—"

    def test_seconds_only(self):
        assert format_time(47.50) == "47.50"

    def test_with_minutes(self):
        assert format_time(105.23) == "1:45.23"

    def test_exactly_one_minute(self):
        assert format_time(60.0) == "1:00.00"

    def test_single_digit_seconds_zero_padded(self):
        assert format_time(65.05) == "1:05.05"

    def test_zero_seconds(self):
        assert format_time(0.0) == "0.00"


class TestNormalizeStroke:
    @pytest.mark.parametrize("raw,expected", [
        ("freestyle", "freestyle"),
        ("free", "freestyle"),
        ("FR", "freestyle"),
        ("f", "freestyle"),
        ("backstroke", "backstroke"),
        ("back", "backstroke"),
        ("BK", "backstroke"),
        ("breaststroke", "breaststroke"),
        ("breast", "breaststroke"),
        ("BR", "breaststroke"),
        ("butterfly", "butterfly"),
        ("fly", "butterfly"),
        ("BU", "butterfly"),
        ("im", "im"),
        ("IM", "im"),
        ("individual medley", "im"),
        ("medley", "im"),
    ])
    def test_known_aliases(self, raw, expected):
        assert normalize_stroke(raw) == expected

    def test_unknown_stroke_raises(self):
        with pytest.raises(ValueError, match="Unknown stroke"):
            normalize_stroke("crawl")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            normalize_stroke("xyz_not_a_stroke")


class TestNormalizeGender:
    @pytest.mark.parametrize("raw,expected", [
        ("m", "M"),
        ("male", "M"),
        ("men", "M"),
        ("men's", "M"),
        ("M", "M"),
        ("f", "F"),
        ("female", "F"),
        ("women", "F"),
        ("women's", "F"),
        ("w", "F"),
        ("F", "F"),
    ])
    def test_known_aliases(self, raw, expected):
        assert normalize_gender(raw) == expected


class TestDeduplicateAthletes:
    def _make(self, name, birth_year=None, **kwargs):
        return AthleteRecord(canonical_name=name, birth_year=birth_year, **kwargs)

    def test_empty_list(self):
        assert deduplicate_athletes([]) == []

    def test_single_record_unchanged(self):
        records = [self._make("caeleb dressel")]
        result = deduplicate_athletes(records)
        assert len(result) == 1

    def test_identical_names_merged(self):
        records = [
            self._make("caeleb dressel", world_aquatics_id="123"),
            self._make("caeleb dressel", swimrankings_id="456"),
        ]
        result = deduplicate_athletes(records)
        assert len(result) == 1
        assert result[0].world_aquatics_id == "123"
        assert result[0].swimrankings_id == "456"

    def test_different_names_not_merged(self):
        records = [
            self._make("caeleb dressel"),
            self._make("leon marchand"),
        ]
        result = deduplicate_athletes(records)
        assert len(result) == 2

    def test_similar_names_same_birth_year_merged(self):
        # Small typo — similarity still >= 0.85
        records = [
            self._make("caeleb dressel", birth_year=1996),
            self._make("caeleb dresel", birth_year=1996),
        ]
        result = deduplicate_athletes(records)
        assert len(result) == 1

    def test_same_name_different_birth_year_not_merged(self):
        records = [
            self._make("john smith", birth_year=1990),
            self._make("john smith", birth_year=2000),
        ]
        result = deduplicate_athletes(records)
        assert len(result) == 2

    def test_missing_birth_year_treated_as_match(self):
        records = [
            self._make("caeleb dressel", birth_year=None),
            self._make("caeleb dressel", birth_year=1996),
        ]
        result = deduplicate_athletes(records)
        assert len(result) == 1

    def test_backfills_birth_year_from_duplicate(self):
        records = [
            self._make("caeleb dressel", birth_year=None),
            self._make("caeleb dressel", birth_year=1996),
        ]
        result = deduplicate_athletes(records)
        assert result[0].birth_year == 1996

    def test_backfills_country_code(self):
        records = [
            self._make("caeleb dressel", country_code=None),
            self._make("caeleb dressel", country_code="USA"),
        ]
        result = deduplicate_athletes(records)
        assert result[0].country_code == "USA"

    def test_keeps_first_country_if_both_present(self):
        records = [
            self._make("caeleb dressel", country_code="USA"),
            self._make("caeleb dressel", country_code="AUS"),
        ]
        result = deduplicate_athletes(records)
        assert result[0].country_code == "USA"

    def test_very_different_names_not_merged(self):
        records = [
            self._make("adam peaty"),
            self._make("leon marchand"),
        ]
        result = deduplicate_athletes(records)
        assert len(result) == 2
