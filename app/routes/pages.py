from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.templates_config import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@router.get("/events", response_class=HTMLResponse)
async def events(
    request: Request,
    gender: str = "M",
    distance: int = 100,
    stroke: str = "freestyle",
    course: str = "LCM",
    limit: int = 50,
    year: int | None = None,
    session: AsyncSession = Depends(get_db),
):
    results = []
    error = None
    if request.query_params:
        from app.services import aggregator
        from app.services.normalizer import normalize_stroke

        try:
            norm_stroke = normalize_stroke(stroke)
            results = await aggregator.get_event_top_times(
                gender=gender,
                distance=distance,
                stroke=norm_stroke,
                course=course,
                limit=min(max(limit, 1), 100),
                year=year,
                session=session,
            )
        except Exception as exc:
            error = str(exc)

    return templates.TemplateResponse(
        request,
        "event_results.html",
        {
            "results": results,
            "error": error,
            "selected": {
                "gender": gender,
                "distance": distance,
                "stroke": stroke,
                "course": course,
                "limit": limit,
                "year": year,
            },
        },
    )


@router.get("/athlete/{athlete_id}", response_class=HTMLResponse)
async def athlete_detail(
    request: Request,
    athlete_id: int,
    session: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException

    from app.services import aggregator

    athlete = await aggregator.get_athlete_detail(athlete_id, session)
    if not athlete:
        raise HTTPException(status_code=404, detail="Athlete not found")

    results = await aggregator.get_athlete_results(athlete_id, session)

    meets_by_year: dict[int, list] = {}
    for res in results:
        yr = res.swim_date.year if res.swim_date else 0
        meets_by_year.setdefault(yr, []).append(res)

    return templates.TemplateResponse(
        request,
        "athlete_detail.html",
        {
            "athlete": athlete,
            "meets_by_year": dict(sorted(meets_by_year.items(), reverse=True)),
        },
    )
