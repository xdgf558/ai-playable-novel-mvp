from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.provider import LLMTaskType
from app.schemas.state import TurnStatePatch


LLMParseErrorCode = Literal["invalid_json", "invalid_schema"]


class LLMChoiceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    risk: Literal["low", "medium", "high"]


class LLMMemoryUpdateOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_facts: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    resolved_threads: list[str] = Field(default_factory=list)


class LLMSafetyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    safe: bool
    reason: str = Field(min_length=1, max_length=300)


class NormalTurnGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative: str = Field(min_length=1)
    choices: list[LLMChoiceOutput] = Field(min_length=3, max_length=3)
    state_patch: TurnStatePatch
    memory_update: LLMMemoryUpdateOutput
    safety: LLMSafetyOutput


class LLMParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    task_type: LLMTaskType
    content: Optional[dict[str, Any]] = None
    error_code: Optional[LLMParseErrorCode] = None
    error_message: Optional[str] = None


def parse_llm_raw_json(raw_text: str, task_type: LLMTaskType) -> LLMParseResult:
    try:
        parsed_json = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return LLMParseResult(
            ok=False,
            task_type=task_type,
            error_code="invalid_json",
            error_message=str(exc),
        )

    if not isinstance(parsed_json, dict):
        return LLMParseResult(
            ok=False,
            task_type=task_type,
            error_code="invalid_json",
            error_message="Provider JSON output must be an object.",
        )

    try:
        content = _validate_task_content(parsed_json, task_type)
    except ValidationError as exc:
        return LLMParseResult(
            ok=False,
            task_type=task_type,
            error_code="invalid_schema",
            error_message=str(exc),
        )

    return LLMParseResult(
        ok=True,
        task_type=task_type,
        content=content,
    )


def _validate_task_content(
    parsed_json: dict[str, Any],
    task_type: LLMTaskType,
) -> dict[str, Any]:
    if task_type in ("normal_turn_generation", "json_repair"):
        return NormalTurnGenerationOutput.model_validate(parsed_json).model_dump()

    return parsed_json
