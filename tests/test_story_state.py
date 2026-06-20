from copy import deepcopy
from typing import Optional
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.schemas.state import StoryState
from app.services.state_manager import (
    apply_choice_turn_state_update,
    apply_free_text_turn_state_update,
    apply_generated_turn_state_patch,
    validate_story_state,
    validate_turn_state_patch,
)
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


def test_story_state_schema_validates_created_fake_story_state() -> None:
    clear_stories()
    client = TestClient(create_app())

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    state = StoryState.model_validate(response.json()["current_state"])
    assert str(state.story_id) == response.json()["story_id"]
    assert state.template_id == "xianxia_rise"
    assert state.protagonist.name == "林澈"
    assert state.story_bible.world_rules
    assert state.plot_plan.total_chapters == 8
    assert state.relationships["npc_001"].status == "unknown"
    assert state.inventory == []
    assert state.stats.danger == 10
    assert state.flags["fake_mode"] is True
    assert state.turn_count == 0


def test_story_state_schema_validates_turn_updated_fake_story_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()["story_id"]

    turn_response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "choice",
            "choice_id": "choice_2",
            "user_text": None,
        },
    )

    assert turn_response.status_code == 200
    state = StoryState.model_validate(turn_response.json()["state"])
    assert state.turn_count == 1
    assert state.current_scene_index == 2
    assert state.stats.danger == 12
    assert state.flags["last_choice_id"] == "choice_2"
    assert "当众反击" in state.short_summary


def test_story_state_schema_rejects_missing_required_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    malformed_state = deepcopy(response.json()["current_state"])
    malformed_state.pop("protagonist")

    with pytest.raises(ValidationError):
        StoryState.model_validate(malformed_state)


def test_story_state_schema_rejects_malformed_stats() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    malformed_state = deepcopy(response.json()["current_state"])
    malformed_state["stats"]["danger"] = "high"

    with pytest.raises(ValidationError):
        StoryState.model_validate(malformed_state)


def test_state_manager_validates_story_state_without_changing_payload() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    state_payload = response.json()["current_state"]
    before_validation = deepcopy(state_payload)

    state = validate_story_state(state_payload)

    assert str(state.story_id) == response.json()["story_id"]
    assert state_payload == before_validation


def test_state_manager_rejects_malformed_story_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    malformed_state = deepcopy(response.json()["current_state"])
    malformed_state["current_scene_index"] = 0

    with pytest.raises(ValidationError):
        validate_story_state(malformed_state)


def test_state_manager_validates_turn_state_patch() -> None:
    patch = validate_turn_state_patch(
        {
            "active_goal": "稳住试炼台局面",
            "short_summary_append": "你看见执事袖口露出半枚木牌。",
            "relationships": {
                "npc_001": {
                    "affinity_delta": 1,
                    "trust_delta": -1,
                    "status": "watching",
                }
            },
            "inventory_add": [
                {
                    "id": "token_001",
                    "name": "裂纹木牌",
                    "description": "试炼台边缘遗落的旧木牌。",
                    "quantity": 1,
                }
            ],
            "inventory_remove_ids": ["dust_001"],
            "stats_delta": {
                "danger": 2,
                "reputation": 1,
                "power": 0,
                "health": -3,
            },
            "flags_set": {"saw_hidden_token": True},
            "chapter_progress_delta": 8,
        }
    )

    assert patch.active_goal == "稳住试炼台局面"
    assert patch.relationships["npc_001"].affinity_delta == 1
    assert patch.relationships["npc_001"].trust_delta == -1
    assert patch.inventory_add[0].id == "token_001"
    assert patch.stats_delta.health == -3
    assert patch.flags_set["saw_hidden_token"] is True
    assert patch.chapter_progress_delta == 8


def test_state_manager_rejects_turn_state_patch_unknown_field() -> None:
    with pytest.raises(ValidationError):
        validate_turn_state_patch(
            {
                "short_summary_append": "你试图跳过当前章节。",
                "teleport_to_finale": True,
            }
        )


def test_state_manager_rejects_turn_state_patch_malformed_inventory() -> None:
    with pytest.raises(ValidationError):
        validate_turn_state_patch(
            {
                "short_summary_append": "你捡起一件无法识别的物品。",
                "inventory_add": [{"id": "broken_item", "quantity": 0}],
            }
        )


def test_state_manager_rejects_turn_state_patch_malformed_relationship() -> None:
    with pytest.raises(ValidationError):
        validate_turn_state_patch(
            {
                "short_summary_append": "韩照忽然态度大变。",
                "relationships": {"npc_001": {"affinity_delta": "much"}},
            }
        )


