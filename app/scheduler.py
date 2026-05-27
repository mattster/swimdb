"""Background scheduler — pre-warms World Aquatics event cache on startup and every 24h."""
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

log = logging.getLogger(__name__)

# Events to pre-fetch from World Aquatics (LCM + SCM, both genders)
_PREWARM_EVENTS: list[tuple[str, int, str, str]] = [
    # (gender, distance, stroke, course)
    # --- LCM ---
    ("M", 50,   "freestyle",    "LCM"),
    ("M", 100,  "freestyle",    "LCM"),
    ("M", 200,  "freestyle",    "LCM"),
    ("M", 400,  "freestyle",    "LCM"),
    ("M", 800,  "freestyle",    "LCM"),
    ("M", 1500, "freestyle",    "LCM"),
    ("M", 50,   "backstroke",   "LCM"),
    ("M", 100,  "backstroke",   "LCM"),
    ("M", 200,  "backstroke",   "LCM"),
    ("M", 50,   "breaststroke", "LCM"),
    ("M", 100,  "breaststroke", "LCM"),
    ("M", 200,  "breaststroke", "LCM"),
    ("M", 50,   "butterfly",    "LCM"),
    ("M", 100,  "butterfly",    "LCM"),
    ("M", 200,  "butterfly",    "LCM"),
    ("M", 200,  "im",           "LCM"),
    ("M", 400,  "im",           "LCM"),
    ("F", 50,   "freestyle",    "LCM"),
    ("F", 100,  "freestyle",    "LCM"),
    ("F", 200,  "freestyle",    "LCM"),
    ("F", 400,  "freestyle",    "LCM"),
    ("F", 800,  "freestyle",    "LCM"),
    ("F", 1500, "freestyle",    "LCM"),
    ("F", 50,   "backstroke",   "LCM"),
    ("F", 100,  "backstroke",   "LCM"),
    ("F", 200,  "backstroke",   "LCM"),
    ("F", 50,   "breaststroke", "LCM"),
    ("F", 100,  "breaststroke", "LCM"),
    ("F", 200,  "breaststroke", "LCM"),
    ("F", 50,   "butterfly",    "LCM"),
    ("F", 100,  "butterfly",    "LCM"),
    ("F", 200,  "butterfly",    "LCM"),
    ("F", 200,  "im",           "LCM"),
    ("F", 400,  "im",           "LCM"),
    # --- SCM ---
    ("M", 50,   "freestyle",    "SCM"),
    ("M", 100,  "freestyle",    "SCM"),
    ("M", 200,  "freestyle",    "SCM"),
    ("M", 50,   "backstroke",   "SCM"),
    ("M", 100,  "backstroke",   "SCM"),
    ("M", 50,   "breaststroke", "SCM"),
    ("M", 100,  "breaststroke", "SCM"),
    ("M", 50,   "butterfly",    "SCM"),
    ("M", 100,  "butterfly",    "SCM"),
    ("M", 200,  "im",           "SCM"),
    ("F", 50,   "freestyle",    "SCM"),
    ("F", 100,  "freestyle",    "SCM"),
    ("F", 200,  "freestyle",    "SCM"),
    ("F", 50,   "backstroke",   "SCM"),
    ("F", 100,  "backstroke",   "SCM"),
    ("F", 50,   "breaststroke", "SCM"),
    ("F", 100,  "breaststroke", "SCM"),
    ("F", 50,   "butterfly",    "SCM"),
    ("F", 100,  "butterfly",    "SCM"),
    ("F", 200,  "im",           "SCM"),
]


async def _prewarm_cache(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Fetch and cache World Aquatics rankings for all pre-warm events."""
    from app.services.world_aquatics import WorldAquaticsSource

    source = WorldAquaticsSource()
    ok = 0
    fail = 0

    async with session_factory() as session:
        for gender, distance, stroke, course in _PREWARM_EVENTS:
            try:
                rows = await source.get_event_top_times(
                    gender=gender,
                    distance=distance,
                    stroke=stroke,
                    course=course,
                    limit=100,
                    session=session,
                )
                log.debug(
                    "Prewarm: %s %s %s %s → %d rows", gender, distance, stroke, course, len(rows)
                )
                ok += 1
            except Exception as exc:
                log.warning(
                    "Prewarm failed: %s %s %s %s — %s", gender, distance, stroke, course, exc
                )
                fail += 1

    log.info("Cache pre-warm complete: %d ok, %d failed", ok, fail)


def create_scheduler(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIOScheduler:
    """Create and configure the background scheduler."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _prewarm_cache,
        trigger="interval",
        hours=24,
        next_run_time=datetime.now(),  # run once immediately on startup
        args=[session_factory],
        id="prewarm_cache",
        name="Pre-warm World Aquatics event cache",
        misfire_grace_time=3600,
        coalesce=True,
    )
    return scheduler
