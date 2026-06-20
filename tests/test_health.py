from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_storycat_prefixed_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/storycat/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
