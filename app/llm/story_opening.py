from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.provider import LLMProvider, LLMRequest, LLMResponse
from app.llm.quota import InMemoryLLMQuotaPolicy, LLMQuotaError
from app.llm.router import InMemoryLLMRouter, LLMRouterSelection
from app.services.state_manager import validate_story_state
from app.schemas.stories import CreateStoryRequest, StoryChoice
from app.schemas.templates import StoryTemplate


class StoryOpeningFaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    attitude: str = Field(min_length=1)


class StoryOpeningCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    personality: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    relationship_to_player: str = Field(min_length=1)


class StoryOpeningBible(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_rules: list[str] = Field(min_length=1)
    tone: str = Field(min_length=1)
    forbidden_moves: list[str] = Field(min_length=1)
    major_factions: list[StoryOpeningFaction] = Field(min_length=1)
    main_characters: list[StoryOpeningCharacter] = Field(min_length=1)


class StoryOpeningChapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    required_outcome: str = Field(min_length=1)
    possible_branches: list[str] = Field(min_length=1)
    cliffhanger: str = Field(min_length=1)


class StoryOpeningPlotPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_chapters: int = Field(ge=1)
    chapters: list[StoryOpeningChapter] = Field(min_length=1)


class StoryOpeningPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    opening_narrative: str = Field(min_length=1)
    story_bible: StoryOpeningBible
    plot_plan: StoryOpeningPlotPlan
    initial_state_patch: dict[str, Any] = Field(default_factory=dict)
    choices: list[StoryChoice] = Field(min_length=3, max_length=3)


class StoryOpeningGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: LLMRequest
    response: LLMResponse
    payload: StoryOpeningPayload
    router_selection: Optional[LLMRouterSelection] = None


class StoryOpeningValidationError(ValueError):
    def __init__(
        self,
        *,
        response: LLMResponse,
        validation_error: ValidationError,
        router_selection: Optional[LLMRouterSelection] = None,
    ) -> None:
        self.response = response
        self.validation_error = validation_error
        self.router_selection = router_selection
        super().__init__("Story opening provider response failed schema validation.")


def build_story_opening_request(
    story_request: CreateStoryRequest,
    *,
    template: StoryTemplate,
    max_output_tokens: int = 2200,
) -> LLMRequest:
    metadata = _story_opening_metadata(story_request, template=template)

    return LLMRequest(
        task_type="story_bible_generation",
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate an original playable novel opening. Return only strict "
                    "json (strict JSON) matching the example JSON output shape below. Do not wrap "
                    "the response in markdown. Include title, opening_narrative, "
                    "story_bible, plot_plan, initial_state_patch, and exactly three "
                    "choices. The opening_narrative should read like a substantial "
                    "first page, not a short setup prompt: 4 to 6 paragraphs, "
                    "roughly 800 to 1200 Chinese characters, establishing "
                    "atmosphere, protagonist pressure, world texture, at least "
                    "one character/faction reaction, and a clear key decision "
                    "point at the end. Build a clear first-chapter rhythm: "
                    "setup the protagonist's immediate pressure, imply the "
                    "deeper conflict, and make the final decision point feel "
                    "like the doorway into a longer arc. The three choices "
                    "should appear only after that key point and should be "
                    "meaningful branch directions for the next section, not "
                    "tiny micro-actions. Make the three choices distinct in "
                    "story function: one investigative/conservative route, "
                    "one relational or negotiation route, and one risky "
                    "confrontational route. "
                    "Do not import existing novels or copyrighted IP.\n\n"
                    f"EXAMPLE JSON OUTPUT:\n{_story_opening_json_example()}"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            },
        ],
        max_output_tokens=max_output_tokens,
        metadata=metadata,
    )


def _story_opening_json_example() -> str:
    example = {
        "title": "原创修仙开局",
        "opening_narrative": (
            "主角站在第一处命运门槛前，先看见环境里不对劲的细节，"
            "再感受到周围人物或势力投来的压力。\n\n"
            "开局要像一页小说：写出场景、气味、声音、人物反应和主角内心判断，"
            "不要一两句话就把读者推去做选择。\n\n"
            "最后让场景自然停在真正会改变后续走向的关键分歧上。"
        ),
        "story_bible": {
            "world_rules": ["行动必须影响状态。"],
            "tone": "热血、悬念、成长",
            "forbidden_moves": ["不得复刻已有作品"],
            "major_factions": [
                {
                    "name": "青云外门",
                    "goal": "维持试炼秩序",
                    "attitude": "谨慎观望",
                }
            ],
            "main_characters": [
                {
                    "id": "npc_001",
                    "name": "顾问尘",
                    "role": "mentor_or_witness",
                    "personality": "冷静、谨慎",
                    "secret": "知道第一章冲突源头",
                    "relationship_to_player": "尚未信任主角",
                }
            ],
        },
        "plot_plan": {
            "total_chapters": 8,
            "chapters": [
                {
                    "index": 1,
                    "title": "命运开局",
                    "goal": "从身份压力推进到第一次关键分歧",
                    "required_outcome": "主角获得继续行动的线索和第一层关系反馈",
                    "possible_branches": ["调查确认", "谈判结盟", "冒险突破"],
                    "cliffhanger": "真正威胁显露，并把主角推向下一章问题。",
                }
            ],
        },
        "initial_state_patch": {},
        "choices": [
            {"id": "choice_1", "label": "先观察局势", "risk": "low"},
            {"id": "choice_2", "label": "主动试探对方", "risk": "medium"},
            {"id": "choice_3", "label": "直接逼近危险源", "risk": "high"},
        ],
    }
    return json.dumps(example, ensure_ascii=False, sort_keys=True)


