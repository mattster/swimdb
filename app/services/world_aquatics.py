"""World Aquatics public API adapter.

Rankings endpoint: https://api.worldaquatics.com/fina/rankings/swimming/report/csv
Athlete search:    https://api.worldaquatics.com/fina/athletes?name={name}&limit=20
Athlete results:   https://api.worldaquatics.com/fina/athletes/{id}/results?limit=500&discipline=SW

All endpoints require a browser-like User-Agent header. No authentication otherwise.

Rankings CSV columns: meet_name, swim_time, swim_date, full_desc, team_code,
    team_short_name, full_name_computed, gender, birth_date, event_id,
    standard_name, RANK, Rank_Order, fina_points, meet_city, country_code
    (Note: country_code = meet venue country, team_code = athlete nation)

Results JSON fields: Rank, DisciplineName, CompetitionName, CompetitionCity,
    CompetitionCountry, Date, Time, NAT, ClubName, Points, PhaseName
"""
import csv
import io
import json
import logging
import re
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.base import DataSource
from app.services.normalizer import (
    AthleteRecord,
    MeetRecord,
    ResultRecord,
    normalize_name,
    parse_time,
)

log = logging.getLogger(__name__)

_RANKINGS_URL = "https://api.worldaquatics.com/fina/rankings/swimming/report/csv"
_ATHLETES_URL = "https://api.worldaquatics.com/fina/athletes"

_STROKE_MAP = {
    "freestyle": "FREESTYLE",
    "backstroke": "BACKSTROKE",
    "breaststroke": "BREASTSTROKE",
    "butterfly": "BUTTERFLY",
    "im": "MEDLEY",
}

# Reverse map for parsing DisciplineName from athlete results
_DISCIPLINE_STROKE_MAP = {
    "freestyle": "freestyle",
    "backstroke": "backstroke",
    "breaststroke": "breaststroke",
    "butterfly": "butterfly",
    "medley": "im",
}

_TTL_RANKINGS = 3600 * 24   # 24 hours for global rankings
_TTL_ATHLETE = 3600 * 6     # 6 hours for athlete-specific results

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Regex to parse "Men's 100m Freestyle" → (gender, distance, stroke)
_DISCIPLINE_RE = re.compile(
    r"(?P<gender>Men|Women|Mixed)'s\s+(?P<distance>\d+)m?\s+(?P<stroke>\w+)",
    re.IGNORECASE,
)


def _parse_discipline(discipline_name: str) -> tuple[str, int, str] | None:
    """Parse DisciplineName → (gender, distance, stroke). Returns None for relays."""
    if "relay" in discipline_name.lower():
        return None
    m = _DISCIPLINE_RE.match(discipline_name)
    if not m:
        return None
    gender = "M" if m.group("gender").lower() == "men" else "F"
    distance = int(m.group("distance"))
    stroke_raw = m.group("stroke").lower()
    stroke = _DISCIPLINE_STROKE_MAP.get(stroke_raw)
    if not stroke:
        return None
    return gender, distance, stroke


def _infer_course(competition_name: str) -> str:
    """Infer pool course from competition name suffix."""
    name = competition_name.lower()
    if "(25m)" in name or "short course" in name or "(scm)" in name:
        return "SCM"
    if "(25yd)" in name or "(scy)" in name:
        return "SCY"
    return "LCM"  # default for World Aquatics events


