import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher


def normalize_name(raw: str) -> str:
    """Lowercase, strip diacritics, normalize whitespace, swap 'Last, First' → 'First Last'."""
    # Strip diacritics
    nfkd = unicodedata.normalize("NFKD", raw)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    name = ascii_str.strip()
    # Swap "Last, First" → "First Last"
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        name = f"{parts[1]} {parts[0]}"
    return " ".join(name.lower().split())


def parse_time(display: str) -> float:
    """Convert formatted swim time string to total seconds.

    Accepts: '45.23', '1:45.23', '16:23.45'
    """
    display = display.strip()
    parts = display.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        raise ValueError(f"Cannot parse swim time: {display!r}")


def format_time(seconds: float | None) -> str:
    """Convert total seconds to formatted swim time string."""
    if seconds is None:
        return "—"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes:
        return f"{minutes}:{secs:05.2f}"
    return f"{secs:.2f}"


_STROKE_MAP: dict[str, str] = {
    # freestyle
    "free": "freestyle",
    "freestyle": "freestyle",
    "fr": "freestyle",
    "f": "freestyle",
    # backstroke
    "back": "backstroke",
    "backstroke": "backstroke",
    "bk": "backstroke",
    # breaststroke
    "breast": "breaststroke",
    "breaststroke": "breaststroke",
    "br": "breaststroke",
    # butterfly
    "fly": "butterfly",
    "butterfly": "butterfly",
    "bu": "butterfly",
    "bf": "butterfly",
    # IM
    "im": "im",
    "individual medley": "im",
    "medley": "im",
    "ind. medley": "im",
}


def normalize_stroke(raw: str) -> str:
    key = raw.strip().lower()
    result = _STROKE_MAP.get(key)
    if result:
        return result
    # Partial match fallback
    for k, v in _STROKE_MAP.items():
        if k in key or key in k:
            return v
    raise ValueError(f"Unknown stroke: {raw!r}")


_GENDER_MAP: dict[str, str] = {
    "m": "M", "male": "M", "men": "M", "men's": "M", "man": "M",
    "w": "F", "f": "F", "female": "F", "women": "F", "women's": "F", "woman": "F",
}


def normalize_gender(raw: str) -> str:
    return _GENDER_MAP.get(raw.strip().lower(), raw.upper()[0])


@dataclass
class AthleteRecord:
    canonical_name: str
    gender: str | None = None
    birth_year: int | None = None
    country_code: str | None = None
    swim_club_name: str | None = None
    swim_club_abbr: str | None = None
    world_aquatics_id: str | None = None
    swimrankings_id: str | None = None
    swimcloud_id: str | None = None
    usas_id: str | None = None
    source: str = ""


@dataclass
class MeetRecord:
    name: str
    course: str
    level: str
    source: str
    start_date: str | None = None    # ISO date string
    end_date: str | None = None
    city: str | None = None
    country_code: str | None = None  # meet venue country
    source_meet_id: str | None = None


@dataclass
class SplitRecord:
    split_number: int
    distance_meters: int
    cumulative_seconds: float | None = None
    lap_seconds: float | None = None


@dataclass
class ResultRecord:
    athlete: AthleteRecord
    meet: MeetRecord
    event_distance: int
    event_stroke: str
    event_gender: str
    course: str
    time_seconds: float
    time_display: str
    source: str
    swim_date: str | None = None    # ISO date string
    source_result_id: str | None = None
    splits: list[SplitRecord] = field(default_factory=list)


def deduplicate_athletes(records: list[AthleteRecord]) -> list[AthleteRecord]:
    """Merge records that refer to the same athlete across sources.

    Groups by normalized name similarity (>= 0.85) + birth_year match.
    Merges source IDs from all records in a group onto a single canonical record.
    """
    merged: list[AthleteRecord] = []
    used = [False] * len(records)

    for i, rec in enumerate(records):
        if used[i]:
            continue
        group = [rec]
        used[i] = True
        for j, other in enumerate(records[i + 1 :], start=i + 1):
            if used[j]:
                continue
            name_sim = SequenceMatcher(None, rec.canonical_name, other.canonical_name).ratio()
            years_match = (
                rec.birth_year is None
                or other.birth_year is None
                or rec.birth_year == other.birth_year
            )
            if name_sim >= 0.85 and years_match:
                group.append(other)
                used[j] = True

        # Merge group onto the first record
        canonical = group[0]
        for duplicate in group[1:]:
            if canonical.birth_year is None:
                canonical.birth_year = duplicate.birth_year
            if canonical.country_code is None:
                canonical.country_code = duplicate.country_code
            if canonical.swim_club_name is None:
                canonical.swim_club_name = duplicate.swim_club_name
            if canonical.swim_club_abbr is None:
                canonical.swim_club_abbr = duplicate.swim_club_abbr
            if canonical.swimrankings_id is None:
                canonical.swimrankings_id = duplicate.swimrankings_id
            if canonical.swimcloud_id is None:
                canonical.swimcloud_id = duplicate.swimcloud_id
            if canonical.usas_id is None:
                canonical.usas_id = duplicate.usas_id
        merged.append(canonical)

    return merged
