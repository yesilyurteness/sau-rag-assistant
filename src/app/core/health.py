"""Dependency health checks used by the readiness endpoint.

Each check returns True/False and never raises, so one failing dependency
cannot crash the probe. The checker is injected as a FastAPI dependency,
which keeps the route testable without real services.
"""

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class HealthChecker:
    engine: AsyncEngine
    redis: Redis

    async def database(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # noqa: BLE001 - report, don't propagate
            log.warning("health.database_failed", error=str(exc))
            return False

    async def cache(self) -> bool:
        try:
            return bool(await self.redis.ping())
        except Exception as exc:  # noqa: BLE001
            log.warning("health.redis_failed", error=str(exc))
            return False