class WorldAquaticsSource(DataSource):
    source_name = "world_aquatics"
    default_ttl_seconds = _TTL_RANKINGS

    async def search_athletes(
        self,
        name: str,
        session: AsyncSession | None = None,
    ) -> list[AthleteRecord]:
        cache_key = self._cache_key("athlete_search", name=name.lower())
        cached: str | None = None
        if session:
            cached = await self._get_cached(cache_key, session)

        if cached:
            items = json.loads(cached)
        else:
            items = await self._fetch_athlete_search(name)
            if session and items:
                await self._set_cached(cache_key, json.dumps(items), _TTL_ATHLETE, session)

        return [self._item_to_athlete_record(item) for item in items]

    async def _fetch_athlete_search(self, name: str) -> list[dict]:
        params = {"name": name, "limit": "30", "discipline": "SW"}
        log.info("World Aquatics athlete search: %s", name)
        async with httpx.AsyncClient(timeout=20.0, headers=_HEADERS) as client:
            resp = await client.get(_ATHLETES_URL, params=params)
            resp.raise_for_status()
        data = resp.json()
        return data.get("content", [])

    def _item_to_athlete_record(self, item: dict) -> AthleteRecord:
        dob = item.get("dateOfBirth", "")
        birth_year = int(dob[:4]) if dob and len(dob) >= 4 else None
        full_name = item.get("fullName", "")
        # WA returns "First LAST" — normalize to "first last"
        canonical = normalize_name(full_name)
        return AthleteRecord(
            canonical_name=canonical,
            gender=item.get("gender"),
            birth_year=birth_year,
            country_code=item.get("nationality"),
            world_aquatics_id=str(item["id"]),
            source=self.source_name,
        )

    async def get_athlete_meets(
        self,
        source_id: str,
        session: AsyncSession | None = None,
    ) -> list[ResultRecord]:
        """Fetch all individual (non-relay) swimming results for a WA athlete ID."""
        cache_key = self._cache_key("athlete_results", athlete_id=source_id)
        cached: str | None = None
        if session:
            cached = await self._get_cached(cache_key, session)

        if cached:
            raw_results = json.loads(cached)
        else:
            raw_results = await self._fetch_athlete_results(source_id)
            if session and raw_results:
                await self._set_cached(
                    cache_key, json.dumps(raw_results), _TTL_ATHLETE, session
                )

        return raw_results  # raw dicts; aggregator converts to ResultRecord

    async def _fetch_athlete_results(self, athlete_id: str) -> list[dict]:
        url = f"{_ATHLETES_URL}/{athlete_id}/results"
        params = {"limit": "500", "discipline": "SW"}
        log.info("World Aquatics athlete results: athlete_id=%s", athlete_id)
        async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        data = resp.json()
        return data.get("Results", [])

    def raw_results_to_records(
        self, raw_results: list[dict], athlete_record: AthleteRecord
    ) -> list[ResultRecord]:
        """Convert raw WA athlete results JSON to ResultRecord list."""
        records = []
        for r in raw_results:
            parsed = _parse_discipline(r.get("DisciplineName", ""))
            if parsed is None:
                continue  # skip relays and unparseable events
            gender, distance, stroke = parsed

            time_str = r.get("Time", "").strip()
            if not time_str:
                continue
            try:
                time_seconds = parse_time(time_str)
            except ValueError:
                continue

            comp_name = r.get("CompetitionName", "Unknown Meet")
            course = _infer_course(comp_name)
            iso_date = r.get("Date")  # already ISO format from WA

            meet = MeetRecord(
                name=comp_name,
                city=r.get("CompetitionCity"),
                country_code=r.get("CompetitionCountry"),
                course=course,
                level="international",
                source=self.source_name,
                start_date=iso_date,
            )
            records.append(
                ResultRecord(
                    athlete=athlete_record,
                    meet=meet,
                    event_distance=distance,
                    event_stroke=stroke,
                    event_gender=gender,
                    course=course,
                    time_seconds=time_seconds,
                    time_display=time_str,
                    swim_date=iso_date,
                    source=self.source_name,
                )
            )
        return records

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
        if course not in ("LCM", "SCM"):
            return []

        stroke_param = _STROKE_MAP.get(stroke)
        if not stroke_param:
            log.warning("Unknown stroke for World Aquatics: %s", stroke)
            return []

        cache_key = self._cache_key(
            "event_top_times",
            gender=gender,
            distance=distance,
            stroke=stroke,
            course=course,
            year=year or "all",
        )

        cached_payload: str | None = None
        if session:
            cached_payload = await self._get_cached(cache_key, session)

        if cached_payload:
            rows = json.loads(cached_payload)
        else:
            rows = await self._fetch_csv(gender, distance, stroke_param, course, year)
            if session and rows:
                await self._set_cached(cache_key, json.dumps(rows), _TTL_RANKINGS, session)

        return self._rows_to_results(rows[:limit], gender, distance, stroke, course)

    async def _fetch_csv(
        self,
        gender: str,
        distance: int,
        stroke_param: str,
        course: str,
        year: int | None,
    ) -> list[dict]:
        params = {
            "gender": gender,
            "stroke": stroke_param,
            "distance": str(distance),
            "poolConfiguration": course,
            "timesMode": "BEST_TIMES",
            "pageSize": "100",
            "year": str(year) if year else "",
            "startDate": "",
            "endDate": "",
            "regionId": "",
            "countryId": "",
        }
        log.info("Fetching World Aquatics rankings: %s", params)
        async with httpx.AsyncClient(timeout=30.0, headers=_HEADERS) as client:
            resp = await client.get(_RANKINGS_URL, params=params)
            resp.raise_for_status()

        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)

    def _rows_to_results(
        self,
        rows: list[dict],
        gender: str,
        distance: int,
        stroke: str,
        course: str,
    ) -> list[ResultRecord]:
        results = []
        for row in rows:
            try:
                name = row.get("full_name_computed", "").strip()
                time_str = row.get("swim_time", "").strip()
                meet_name = row.get("meet_name", "Unknown Meet").strip()
                swim_date = row.get("swim_date", "").strip()
                athlete_country = row.get("team_code", "").strip()
                meet_country = row.get("country_code", "").strip()
                meet_city = row.get("meet_city", "").strip()

                if not name or not time_str:
                    continue

                time_seconds = parse_time(time_str)
            except (ValueError, KeyError) as e:
                log.debug("Skipping row due to parse error: %s — %s", row, e)
                continue

            athlete = AthleteRecord(
                canonical_name=normalize_name(name),
                gender=gender,
                country_code=athlete_country[:3] if athlete_country else None,
                source=self.source_name,
            )
            iso_date = self._parse_date(swim_date)
            meet = MeetRecord(
                name=meet_name,
                city=meet_city or None,
                country_code=meet_country[:3] if meet_country else None,
                course=course,
                level="international",
                source=self.source_name,
                start_date=iso_date,
            )
            results.append(
                ResultRecord(
                    athlete=athlete,
                    meet=meet,
                    event_distance=distance,
                    event_stroke=stroke,
                    event_gender=gender,
                    course=course,
                    time_seconds=time_seconds,
                    time_display=time_str,
                    swim_date=iso_date,
                    source=self.source_name,
                )
            )
        return sorted(results, key=lambda r: r.time_seconds)

    @staticmethod
    def _parse_date(raw: str) -> str | None:
        if not raw:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%d %b %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                continue
        return None
