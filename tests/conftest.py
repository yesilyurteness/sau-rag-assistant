from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.health import get_health_checker
from app.core.config import Settings
from app.main import create_app


@dataclass
class FakeHealthChecker:
    db_ok: bool = True
    cache_ok: bool = True

    async def database(self) -> bool:
        return self.db_ok

    async def cache(self) -> bool:
        return self.cache_ok


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test")  # type: ignore[call-arg]


@pytest.fixture
def fake_checker() -> FakeHealthChecker:
    return FakeHealthChecker()


@pytest.fixture
def app(settings: Settings, fake_checker: FakeHealthChecker) -> FastAPI:
    application = create_app(settings)
    application.dependency_overrides[get_health_checker] = lambda: fake_checker
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # No `with` block: the lifespan (real DB/Redis connections) is not started in unit tests.
    yield TestClient(app)
