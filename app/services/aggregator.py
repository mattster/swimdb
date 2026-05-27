"""Central fan-out layer — all routes call only this module."""
import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.athlete import Athlete
from app.models.meet import Meet
from app.models.result import Result, Split
from app.services.normalizer import (
    AthleteRecord,
    ResultRecord,
    deduplicate_athletes,
    normalize_name,
)
from app.services.usa_swimming import USASwimmingSource
from app.services.world_aquatics import WorldAquaticsSource

log = logging.getLogger(__name__)

_world_aquatics = WorldAquaticsSource()
_usa_swimming = USASwimmingSource()

_SOURCES_BY_COURSE = {
    "LCM": [_world_aquatics],
    "SCM": [_world_aquatics],
    "SCY": [_usa_swimming],
}


# ---------------------------------------------------------------------------
# Athlete search
# ---------------------------------------------------------------------------

async def search_athletes(name: str, session: AsyncSession) -> list[Athlete]:
    """Search athletes: checks DB first, then fetches from WA API if sparse results."""
    norm = normalize_name(name)
    q = f"%{norm}%"
    db_rows = list(
        await session.scalars(
            select(Athlete).where(Athlete.canonical_name.ilike(q)).limit(50)
        )
    )
    if db_rows:
        return db_rows

    # Not in cache — fetch from World Aquatics and persist
    wa_records = await _world_aquatics.search_athletes(name, session)
    if not wa_records:
        return []

    deduped = deduplicate_athletes(wa_records)
    athletes = []
    for rec in deduped:
        athlete = await _get_or_create_athlete(rec, session)
        athletes.append(athlete)
    await session.commit()
    return athletes


# ---------------------------------------------------------------------------
# Athlete detail
# ---------------------------------------------------------------------------

async def get_athlete_detail(athlete_id: int, session: AsyncSession) -> Athlete | None:
    """Load an athlete + all their results. Fetches from WA if results not yet cached."""
    athlete = await session.scalar(
        select(Athlete).where(Athlete.id == athlete_id)
    )
    if not athlete:
        return None

    # Check if we already have results for this athlete
    existing_count = await session.scalar(
        select(Result.id).where(Result.athlete_id == athlete_id).limit(1)
    )

    if not existing_count and athlete.world_aquatics_id:
        await _fetch_and_store_athlete_results(athlete, session)

    return athlete


async def _fetch_and_store_athlete_results(athlete: Athlete, session: AsyncSession) -> None:
    """Fetch WA athlete results and persist them to the DB."""
    wa_id = athlete.world_aquatics_id
    if not wa_id:
        return

    raw_results = await _world_aquatics.get_athlete_meets(wa_id, session)

    athlete_rec = AthleteRecord(
        canonical_name=athlete.canonical_name,
        gender=athlete.gender,
        birth_year=athlete.birth_year,
        country_code=athlete.country_code,
        world_aquatics_id=wa_id,
        source="world_aquatics",
    )

    result_records = _world_aquatics.raw_results_to_records(raw_results, athlete_rec)

    for rec in result_records:
        meet = await _get_or_create_meet(rec.meet, session)
        await _get_or_create_result(rec, athlete.id, meet.id, session)

    await session.commit()


async def get_athlete_results(athlete_id: int, session: AsyncSession) -> list[Result]:
    """Return all results for an athlete ordered by date desc, with relationships loaded."""
    results = await session.scalars(
        select(Result)
        .where(Result.athlete_id == athlete_id)
        .options(selectinload(Result.meet), selectinload(Result.splits))
        .order_by(Result.swim_date.desc())
    )
    return list(results)


# ---------------------------------------------------------------------------
# Event top times
# ---------------------------------------------------------------------------

async def get_event_top_times(
    gender: str,
    distance: int,
    stroke: str,
    course: str,
    limit: int,
    year: int | None,
    session: AsyncSession,
) -> list[Result]:
    sources = _SOURCES_BY_COURSE.get(course, [])
    if not sources:
        return []

    # Only serve from the results table when a fresh source-cache entry exists.
    # Without this guard, rows stored from individual athlete lookups would
    # satisfy the query and prevent a proper ranked list from being fetched.
    if await _event_cache_is_fresh(gender, distance, stroke, course, year, sources, session):
        db_results = await _load_results_from_db(
            gender, distance, stroke, course, limit, year, session
        )
        if db_results:
            return db_results

    fetch_tasks = [
        src.get_event_top_times(gender, distance, stroke, course, limit, year, session)
        for src in sources
    ]
    results_per_source: list[list[ResultRecord]] = await asyncio.gather(*fetch_tasks)

    all_records: list[ResultRecord] = []
    for records in results_per_source:
        all_records.extend(records)

    all_records.sort(key=lambda r: r.time_seconds)
    top_records = all_records[:limit]

    orm_results = await _upsert_results(top_records, session)
    return orm_results[:limit]


async def _event_cache_is_fresh(
    gender: str,
    distance: int,
    stroke: str,
    course: str,
    year: int | None,
    sources: list,
    session: AsyncSession,
) -> bool:
    """Return True if at least one source has a live cache entry for this event."""
    for src in sources:
        cache_key = src._cache_key(
            "event_top_times",
            gender=gender,
            distance=distance,
            stroke=stroke,
            course=course,
            year=year or "all",
        )
        if await src._get_cached(cache_key, session):
            return True
    return False


