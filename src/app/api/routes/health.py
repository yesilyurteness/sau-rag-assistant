"""Liveness and readiness probes.

- /health        : the process is up (used by Docker HEALTHCHECK and load balancers)
- /health/ready  : the process can serve traffic (database and cache reachable)
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from app import __version__
from app.core.health import HealthChecker

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str = __version__


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    checks: dict[str, bool]


def get_health_checker(request: Request) -> HealthChecker:
    checker: HealthChecker = request.app.state.health_checker
    return checker


@router.get("", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    checker: Annotated[HealthChecker, Depends(get_health_checker)],
) -> ReadinessResponse:
    checks = {"database": await checker.database(), "cache": await checker.cache()}
    ready = all(checks.values())
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if ready else "degraded", checks=checks)
