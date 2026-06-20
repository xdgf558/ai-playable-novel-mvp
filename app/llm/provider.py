from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


LLMTaskType = Literal[
    "story_bible_generation",
    "chapter_outline_generation",
    "normal_turn_generation",
    "state_extraction",
    "summary_generation",
    "json_repair",
    "safety_classification",
    "ending_generation",
]
LLMModelTier = Literal["fast", "quality"]

LLM_TASK_TYPES: tuple[str, ...] = (
    "story_bible_generation",
    "chapter_outline_generation",
    "normal_turn_generation",
    "state_extraction",
    "summary_generation",
    "json_repair",
    "safety_classification",
    "ending_generation",
)

_QUALITY_TASK_TYPES: tuple[str, ...] = (
    "story_bible_generation",
    "chapter_outline_generation",
    "ending_generation",
)


def model_tier_for_task(task_type: LLMTaskType) -> LLMModelTier:
    if task_type in _QUALITY_TASK_TYPES:
        return "quality"

    return "fast"


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: LLMTaskType
    messages: list[LLMMessage] = Field(min_length=1)
    response_format: Literal["json_object"] = "json_object"
    max_output_tokens: int = Field(default=900, ge=1, le=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated: bool = True


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    task_type: LLMTaskType
    content: dict[str, Any]
    usage: LLMUsage
    latency_ms: int = Field(ge=0)
    raw_text: str
    fallback_used: bool = False


class LLMProvider(Protocol):
    name: str

    def generate(self, request: LLMRequest) -> LLMResponse:
        ...
