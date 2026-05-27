"""USA Swimming SWIMS 3.0 data hub Playwright adapter.

Scrapes the public event rank search at data.usaswimming.org/datahub/usas/timeseventrank.
No authentication required — the page is publicly accessible.

Event IDs come from the form's checkboxes; SCY and SCM are fully mapped.
The form auto-submits on field changes, so no explicit submit button is needed.
"""
import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.base import DataSource
from app.services.normalizer import AthleteRecord, MeetRecord, ResultRecord, normalize_name, parse_time

log = logging.getLogger(__name__)

_DATAHUB_URL = "https://data.usaswimming.org/datahub/usas/timeseventrank"
_TTL = 3600 * 6  # 6 hours

# (distance, stroke, course) → USAS form checkbox value
_EVENT_IDS: dict[tuple[int, str, str], int] = {
    # SCY
    (50, "freestyle", "SCY"): 1,
    (100, "freestyle", "SCY"): 2,
    (200, "freestyle", "SCY"): 3,
    (500, "freestyle", "SCY"): 4,
    (1000, "freestyle", "SCY"): 5,
    (1650, "freestyle", "SCY"): 6,
    (50, "backstroke", "SCY"): 11,
    (100, "backstroke", "SCY"): 12,
    (200, "backstroke", "SCY"): 13,
    (50, "breaststroke", "SCY"): 14,
    (100, "breaststroke", "SCY"): 15,
    (200, "breaststroke", "SCY"): 16,
    (50, "butterfly", "SCY"): 17,
    (100, "butterfly", "SCY"): 18,
    (200, "butterfly", "SCY"): 19,
    (100, "im", "SCY"): 20,
    (200, "im", "SCY"): 21,
    (400, "im", "SCY"): 22,
    # SCM
    (50, "freestyle", "SCM"): 28,
    (100, "freestyle", "SCM"): 29,
    (200, "freestyle", "SCM"): 30,
    (400, "freestyle", "SCM"): 31,
    (800, "freestyle", "SCM"): 32,
    (1500, "freestyle", "SCM"): 33,
    (50, "backstroke", "SCM"): 38,
    (100, "backstroke", "SCM"): 39,
    (200, "backstroke", "SCM"): 40,
    (50, "breaststroke", "SCM"): 41,
    (100, "breaststroke", "SCM"): 42,
    (200, "breaststroke", "SCM"): 43,
    (50, "butterfly", "SCM"): 44,
    (100, "butterfly", "SCM"): 45,
    (200, "butterfly", "SCM"): 46,
    (100, "im", "SCM"): 47,
    (200, "im", "SCM"): 48,
    (400, "im", "SCM"): 49,
}

# Approximate competition year for a USAS season year (Sept–Aug cycle)
# Season "2025" = Sept 2024 – Aug 2025 → use Aug end as representative date
def _season_year_to_date(comp_year: str) -> str | None:
    try:
        y = int(comp_year)
        return f"{y}-08-31"
    except ValueError:
        return None


