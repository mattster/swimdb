"""Shared Jinja2Templates instance with custom filters."""
from pathlib import Path

from fastapi.templating import Jinja2Templates


def format_time(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes:
        return f"{minutes}:{secs:05.2f}"
    return f"{secs:.2f}"


templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["format_time"] = format_time
