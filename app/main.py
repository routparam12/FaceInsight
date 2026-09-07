from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import init_db
from app.utils.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    # Dev/test convenience. In production run Alembic migrations instead and
    # set RUN_CREATE_ALL=0-equivalent by removing this call.
    await init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.env,
        "model_version": settings.model_version,
        "embedding_dim": settings.embedding_dim,
    }
