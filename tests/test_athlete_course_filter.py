"""Tests for the athlete results course filter (partial endpoint + template)."""
from datetime import date

import pytest

from app.models.athlete import Athlete
from app.models.meet import Meet
from app.models.result import Result
from tests.conftest import HTMX_HEADERS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def athlete_with_results(db_session):
    """An athlete with one result per course (LCM, SCM, SCY)."""
    athlete = Athlete(canonical_name="test swimmer", gender="M", country_code="USA")
    db_session.add(athlete)
    await db_session.flush()

    for course in ("LCM", "SCM", "SCY"):
        meet = Meet(
            name=f"Test Meet {course}",
            course=course,
            level="international",
            source="test",
        )
        db_session.add(meet)
        await db_session.flush()

        result = Result(
            athlete_id=athlete.id,
            meet_id=meet.id,
            event_distance=100,
            event_stroke="freestyle",
            event_gender="M",
            course=course,
            time_seconds=47.0,
            time_display="47.00",
            swim_date=date(2024, 6, 1),
            source="test",
        )
        db_session.add(result)

    await db_session.commit()
    return athlete


# ---------------------------------------------------------------------------
# Endpoint access control
# ---------------------------------------------------------------------------

class TestAthleteResultsPartialAccess:
    async def test_missing_htmx_header_returns_400(self, client, athlete_with_results):
        resp = await client.get(f"/htmx/athlete/{athlete_with_results.id}/results")
        assert resp.status_code == 400

    async def test_with_htmx_header_returns_200(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results?course=LCM",
            headers=HTMX_HEADERS,
        )
        assert resp.status_code == 200

    async def test_unknown_athlete_returns_empty_results(self, client):
        resp = await client.get(
            "/htmx/athlete/999999/results?course=LCM",
            headers=HTMX_HEADERS,
        )
        assert resp.status_code == 200
        assert "No results" in resp.text


# ---------------------------------------------------------------------------
# Course filtering logic
# ---------------------------------------------------------------------------

class TestAthleteResultsCourseFilter:
    async def test_all_courses_shows_all_results(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results"
            "?course=LCM&course=SCM&course=SCY",
            headers=HTMX_HEADERS,
        )
        assert resp.status_code == 200
        text = resp.text
        assert "LCM" in text
        assert "SCM" in text
        assert "SCY" in text

    async def test_lcm_only_shows_lcm_results(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results?course=LCM",
            headers=HTMX_HEADERS,
        )
        text = resp.text
        assert "LCM" in text
        assert "SCM" not in text
        assert "SCY" not in text

    async def test_scm_only_shows_scm_results(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results?course=SCM",
            headers=HTMX_HEADERS,
        )
        text = resp.text
        assert "SCM" in text
        assert "LCM" not in text
        assert "SCY" not in text

    async def test_scy_only_shows_scy_results(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results?course=SCY",
            headers=HTMX_HEADERS,
        )
        text = resp.text
        assert "SCY" in text
        assert "LCM" not in text
        assert "SCM" not in text

    async def test_two_courses_shows_only_those(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results?course=LCM&course=SCY",
            headers=HTMX_HEADERS,
        )
        text = resp.text
        assert "LCM" in text
        assert "SCY" in text
        assert "SCM" not in text

    async def test_no_courses_selected_shows_message(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results",
            headers=HTMX_HEADERS,
        )
        assert resp.status_code == 200
        assert "Select at least one course" in resp.text

    async def test_invalid_course_value_returns_empty(self, client, athlete_with_results):
        resp = await client.get(
            f"/htmx/athlete/{athlete_with_results.id}/results?course=INVALID",
            headers=HTMX_HEADERS,
        )
        assert resp.status_code == 200
        assert "No results" in resp.text


# ---------------------------------------------------------------------------
# Template: athlete_detail.html contains the filter UI
# ---------------------------------------------------------------------------

class TestAthleteDetailFilterUI:
    async def test_detail_page_has_course_checkboxes(self, client, athlete_with_results):
        from unittest.mock import AsyncMock, patch

        with patch(
            "app.services.aggregator.get_athlete_detail",
            new_callable=AsyncMock,
            return_value=athlete_with_results,
        ), patch(
            "app.services.aggregator.get_athlete_results",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get(f"/athlete/{athlete_with_results.id}")

        assert resp.status_code == 200
        text = resp.text
        # All three course checkboxes present
        assert 'value="LCM"' in text
        assert 'value="SCM"' in text
        assert 'value="SCY"' in text
        # All checked by default
        assert text.count('type="checkbox"') == 3
        assert text.count("checked") >= 3

    async def test_detail_page_filter_targets_results_div(self, client, athlete_with_results):
        from unittest.mock import AsyncMock, patch

        with patch(
            "app.services.aggregator.get_athlete_detail",
            new_callable=AsyncMock,
            return_value=athlete_with_results,
        ), patch(
            "app.services.aggregator.get_athlete_results",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get(f"/athlete/{athlete_with_results.id}")

        assert 'id="athlete-results"' in resp.text
        assert 'hx-target="#athlete-results"' in resp.text