class USASwimmingSource(DataSource):
    source_name = "usa_swimming"
    default_ttl_seconds = _TTL

    async def search_athletes(self, name: str, session: AsyncSession | None = None) -> list[AthleteRecord]:
        return []  # USAS data hub has no public athlete search endpoint

    async def get_athlete_meets(self, source_id: str, session: AsyncSession | None = None) -> list:
        return []

    async def get_event_top_times(
        self,
        gender: str,
        distance: int,
        stroke: str,
        course: str,
        limit: int = 100,
        year: int | None = None,
        session: AsyncSession | None = None,
    ) -> list[ResultRecord]:
        event_id = _EVENT_IDS.get((distance, stroke, course))
        if not event_id:
            return []

        comp_year = str(year) if year else str(datetime.now().year)
        gender_val = "Male" if gender == "M" else "Female"

        cache_key = self._cache_key(
            "event_top_times",
            gender=gender, distance=distance, stroke=stroke, course=course, year=comp_year,
        )
        if session:
            cached = await self._get_cached(cache_key, session)
            if cached:
                rows = json.loads(cached)
                return self._rows_to_records(rows[:limit], gender, distance, stroke, course)

        expected_label = self._event_label(distance, stroke, course)
        rows = await self._scrape_event_rank(event_id, gender_val, comp_year, limit, expected_label)
        if session and rows:
            await self._set_cached(cache_key, json.dumps(rows), _TTL, session)

        return self._rows_to_records(rows[:limit], gender, distance, stroke, course)

    @staticmethod
    def _event_label(distance: int, stroke: str, course: str) -> str:
        """Build the event label as shown in the USAS results table, e.g. '100 FR SCY'."""
        stroke_abbr = {"freestyle": "FR", "backstroke": "BK", "breaststroke": "BR", "butterfly": "FL", "im": "IM"}
        return f"{distance} {stroke_abbr.get(stroke, stroke.upper())} {course}"

    async def _scrape_event_rank(
        self, event_id: int, gender_val: str, comp_year: str, limit: int,
        expected_event_label: str = "",
    ) -> list[dict]:
        from playwright.async_api import Error as PlaywrightError, async_playwright

        log.info("USAS scraping event_id=%d gender=%s year=%s limit=%d", event_id, gender_val, comp_year, limit)

        try:
            return await self._scrape_event_rank_inner(
                event_id, gender_val, comp_year, limit, expected_event_label
            )
        except PlaywrightError as exc:
            log.warning("USAS Playwright scrape failed (event_id=%d): %s", event_id, exc)
            return []
        except Exception as exc:
            log.warning("USAS scrape unexpected error (event_id=%d): %s", event_id, exc)
            return []

    async def _scrape_event_rank_inner(
        self, event_id: int, gender_val: str, comp_year: str, limit: int,
        expected_event_label: str = "",
    ) -> list[dict]:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                await page.goto(_DATAHUB_URL, timeout=30000)
                await page.wait_for_selector('select[name="competitionYearId"]', timeout=20000)
                await page.wait_for_timeout(1500)

                # Select event FIRST to avoid the page auto-loading a default event
                await page.evaluate(
                    "(id) => document.querySelector(`input[name='events-tree'][value='${id}']`)?.click()",
                    event_id,
                )
                await page.wait_for_timeout(400)

                await page.select_option('select[name="competitionYearId"]', comp_year)
                await page.wait_for_timeout(400)
                await page.select_option('select[name="competitionCategoryId"]', gender_val)
                await page.wait_for_timeout(400)
                await page.select_option('select[name="ageGroupDescId"]', "0")  # Open
                await page.wait_for_timeout(400)
                await page.select_option('select[name="displayId"]', "1")  # Best Times Only
                await page.wait_for_timeout(400)

                await page.fill('input[name="maxResults"]', str(min(limit, 500)))
                await page.wait_for_timeout(400)

                # Collapse the filter panel to trigger a clean results render
                toggle_btn = await page.query_selector("button._ToggleButton_cfyju_23")
                if toggle_btn:
                    await toggle_btn.click()

                # Wait for the table to show results matching the expected event
                deadline = 15000
                poll_interval = 1500
                elapsed = 0
                rows = []
                while elapsed < deadline:
                    await page.wait_for_timeout(poll_interval)
                    elapsed += poll_interval
                    rows = await page.evaluate("""() => {
                        const table = document.querySelector("table");
                        if (!table) return [];
                        const result = [];
                        for (const tr of table.querySelectorAll("tbody tr")) {
                            const cells = Array.from(tr.querySelectorAll("td")).map(c => c.textContent.trim());
                            if (cells.length >= 9) {
                                result.push({
                                    rank: cells[0],
                                    time_display: cells[1],
                                    name: cells[2],
                                    foreign: cells[3],
                                    age: cells[4],
                                    event: cells[5],
                                    lsc: cells[6],
                                    team: cells[7],
                                    meet: cells[8],
                                });
                            }
                        }
                        return result;
                    }""")
                    if rows and (not expected_event_label or rows[0].get("event") == expected_event_label):
                        break
                    if rows and expected_event_label:
                        log.debug("USAS: table shows '%s', waiting for '%s'", rows[0].get("event"), expected_event_label)
                        # Re-click event checkbox to force re-query
                        await page.evaluate(
                            "(id) => document.querySelector(`input[name='events-tree'][value='${id}']`)?.click()",
                            event_id,
                        )
                        await page.wait_for_timeout(400)

                if expected_event_label and rows and rows[0].get("event") != expected_event_label:
                    log.warning("USAS: expected event '%s' but got '%s' — discarding", expected_event_label, rows[0].get("event"))
                    return []

                log.info("USAS scraped %d rows for %s", len(rows), expected_event_label)
                return rows
            finally:
                await browser.close()

    def _rows_to_records(
        self,
        rows: list[dict],
        gender: str,
        distance: int,
        stroke: str,
        course: str,
    ) -> list[ResultRecord]:
        records = []
        for row in rows:
            try:
                time_seconds = parse_time(row["time_display"])
            except ValueError:
                continue

            country = None if row.get("foreign") == "Yes" else "USA"
            athlete = AthleteRecord(
                canonical_name=normalize_name(row["name"]),
                gender=gender,
                country_code=country,
                swim_club_name=row.get("team") or None,
                source=self.source_name,
            )
            meet = MeetRecord(
                name=row.get("meet") or "Unknown Meet",
                country_code="USA",
                course=course,
                level="usas",
                source=self.source_name,
            )
            records.append(
                ResultRecord(
                    athlete=athlete,
                    meet=meet,
                    event_distance=distance,
                    event_stroke=stroke,
                    event_gender=gender,
                    course=course,
                    time_seconds=time_seconds,
                    time_display=row["time_display"],
                    source=self.source_name,
                )
            )
        return records
