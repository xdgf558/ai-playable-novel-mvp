from __future__ import annotations

from typing import Any, Literal, Mapping, MutableMapping

from app.schemas.state import StoryState, TurnStatePatch


ChoiceRisk = Literal["low", "medium", "high"]

_CHOICE_DANGER_DELTA: dict[ChoiceRisk, int] = {
    "low": 0,
    "medium": 2,
    "high": 5,
}
_XIANXIA_CHAPTER_ONE_COMPLETE_TURN = 6
_FAKE_CHAPTER_MAX_SCENE_INDEX = 9


def validate_story_state(state: Mapping[str, Any]) -> StoryState:
    return StoryState.model_validate(state)


def validate_turn_state_patch(patch: Mapping[str, Any]) -> TurnStatePatch:
    return TurnStatePatch.model_validate(patch)


def apply_generated_turn_state_patch(
    state: MutableMapping[str, Any],
    *,
    patch: Mapping[str, Any],
    narrative: str,
    updated_at: str,
) -> StoryState:
    validated_patch = validate_turn_state_patch(patch)

    state["turn_count"] += 1
    state["current_scene_index"] = max(
        1,
        state["current_scene_index"] + validated_patch.chapter_progress_delta,
    )
    state["updated_at"] = updated_at

    if validated_patch.active_goal is not None:
        state["active_goal"] = validated_patch.active_goal

    short_summary = validated_patch.short_summary_append.strip()
    state["short_summary"] = short_summary or narrative
    state["long_summary"] = _append_summary(state["long_summary"], narrative)
    if short_summary and short_summary not in narrative:
        state["long_summary"] = _append_summary(state["long_summary"], short_summary)

    _apply_relationship_patches(state, validated_patch)
    _apply_inventory_patches(state, validated_patch)
    _apply_stat_deltas(state, validated_patch)
    state["flags"].update(validated_patch.flags_set)

    _maybe_complete_fake_chapter(state)
    return validate_story_state(state)


def apply_choice_turn_state_update(
    state: MutableMapping[str, Any],
    *,
    choice_id: str,
    choice_risk: ChoiceRisk,
    narrative: str,
    updated_at: str,
) -> StoryState:
    _advance_turn(state, narrative=narrative, updated_at=updated_at)
    state["flags"]["last_choice_id"] = choice_id
    state["flags"]["last_choice_risk"] = choice_risk
    state["stats"]["danger"] += _CHOICE_DANGER_DELTA[choice_risk]

    relationship = state["relationships"]["npc_001"]
    if choice_risk == "low":
        relationship["trust"] += 1
    elif choice_risk == "medium":
        relationship["affinity"] += 1
    else:
        relationship["trust"] -= 1

    _maybe_complete_fake_chapter(state)
    return validate_story_state(state)


def apply_free_text_turn_state_update(
    state: MutableMapping[str, Any],
    *,
    user_text: str,
    narrative: str,
    updated_at: str,
) -> StoryState:
    _advance_turn(state, narrative=narrative, updated_at=updated_at)
    state["flags"]["last_input_type"] = "free_text"
    state["flags"]["last_user_text"] = user_text
    state["stats"]["danger"] += 1
    state["relationships"]["npc_001"]["trust"] += 1

    _maybe_complete_fake_chapter(state)
    return validate_story_state(state)


def _advance_turn(
    state: MutableMapping[str, Any],
    *,
    narrative: str,
    updated_at: str,
) -> None:
    state["turn_count"] += 1
    state["current_scene_index"] += 1
    state["updated_at"] = updated_at
    state["short_summary"] = narrative
    state["long_summary"] = f"{state['long_summary']}\n{narrative}"


def _append_summary(existing: str, addition: str) -> str:
    stripped_addition = addition.strip()
    if not stripped_addition:
        return existing

    return f"{existing}\n{stripped_addition}"


