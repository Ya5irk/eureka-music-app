from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.database import init_db
from app.routers import genres, health, tracks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings()  # ensures storage_dir exists
    await init_db()
    yield


app = FastAPI(
    title="Eureka Music Server",
    description="Catalog + audio storage server for the Eureka Music App.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(tracks.router)
app.include_router(genres.router)