async def _load_results_from_db(
    gender: str,
    distance: int,
    stroke: str,
    course: str,
    limit: int,
    year: int | None,
    session: AsyncSession,
) -> list[Result]:
    q = (
        select(Result)
        .where(
            Result.event_gender == gender,
            Result.event_distance == distance,
            Result.event_stroke == stroke,
            Result.course == course,
        )
        .options(
            selectinload(Result.athlete),
            selectinload(Result.meet),
            selectinload(Result.splits),
        )
        .order_by(Result.time_seconds)
        .limit(limit)
    )
    if year:
        q = q.where(
            Result.swim_date >= date(year, 1, 1).isoformat(),
            Result.swim_date <= date(year, 12, 31).isoformat(),
        )
    rows = await session.scalars(q)
    return list(rows)


# ---------------------------------------------------------------------------
# DB upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_results(records: list[ResultRecord], session: AsyncSession) -> list[Result]:
    orm_results = []
    for rec in records:
        athlete = await _get_or_create_athlete(rec.athlete, session)
        meet = await _get_or_create_meet(rec.meet, session)
        result = await _get_or_create_result(rec, athlete.id, meet.id, session)
        orm_results.append(result)
    return orm_results


async def _get_or_create_athlete(rec: AthleteRecord, session: AsyncSession) -> Athlete:
    # Prefer lookup by stable external ID
    existing = None
    if rec.world_aquatics_id:
        existing = await session.scalar(
            select(Athlete).where(Athlete.world_aquatics_id == rec.world_aquatics_id)
        )
    if not existing and rec.swimrankings_id:
        existing = await session.scalar(
            select(Athlete).where(Athlete.swimrankings_id == rec.swimrankings_id)
        )
    if not existing:
        existing = await session.scalar(
            select(Athlete).where(Athlete.canonical_name == rec.canonical_name)
        )
    if existing:
        # Backfill any IDs that weren't set before
        if rec.world_aquatics_id and not existing.world_aquatics_id:
            existing.world_aquatics_id = rec.world_aquatics_id
        return existing

    athlete = Athlete(
        canonical_name=rec.canonical_name,
        gender=rec.gender,
        birth_year=rec.birth_year,
        country_code=rec.country_code,
        swim_club_name=rec.swim_club_name,
        swim_club_abbr=rec.swim_club_abbr,
        world_aquatics_id=rec.world_aquatics_id,
        swimrankings_id=rec.swimrankings_id,
        swimcloud_id=rec.swimcloud_id,
        usas_id=rec.usas_id,
    )
    session.add(athlete)
    await session.flush()
    return athlete


async def _get_or_create_meet(rec, session: AsyncSession) -> Meet:
    existing = None
    if rec.source_meet_id:
        existing = await session.scalar(
            select(Meet).where(
                Meet.source == rec.source,
                Meet.source_meet_id == rec.source_meet_id,
            )
        )
    if not existing:
        existing = await session.scalar(
            select(Meet).where(
                Meet.name == rec.name,
                Meet.start_date == (date.fromisoformat(rec.start_date) if rec.start_date else None),
            )
        )
    if existing:
        return existing

    meet = Meet(
        name=rec.name,
        city=rec.city,
        country_code=rec.country_code,
        start_date=date.fromisoformat(rec.start_date) if rec.start_date else None,
        end_date=date.fromisoformat(rec.end_date) if rec.end_date else None,
        course=rec.course,
        level=rec.level,
        source=rec.source,
        source_meet_id=rec.source_meet_id,
    )
    session.add(meet)
    await session.flush()
    return meet


async def _get_or_create_result(
    rec: ResultRecord, athlete_id: int, meet_id: int, session: AsyncSession
) -> Result:
    existing = None
    if rec.source_result_id:
        existing = await session.scalar(
            select(Result).where(
                Result.source == rec.source,
                Result.source_result_id == rec.source_result_id,
            )
        )
    if not existing:
        existing = await session.scalar(
            select(Result).where(
                Result.athlete_id == athlete_id,
                Result.meet_id == meet_id,
                Result.event_distance == rec.event_distance,
                Result.event_stroke == rec.event_stroke,
                Result.time_seconds == rec.time_seconds,
            )
        )
    if existing:
        return existing

    result = Result(
        athlete_id=athlete_id,
        meet_id=meet_id,
        event_distance=rec.event_distance,
        event_stroke=rec.event_stroke,
        event_gender=rec.event_gender,
        course=rec.course,
        time_seconds=rec.time_seconds,
        time_display=rec.time_display,
        swim_date=date.fromisoformat(rec.swim_date) if rec.swim_date else None,
        source=rec.source,
        source_result_id=rec.source_result_id,
    )
    session.add(result)
    await session.flush()

    for s in rec.splits:
        session.add(
            Split(
                result_id=result.id,
                split_number=s.split_number,
                distance_meters=s.distance_meters,
                cumulative_seconds=s.cumulative_seconds,
                lap_seconds=s.lap_seconds,
            )
        )

    await session.commit()

    result = await session.scalar(
        select(Result)
        .where(Result.id == result.id)
        .options(
            selectinload(Result.athlete),
            selectinload(Result.meet),
            selectinload(Result.splits),
        )
    )
    return result
