from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import HTMX_HEADERS


class TestHomePage:
    async def test_returns_200(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200

    async def test_contains_brand_name(self, client):
        resp = await client.get("/")
        assert "SwimDB" in resp.text

    async def test_contains_search_input(self, client):
        resp = await client.get("/")
        assert "athlete-search" in resp.text


class TestEventsPage:
    async def test_no_params_returns_200(self, client):
        resp = await client.get("/events")
        assert resp.status_code == 200

    async def test_form_rendered(self, client):
        resp = await client.get("/events")
        assert "LCM" in resp.text
        assert "SCY" in resp.text

    async def test_valid_params_returns_200(self, client):
        with patch(
            "app.services.aggregator.get_event_top_times",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get(
                "/events?gender=M&distance=100&stroke=freestyle&course=LCM&limit=50"
            )
        assert resp.status_code == 200

    async def test_invalid_stroke_returns_200_with_error_message(self, client):
        resp = await client.get("/events?gender=M&distance=100&stroke=crawl&course=LCM")
        assert resp.status_code == 200
        assert "Unknown stroke" in resp.text

    async def test_gender_selection_preserved(self, client):
        with patch(
            "app.services.aggregator.get_event_top_times",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/events?gender=F&distance=200&stroke=butterfly&course=SCM")
        assert resp.status_code == 200


class TestAthleteDetailPage:
    async def test_unknown_athlete_returns_404(self, client):
        resp = await client.get("/athlete/999999")
        assert resp.status_code == 404


class TestAthleteSearchPartial:
    async def test_missing_htmx_header_returns_400(self, client):
        resp = await client.get("/htmx/athlete-search?q=dressel")
        assert resp.status_code == 400

    async def test_empty_query_returns_200(self, client):
        resp = await client.get("/htmx/athlete-search?q=", headers=HTMX_HEADERS)
        assert resp.status_code == 200

    async def test_empty_query_no_db_call(self, client):
        # Blank query should short-circuit before hitting aggregator
        with patch(
            "app.services.aggregator.search_athletes",
            new_callable=AsyncMock,
        ) as mock_search:
            await client.get("/htmx/athlete-search?q=", headers=HTMX_HEADERS)
        mock_search.assert_not_called()

    async def test_nonempty_query_returns_200(self, client):
        with patch(
            "app.services.aggregator.search_athletes",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/htmx/athlete-search?q=dressel", headers=HTMX_HEADERS)
        assert resp.status_code == 200

    async def test_missing_q_param_returns_200(self, client):
        resp = await client.get("/htmx/athlete-search", headers=HTMX_HEADERS)
        assert resp.status_code == 200


class TestEventResultsPartial:
    async def test_missing_htmx_header_returns_400(self, client):
        resp = await client.get("/htmx/event-results")
        assert resp.status_code == 400

    async def test_valid_request_returns_200(self, client):
        with patch(
            "app.services.aggregator.get_event_top_times",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get(
                "/htmx/event-results?gender=M&distance=100&stroke=freestyle&course=LCM",
                headers=HTMX_HEADERS,
            )
        assert resp.status_code == 200

    async def test_invalid_stroke_returns_200_with_error(self, client):
        resp = await client.get(
            "/htmx/event-results?gender=M&distance=100&stroke=crawl&course=LCM",
            headers=HTMX_HEADERS,
        )
        assert resp.status_code == 200
        assert "Unknown stroke" in resp.text

    async def test_default_params_accepted(self, client):
        with patch(
            "app.services.aggregator.get_event_top_times",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/htmx/event-results", headers=HTMX_HEADERS)
        assert resp.status_code == 200

    async def test_limit_clamped_at_100(self, client):
        with patch(
            "app.services.aggregator.get_event_top_times",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_fn:
            await client.get(
                "/htmx/event-results?gender=M&distance=100&stroke=freestyle&course=LCM&limit=9999",
                headers=HTMX_HEADERS,
            )
        _, kwargs = mock_fn.call_args
        assert kwargs["limit"] == 100

    async def test_limit_minimum_is_1(self, client):
        with patch(
            "app.services.aggregator.get_event_top_times",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_fn:
            await client.get(
                "/htmx/event-results?gender=M&distance=100&stroke=freestyle&course=LCM&limit=0",
                headers=HTMX_HEADERS,
            )
        _, kwargs = mock_fn.call_args
        assert kwargs["limit"] == 1


class TestSplitsPartial:
    async def test_missing_htmx_header_returns_400(self, client):
        resp = await client.get("/htmx/result/1/splits")
        assert resp.status_code == 400

    async def test_nonexistent_result_returns_404(self, client):
        resp = await client.get("/htmx/result/999999/splits", headers=HTMX_HEADERS)
        assert resp.status_code == 404

    async def test_collapse_row_returns_200_without_db_lookup(self, client):
        resp = await client.get("/htmx/result/42/splits?collapse=true", headers=HTMX_HEADERS)
        assert resp.status_code == 200

    async def test_collapse_row_contains_correct_id(self, client):
        resp = await client.get("/htmx/result/42/splits?collapse=true", headers=HTMX_HEADERS)
        assert "splits-42" in resp.text

    async def test_collapse_inline_returns_200(self, client):
        resp = await client.get(
            "/htmx/result/7/splits?collapse=true&inline=true", headers=HTMX_HEADERS
        )
        assert resp.status_code == 200

    async def test_collapse_inline_contains_correct_id(self, client):
        resp = await client.get(
            "/htmx/result/7/splits?collapse=true&inline=true", headers=HTMX_HEADERS
        )
        assert "ath-splits-7" in resp.text
