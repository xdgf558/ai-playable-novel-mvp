from typing import Optional
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.feedback_service import clear_feedback_records, list_feedback_records
from app.services.story_service import clear_stories


def _create_story_payload(
    template_id: str = "xianxia_rise",
    device_id: Optional[str] = None,
) -> dict:
    return {
        "device_id": device_id or str(uuid4()),
        "template_id": template_id,
        "locale": "zh-Hans",
        "protagonist": {
            "name": "林澈",
            "pronouns": "他",
            "age_band": "adult",
            "personality": ["冷静", "不服输"],
            "starting_role": "被宗门轻视的外门弟子",
            "main_goal": "查清家族没落真相",
            "special_ability": "能听见灵气裂隙中的低语",
        },
        "tone": "热血、悬念、成长",
        "content_rating": "teen",
    }


def test_submit_feedback_stores_fake_mode_record() -> None:
    clear_stories()
    clear_feedback_records()
    client = TestClient(create_app())
    device_id = str(uuid4())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()["story_id"]
    turn_id = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "choice",
            "choice_id": "choice_1",
            "user_text": None,
        },
    ).json()["turn_id"]

    response = client.post(
        "/v1/feedback",
        json={
            "device_id": device_id,
            "story_id": story_id,
            "turn_id": turn_id,
            "rating": "thumbs_down",
            "reason": "人物突然变得不像自己",
            "free_text": "这一段太快了，希望多一点对话。",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    records = list_feedback_records()
    assert len(records) == 1
    assert UUID(str(records[0].feedback_id))
    assert str(records[0].device_id) == device_id
    assert str(records[0].story_id) == story_id
    assert str(records[0].turn_id) == turn_id
    assert records[0].rating == "thumbs_down"
    assert records[0].reason == "人物突然变得不像自己"
    assert records[0].free_text == "这一段太快了，希望多一点对话。"


def test_submit_feedback_rejects_missing_story() -> None:
    clear_stories()
    clear_feedback_records()
    client = TestClient(create_app())
    story_id = str(uuid4())

    response = client.post(
        "/v1/feedback",
        json={
            "device_id": str(uuid4()),
            "story_id": story_id,
            "turn_id": None,
            "rating": "thumbs_up",
            "reason": "节奏不错",
            "free_text": None,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "story_not_found",
        "message": "Story was not found.",
        "details": {"story_id": story_id},
    }
    assert list_feedback_records() == []


def test_submit_feedback_rejects_mismatched_story_owner() -> None:
    clear_stories()
    clear_feedback_records()
    client = TestClient(create_app())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=str(uuid4())),
    ).json()["story_id"]

    response = client.post(
        "/v1/feedback",
        json={
            "device_id": str(uuid4()),
            "story_id": story_id,
            "turn_id": None,
            "rating": "neutral",
            "reason": "先记录一下",
            "free_text": None,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "story_not_found",
        "message": "Story was not found.",
        "details": {"story_id": story_id},
    }
    assert list_feedback_records() == []