def test_state_manager_applies_generated_turn_state_patch() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    state_payload = response.json()["current_state"]

    state = apply_generated_turn_state_patch(
        state_payload,
        patch={
            "active_goal": "确认执事藏起木牌的原因",
            "short_summary_append": "你借选择逼近了执事藏起木牌的秘密。",
            "relationships": {
                "npc_001": {
                    "affinity_delta": 1,
                    "trust_delta": 2,
                    "status": "watching",
                }
            },
            "inventory_add": [
                {
                    "id": "token_001",
                    "name": "裂纹木牌",
                    "description": "试炼台边缘遗落的旧木牌。",
                    "quantity": 1,
                }
            ],
            "inventory_remove_ids": [],
            "stats_delta": {
                "danger": 1,
                "reputation": 1,
                "power": 0,
                "health": -2,
            },
            "flags_set": {"saw_hidden_token": True},
            "chapter_progress_delta": 1,
        },
        narrative="你选择逼近执事藏起木牌的秘密。",
        updated_at="2026-05-31T00:00:00+00:00",
    )

    assert state.turn_count == 1
    assert state.current_scene_index == 2
    assert state.active_goal == "确认执事藏起木牌的原因"
    assert state.short_summary == "你借选择逼近了执事藏起木牌的秘密。"
    assert state.relationships["npc_001"].affinity == 1
    assert state.relationships["npc_001"].trust == 2
    assert state.relationships["npc_001"].status == "watching"
    assert state.inventory[0].id == "token_001"
    assert state.stats.danger == 11
    assert state.stats.reputation == 1
    assert state.stats.health == 98
    assert state.flags["saw_hidden_token"] is True


def test_state_manager_applies_choice_turn_update_deterministically() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    state_payload = response.json()["current_state"]
    narrative = "你选择了「当众反击，争取试炼机会」。"

    state = apply_choice_turn_state_update(
        state_payload,
        choice_id="choice_2",
        choice_risk="medium",
        narrative=narrative,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    assert state.turn_count == 1
    assert state.current_scene_index == 2
    assert state.stats.danger == 12
    assert state.relationships["npc_001"].affinity == 1
    assert state.relationships["npc_001"].trust == 0
    assert state.flags["last_choice_id"] == "choice_2"
    assert state.short_summary == narrative


def test_state_manager_completes_xianxia_chapter_one_deterministically() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    state_payload = response.json()["current_state"]
    state_payload["turn_count"] = 5
    state_payload["current_scene_index"] = 6
    narrative = "你选择了「顺着线索继续试探」。"

    state = apply_choice_turn_state_update(
        state_payload,
        choice_id="choice_1",
        choice_risk="low",
        narrative=narrative,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    assert state.turn_count == 6
    assert state.current_chapter_index == 2
    assert state.current_scene_index == 1
    assert state.active_goal == "追查试炼台后显露的真正威胁"
    assert state.flags["chapter_1_completed"] is True
    assert state.flags["chapter_1_completed_at_turn"] == 6
    assert state.flags["last_completed_chapter_index"] == 1
    assert "第一章完成" in state.long_summary


def test_state_manager_rolls_over_later_fake_chapters_at_scene_boundary() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    state_payload = response.json()["current_state"]
    state_payload["turn_count"] = 14
    state_payload["current_chapter_index"] = 2
    state_payload["current_scene_index"] = 9
    state_payload["active_goal"] = "追查第二章的幕后威胁"
    state_payload["flags"]["chapter_1_completed"] = True
    state_payload["flags"]["chapter_1_completed_at_turn"] = 6
    state_payload["flags"]["last_completed_chapter_index"] = 1
    narrative = "你选择了「直接触碰禁忌线索换取突破」。"

    state = apply_choice_turn_state_update(
        state_payload,
        choice_id="choice_3",
        choice_risk="high",
        narrative=narrative,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    assert state.turn_count == 15
    assert state.current_chapter_index == 3
    assert state.current_scene_index == 1
    assert state.active_goal == "推进第3章的新目标"
    assert state.flags["chapter_2_completed"] is True
    assert state.flags["chapter_2_completed_at_turn"] == 15
    assert state.flags["last_completed_chapter_index"] == 2
    assert "第2章完成" in state.long_summary


def test_state_manager_applies_free_text_turn_update_deterministically() -> None:
    clear_stories()
    client = TestClient(create_app())
    response = client.post("/v1/stories", json=_create_story_payload())
    state_payload = response.json()["current_state"]
    user_text = "我绕到试炼台侧面，确认执事手里的木牌顺序。"
    narrative = f"你没有选择既定路线，而是把想法落成行动：「{user_text}」"

    state = apply_free_text_turn_state_update(
        state_payload,
        user_text=user_text,
        narrative=narrative,
        updated_at="2026-05-30T00:00:00+00:00",
    )

    assert state.turn_count == 1
    assert state.current_scene_index == 2
    assert state.stats.danger == 11
    assert state.relationships["npc_001"].trust == 1
    assert state.relationships["npc_001"].affinity == 0
    assert state.flags["last_input_type"] == "free_text"
    assert state.flags["last_user_text"] == user_text
    assert state.short_summary == narrative
