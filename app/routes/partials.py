from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.result import Result
from app.templates_config import templates

router = APIRouter()


def _require_htmx(request: Request) -> None:
    if not request.headers.get("HX-Request"):
        raise HTTPException(status_code=400, detail="HTMX request required")


@router.get("/athlete-search", response_class=HTMLResponse)
async def athlete_search(
    request: Request,
    q: str = "",
    session: AsyncSession = Depends(get_db),
):
    _require_htmx(request)
    athletes = []
    if q.strip():
        from app.services import aggregator
        athletes = await aggregator.search_athletes(q.strip(), session)
    return templates.TemplateResponse(
        request,
        "partials/athlete_search_results.html",
        {"athletes": athletes, "query": q},
    )


@router.get("/event-results", response_class=HTMLResponse)
async def event_results(
    request: Request,
    gender: str = "M",
    distance: int = 100,
    stroke: str = "freestyle",
    course: str = "LCM",
    limit: int = 50,
    year: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    _require_htmx(request)
    from app.services import aggregator
    from app.services.normalizer import normalize_stroke

    year_int: int | None = int(year) if year else None
    results = []
    error = None
    try:
        norm_stroke = normalize_stroke(stroke)
        results = await aggregator.get_event_top_times(
            gender=gender,
            distance=distance,
            stroke=norm_stroke,
            course=course,
            limit=min(max(limit, 1), 100),
            year=year_int,
            session=session,
        )
    except Exception as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "partials/event_table.html",
        {"results": results, "error": error},
    )


@router.get("/athlete/{athlete_id}/results", response_class=HTMLResponse)
async def athlete_results_partial(
    request: Request,
    athlete_id: int,
    course: list[str] = Query(default=None),
    session: AsyncSession = Depends(get_db),
):
    _require_htmx(request)
    from app.services import aggregator

    all_results = await aggregator.get_athlete_results(athlete_id, session)

    selected_courses = set(course) if course else set()
    no_courses_selected = len(selected_courses) == 0
    filtered = [r for r in all_results if r.course in selected_courses]

    meets_by_year: dict[int, list] = {}
    for r in filtered:
        yr = r.swim_date.year if r.swim_date else 0
        meets_by_year.setdefault(yr, []).append(r)
    meets_by_year = dict(sorted(meets_by_year.items(), reverse=True))

    return templates.TemplateResponse(
        request,
        "partials/athlete_results.html",
        {"meets_by_year": meets_by_year, "no_courses_selected": no_courses_selected},
    )


@router.get("/result/{result_id}/splits", response_class=HTMLResponse)
async def result_splits(
    request: Request,
    result_id: int,
    collapse: bool = False,
    inline: bool = False,
    session: AsyncSession = Depends(get_db),
):
    _require_htmx(request)
    if collapse:
        template = "partials/splits_inline.html" if inline else "partials/splits_row.html"
        return templates.TemplateResponse(
            request, template,
            {"result_id": result_id, "result": None, "splits": [], "collapsed": True},
        )

    result = await session.scalar(
        select(Result)
        .where(Result.id == result_id)
        .options(selectinload(Result.splits))
    )
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    splits = sorted(result.splits, key=lambda s: s.split_number)
    template = "partials/splits_inline.html" if inline else "partials/splits_row.html"
    return templates.TemplateResponse(
        request, template,
        {"result_id": result_id, "result": result, "splits": splits, "collapsed": False},
    )
