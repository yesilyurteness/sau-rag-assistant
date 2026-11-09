"""Runs against real Postgres and Redis. Start them first: `make up` (or CI service containers)."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


def test_readiness_with_real_services() -> None:
    app = create_app(Settings(app_env="test"))

    with TestClient(app) as client:  # `with` runs the lifespan -> real connections
        response = client.get("/health/ready")

    assert response.status_code == 200, response.json()
    assert response.json()["checks"] == {"database": True, "cache": True}
