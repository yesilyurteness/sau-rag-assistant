from fastapi.testclient import TestClient

from app import __version__
from tests.conftest import FakeHealthChecker


def test_liveness_returns_ok_and_version(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_readiness_ok_when_all_dependencies_up(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": True, "cache": True}}


def test_readiness_503_when_database_down(
    client: TestClient, fake_checker: FakeHealthChecker
) -> None:
    fake_checker.db_ok = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {"database": False, "cache": True}
