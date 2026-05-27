from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import AsyncSessionLocal, init_db
from app.scheduler import create_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = create_scheduler(AsyncSessionLocal)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="SwimDB", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent / "static"), name="static")

from app.routes import pages, partials  # noqa: E402

app.include_router(pages.router)
app.include_router(partials.router, prefix="/htmx")
