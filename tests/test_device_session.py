from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.device_session_service import clear_device_sessions


def test_device_session_creates_session() -> None:
    clear_device_sessions()
    client = TestClient(create_app())
    device_id = str(uuid4())

    response = client.post(
        "/v1/device-session",
        json={
            "device_id": device_id,
            "app_version": "0.1.0",
            "locale": "zh-Hans",
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert response_body == {
        "user_id": response_body["user_id"],
        "device_id": device_id,
        "daily_turn_limit": 50,
        "turns_used_today": 0,
    }
    assert UUID(response_body["user_id"])


def test_device_session_reuses_user_for_same_device() -> None:
    clear_device_sessions()
    client = TestClient(create_app())
    device_id = str(uuid4())
    payload = {
        "device_id": device_id,
        "app_version": "0.1.0",
        "locale": "zh-Hans",
    }

    first_response = client.post("/v1/device-session", json=payload)
    second_response = client.post("/v1/device-session", json=payload)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json() == first_response.json()


def test_device_session_rejects_invalid_device_id() -> None:
    clear_device_sessions()
    client = TestClient(create_app())

    response = client.post(
        "/v1/device-session",
        json={
            "device_id": "not-a-uuid",
            "app_version": "0.1.0",
            "locale": "zh-Hans",
        },
    )

    assert response.status_code == 422
    response_body = response.json()
    assert response_body["error"]["code"] == "validation_error"
    assert response_body["error"]["message"] == "Request validation failed."
    assert response_body["error"]["details"]["errors"][0]["loc"] == [
        "body",
        "device_id",
    ]