def _apply_relationship_patches(
    state: MutableMapping[str, Any],
    patch: TurnStatePatch,
) -> None:
    for character_id, relationship_patch in patch.relationships.items():
        relationship = state["relationships"].setdefault(
            character_id,
            {"affinity": 0, "trust": 0, "status": "unknown"},
        )
        relationship["affinity"] += relationship_patch.affinity_delta
        relationship["trust"] += relationship_patch.trust_delta
        if relationship_patch.status is not None:
            relationship["status"] = relationship_patch.status


def _apply_inventory_patches(
    state: MutableMapping[str, Any],
    patch: TurnStatePatch,
) -> None:
    remove_ids = set(patch.inventory_remove_ids)
    inventory = [
        item for item in state["inventory"] if item.get("id") not in remove_ids
    ]
    add_ids = {item.id for item in patch.inventory_add}
    inventory = [item for item in inventory if item.get("id") not in add_ids]
    inventory.extend(item.model_dump() for item in patch.inventory_add)
    state["inventory"] = inventory


def _apply_stat_deltas(
    state: MutableMapping[str, Any],
    patch: TurnStatePatch,
) -> None:
    stats = state["stats"]
    stats["danger"] = max(0, stats["danger"] + patch.stats_delta.danger)
    stats["reputation"] += patch.stats_delta.reputation
    stats["power"] = max(0, stats["power"] + patch.stats_delta.power)
    stats["health"] = min(100, max(0, stats["health"] + patch.stats_delta.health))


def _maybe_complete_fake_chapter(state: MutableMapping[str, Any]) -> None:
    if state["template_id"] != "xianxia_rise":
        return

    if state["current_chapter_index"] == 1:
        if state["turn_count"] < _XIANXIA_CHAPTER_ONE_COMPLETE_TURN:
            return

        _complete_fake_chapter_one(state)
        return

    if state["current_scene_index"] <= _FAKE_CHAPTER_MAX_SCENE_INDEX:
        return

    _complete_fake_chapter(state, completed_chapter_index=state["current_chapter_index"])


def _complete_fake_chapter_one(state: MutableMapping[str, Any]) -> None:
    _complete_fake_chapter(state, completed_chapter_index=1)
    state["active_goal"] = "追查试炼台后显露的真正威胁"
    state["short_summary"] = (
        f"{state['short_summary']}第一章的核心冲突暂告一段落，"
        "新的威胁把你推向第二章。"
    )
    state["long_summary"] = (
        f"{state['long_summary']}\n"
        "第一章完成：主角获得继续追查真正威胁的线索。"
    )


def _complete_fake_chapter(
    state: MutableMapping[str, Any],
    *,
    completed_chapter_index: int,
) -> None:
    next_chapter_index = completed_chapter_index + 1
    state["current_chapter_index"] = next_chapter_index
    state["current_scene_index"] = 1
    state["active_goal"] = _next_chapter_goal(state, next_chapter_index)
    state["flags"][f"chapter_{completed_chapter_index}_completed"] = True
    state["flags"][f"chapter_{completed_chapter_index}_completed_at_turn"] = state[
        "turn_count"
    ]
    state["flags"]["last_completed_chapter_index"] = completed_chapter_index
    if completed_chapter_index > 1:
        state["short_summary"] = (
            f"{state['short_summary']}第{completed_chapter_index}章的阶段目标完成，"
            f"故事进入第{next_chapter_index}章。"
        )
        state["long_summary"] = (
            f"{state['long_summary']}\n"
            f"第{completed_chapter_index}章完成：主角进入第{next_chapter_index}章。"
        )


def _next_chapter_goal(state: Mapping[str, Any], chapter_index: int) -> str:
    chapters = state.get("plot_plan", {}).get("chapters", [])
    for chapter in chapters:
        if chapter.get("index") == chapter_index:
            return chapter.get("goal") or f"推进第{chapter_index}章的新目标"

    return f"推进第{chapter_index}章的新目标"
    state["long_summary"] = (
        f"{state['long_summary']}\n"
        "第一章完成：主角获得继续追查真正威胁的线索。"
    )
