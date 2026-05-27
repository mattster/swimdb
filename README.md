# SwimDB

A web app for searching competitive swimming times across international, USA national, and college levels. Built with FastAPI, Jinja2, HTMX, and SQLite.

## Features

- **Athlete search** — typeahead search by name; click through to a full results page grouped by year with collapsible sections
- **Event top times** — ranked leaderboard for any event (distance + stroke + course + gender), with optional year filter
- **Splits expansion** — click any result row to expand lap splits inline; click again to collapse
- **Multi-course support** — LCM, SCM, and SCY (short course yards)
- **DB-backed caching** — scraped/fetched data is cached in SQLite with per-source TTLs to avoid redundant network calls

## Data Sources

| Course | Source | Method |
|--------|--------|--------|
| LCM, SCM | [World Aquatics](https://www.worldaquatics.com) | JSON API (httpx) |
| SCY, SCM | [USA Swimming SWIMS 3.0](https://data.usaswimming.org/datahub/usas/timeseventrank) | Playwright headless scraper |

Cache TTLs: World Aquatics rankings → 24h · Athlete results → 6h · USAS event rankings → 6h

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy (async) + aiosqlite
- **Templates:** Jinja2 + HTMX (no JavaScript frameworks)
- **Styling:** Tailwind CSS
- **Scraping:** Playwright (Chromium, headless)
- **Migrations:** Alembic

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright's Chromium browser (required for USA Swimming scraping)
playwright install chromium

# 4. Run the app
uvicorn app.main:app --reload
```

The app auto-creates the SQLite database (`swimdb.sqlite`) on first run — no migration step needed for a fresh start.

Open [http://localhost:8000](http://localhost:8000).

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```
DATABASE_URL=sqlite+aiosqlite:///./swimdb.sqlite
DEBUG=false
```

The default SQLite path works out of the box. To use PostgreSQL, change `DATABASE_URL` to a `postgresql+asyncpg://` connection string — no code changes required.

## Project Structure

```
app/
├── main.py               # FastAPI app + lifespan (DB init)
├── config.py             # Pydantic settings (.env)
├── database.py           # Async engine + session factory
├── models/               # SQLAlchemy ORM models
│   ├── athlete.py
│   ├── meet.py
│   ├── result.py         # Result + Split
│   └── cache.py          # DataSourceCache
├── services/
│   ├── base.py           # Abstract DataSource + cache helpers
│   ├── world_aquatics.py # World Aquatics JSON API adapter
│   ├── usa_swimming.py   # USAS SWIMS 3.0 Playwright scraper
│   ├── aggregator.py     # Fan-out across sources; all routes call this
│   └── normalizer.py     # Name normalization, time parsing, stroke mapping
├── routes/
│   ├── pages.py          # Full-page routes: /, /events, /athlete/{id}
│   └── partials.py       # HTMX partials: /htmx/*
└── templates/
    ├── base.html
    ├── home.html
    ├── event_results.html
    ├── athlete_detail.html
    └── partials/
```

## Routes

| Route | Description |
|-------|-------------|
| `GET /` | Athlete search home page |
| `GET /events` | Event top times (query params: `gender`, `distance`, `stroke`, `course`, `limit`, `year`) |
| `GET /athlete/{id}` | Athlete detail with full results history |
| `GET /htmx/athlete-search?q=` | Typeahead search partial |
| `GET /htmx/event-results?...` | Event results table partial |
| `GET /htmx/result/{id}/splits` | Splits expand/collapse partial |

## Notes

- **USA Swimming scraping** uses Playwright and takes 10–20 seconds on a cold request. The browser launches headless Chromium and interacts with the SWIMS 3.0 SPA. Subsequent requests are served from cache.
- **Splits data** — the UI supports inline splits expansion, but current data sources (World Aquatics, USAS) do not provide split times. The feature is wired and ready; rows show "No splits available" until a splits-capable source is added.
- **Event search is bookmarkable** — query params are pushed to the URL on each search, so results pages can be shared directly.