def generate_story_opening(
    provider: LLMProvider,
    story_request: CreateStoryRequest,
    *,
    template: StoryTemplate,
    max_output_tokens: int = 1800,
    router: Optional[InMemoryLLMRouter] = None,
    quota_policy: Optional[InMemoryLLMQuotaPolicy] = None,
) -> StoryOpeningGenerationResult:
    llm_request = build_story_opening_request(
        story_request,
        template=template,
        max_output_tokens=max_output_tokens,
    )
    router_selection = _select_story_opening_router_model(
        router=router,
        request=llm_request,
    )
    llm_request = _request_for_router_selection(
        request=llm_request,
        router_selection=router_selection,
    )
    _check_story_opening_quota_preflight(
        quota_policy=quota_policy,
        request=llm_request,
    )
    response = provider.generate(llm_request)
    response = _apply_router_selection_metadata(
        response=response,
        router_selection=router_selection,
    )
    try:
        payload = validate_story_opening_payload(response.content)
    except ValidationError as exc:
        raise StoryOpeningValidationError(
            response=response,
            validation_error=exc,
            router_selection=router_selection,
        ) from exc

    return StoryOpeningGenerationResult(
        request=llm_request,
        response=response,
        payload=payload,
        router_selection=router_selection,
    )


def validate_story_opening_payload(content: dict[str, Any]) -> StoryOpeningPayload:
    return StoryOpeningPayload.model_validate(content)


def assemble_story_state_from_opening_payload(
    payload: StoryOpeningPayload,
    *,
    story_id: UUID,
    story_request: CreateStoryRequest,
    template: StoryTemplate,
    updated_at: str | None = None,
) -> dict[str, Any]:
    state = {
        "story_id": str(story_id),
        "locale": story_request.locale,
        "template_id": template.id,
        "title": payload.title,
        "protagonist": story_request.protagonist.model_dump(),
        "story_bible": payload.story_bible.model_dump(),
        "plot_plan": payload.plot_plan.model_dump(),
        "current_chapter_index": 1,
        "current_scene_index": 1,
        "active_goal": story_request.protagonist.main_goal,
        "short_summary": payload.opening_narrative,
        "long_summary": payload.opening_narrative,
        "relationships": _initial_relationships(payload),
        "inventory": [],
        "stats": {"danger": 10, "reputation": 0, "power": 1, "health": 100},
        "flags": {
            "opening_created": True,
            "story_opening_generated": True,
            "opening_template_id": template.id,
            "opening_initial_state_patch": payload.initial_state_patch,
        },
        "turn_count": 0,
        "updated_at": updated_at or datetime.now(timezone.utc).isoformat(),
    }
    validate_story_state(state)

    return state


def _story_opening_metadata(
    story_request: CreateStoryRequest,
    *,
    template: StoryTemplate,
) -> dict[str, Any]:
    protagonist = story_request.protagonist

    return {
        "locale": story_request.locale,
        "content_rating": story_request.content_rating,
        "tone": story_request.tone,
        "template_id": template.id,
        "template_name": template.name,
        "template_genre": template.genre,
        "template_short_description": template.short_description,
        "template_tags": list(template.tags),
        "template_recommended_tone": list(template.recommended_tone),
        "protagonist_name": protagonist.name,
        "protagonist_pronouns": protagonist.pronouns,
        "protagonist_age_band": protagonist.age_band,
        "protagonist_personality": list(protagonist.personality),
        "protagonist_starting_role": protagonist.starting_role,
        "protagonist_main_goal": protagonist.main_goal,
        "protagonist_special_ability": protagonist.special_ability,
    }


def _initial_relationships(
    payload: StoryOpeningPayload,
) -> dict[str, dict[str, int | str]]:
    relationships: dict[str, dict[str, int | str]] = {}
    for character in payload.story_bible.main_characters:
        relationships[character.id] = {
            "affinity": 0,
            "trust": 0,
            "status": _relationship_status(character.relationship_to_player),
        }

    return relationships


def _relationship_status(value: str) -> str:
    stripped_value = value.strip()
    if stripped_value and len(stripped_value) <= 80:
        return stripped_value

    return "unknown"


def _select_story_opening_router_model(
    *,
    router: Optional[InMemoryLLMRouter],
    request: LLMRequest,
) -> Optional[LLMRouterSelection]:
    if router is None:
        return None

    return router.select_model(
        task_type=request.task_type,
        estimated_input_tokens=_estimate_request_input_tokens(request),
        max_output_tokens=request.max_output_tokens,
    )


def _request_for_router_selection(
    *,
    request: LLMRequest,
    router_selection: Optional[LLMRouterSelection],
) -> LLMRequest:
    if router_selection is None:
        return request

    return request.model_copy(
        update={"max_output_tokens": router_selection.max_output_tokens}
    )


def _apply_router_selection_metadata(
    *,
    response: LLMResponse,
    router_selection: Optional[LLMRouterSelection],
) -> LLMResponse:
    if router_selection is None:
        return response

    return response.model_copy(
        update={
            "provider": router_selection.provider,
            "model": router_selection.model,
            "fallback_used": router_selection.fallback_used,
        }
    )


def _check_story_opening_quota_preflight(
    *,
    quota_policy: Optional[InMemoryLLMQuotaPolicy],
    request: LLMRequest,
) -> None:
    if quota_policy is None:
        return

    failure = quota_policy.check_request(
        requested_tokens=_estimate_request_total_tokens(request),
    )
    if failure is not None:
        raise LLMQuotaError(failure)


def _estimate_request_input_tokens(request: LLMRequest) -> int:
    text = " ".join(message.content for message in request.messages)
    return max(1, len(text) // 4)


def _estimate_request_total_tokens(request: LLMRequest) -> int:
    return _estimate_request_input_tokens(request) + request.max_output_tokens
