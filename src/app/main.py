"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from app import __version__
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.health import HealthChecker
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
    redis = Redis.from_url(str(settings.redis_url))
    app.state.health_checker = HealthChecker(engine=engine, redis=redis)
    log.info("app.startup", env=settings.app_env, version=__version__)
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()
        log.info("app.shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="SAU RAG Assistant",
        version=__version__,
        lifespan=lifespan,
        # Interactive docs are useful in dev but expose the API surface in prod.
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
