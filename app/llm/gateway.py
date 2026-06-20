from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.llm.ledger import (
    LLMCallAttemptType,
    LLMCallLedger,
    LLMCallLedgerEntry,
    default_llm_call_ledger,
)
from app.llm.parser import LLMParseResult, parse_llm_raw_json
from app.llm.provider import LLMProvider, LLMRequest, LLMResponse, LLMTaskType, LLMUsage
from app.llm.quota import InMemoryLLMQuotaPolicy, LLMQuotaFailure, LLMQuotaUsageUpdate
from app.llm.router import (
    InMemoryLLMRouter,
    LLMRouterSelection,
    LLMRouterSelectionError,
    LLMRouterSelectionFailure,
    LLMRouterUsageUpdate,
)


LLMGenerationErrorCode = Literal["quota_exceeded", "router_selection_failed"]


class LLMGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    requested_task_type: LLMTaskType
    content: Optional[dict[str, Any]] = None
    response: Optional[LLMResponse] = None
    parse_result: Optional[LLMParseResult] = None
    repair_used: bool = False
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    error_code: Optional[LLMGenerationErrorCode] = None
    error_message: Optional[str] = None
    initial_response: Optional[LLMResponse] = None
    initial_parse_result: Optional[LLMParseResult] = None
    repair_response: Optional[LLMResponse] = None
    repair_parse_result: Optional[LLMParseResult] = None
    quota_failure: Optional[LLMQuotaFailure] = None
    quota_usage_updates: list[LLMQuotaUsageUpdate] = Field(default_factory=list)
    router_selection: Optional[LLMRouterSelection] = None
    router_selection_failure: Optional[LLMRouterSelectionFailure] = None
    router_usage_update: Optional[LLMRouterUsageUpdate] = None


def generate_normal_turn_with_repair(
    provider: LLMProvider,
    request: LLMRequest,
    ledger: Optional[LLMCallLedger] = None,
    router: Optional[InMemoryLLMRouter] = None,
    quota_policy: Optional[InMemoryLLMQuotaPolicy] = None,
) -> LLMGenerationResult:
    if request.task_type != "normal_turn_generation":
        raise ValueError("JSON repair retry currently supports normal_turn_generation only.")

    active_ledger = ledger or default_llm_call_ledger
    try:
        router_selection = _select_initial_router_model(
            router=router,
            request=request,
        )
    except LLMRouterSelectionError as exc:
        return _router_selection_failure_result(
            request=request,
            failure=exc.failure,
        )
    initial_request = _request_for_router_selection(
        request=request,
        router_selection=router_selection,
    )
    quota_failure = _check_quota_preflight(
        quota_policy=quota_policy,
        request=initial_request,
    )
    if quota_failure is not None:
        return _quota_failure_result(
            request=request,
            failure=quota_failure,
            router_selection=router_selection,
        )

    initial_response = provider.generate(initial_request)
    initial_response = _apply_router_selection_metadata(
        response=initial_response,
        router_selection=router_selection,
    )
    initial_parse_result = parse_llm_raw_json(
        raw_text=initial_response.raw_text,
        task_type=initial_request.task_type,
    )
    initial_ledger_entry = _record_response(
        ledger=active_ledger,
        response=initial_response,
        attempt_type="initial",
        parse_result=initial_parse_result,
    )
    router_usage_update = _record_initial_router_usage(
        router=router,
        entry=initial_ledger_entry,
    )
    quota_usage_updates = _record_initial_quota_usage(
        quota_policy=quota_policy,
        entry=initial_ledger_entry,
    )
    if initial_parse_result.ok:
        return LLMGenerationResult(
            ok=True,
            requested_task_type=request.task_type,
            content=initial_parse_result.content,
            response=initial_response,
            parse_result=initial_parse_result,
            repair_used=False,
            fallback_used=False,
            initial_response=initial_response,
            initial_parse_result=initial_parse_result,
            router_selection=router_selection,
            router_usage_update=router_usage_update,
            quota_usage_updates=quota_usage_updates,
        )

    repair_request = _build_repair_request(
        original_request=request,
        failed_response=initial_response,
        failed_parse_result=initial_parse_result,
    )
    repair_response = provider.generate(repair_request)
    repair_parse_result = parse_llm_raw_json(
        raw_text=repair_response.raw_text,
        task_type=repair_request.task_type,
    )
    _record_response(
        ledger=active_ledger,
        response=repair_response,
        attempt_type="repair",
        parse_result=repair_parse_result,
    )
    if repair_parse_result.ok:
        return LLMGenerationResult(
            ok=True,
            requested_task_type=request.task_type,
            content=repair_parse_result.content,
            response=repair_response,
            parse_result=repair_parse_result,
            repair_used=True,
            fallback_used=False,
            initial_response=initial_response,
            initial_parse_result=initial_parse_result,
            repair_response=repair_response,
            repair_parse_result=repair_parse_result,
            router_selection=router_selection,
            router_usage_update=router_usage_update,
            quota_usage_updates=quota_usage_updates,
        )

    fallback_response, fallback_parse_result = _build_fallback_response(
        original_request=request,
    )
    _record_fallback(
        ledger=active_ledger,
        response=fallback_response,
        fallback_reason=repair_parse_result,
    )

    return LLMGenerationResult(
        ok=True,
        requested_task_type=request.task_type,
        content=fallback_parse_result.content,
        response=fallback_response,
        parse_result=fallback_parse_result,
        repair_used=True,
        fallback_used=True,
        fallback_reason=repair_parse_result.error_code,
        initial_response=initial_response,
        initial_parse_result=initial_parse_result,
        repair_response=repair_response,
        repair_parse_result=repair_parse_result,
        router_selection=router_selection,
        router_usage_update=router_usage_update,
        quota_usage_updates=quota_usage_updates,
    )


def _build_repair_request(
    *,
    original_request: LLMRequest,
    failed_response: LLMResponse,
    failed_parse_result: LLMParseResult,
) -> LLMRequest:
    metadata = dict(original_request.metadata)
    metadata.update(
        {
            "repair_of_task_type": original_request.task_type,
            "invalid_raw_text": failed_response.raw_text,
            "parse_error_code": failed_parse_result.error_code,
            "parse_error_message": failed_parse_result.error_message,
        }
    )

    return LLMRequest(
        task_type="json_repair",
        messages=[
            {
                "role": "system",
                "content": (
                    "The previous model output was invalid JSON or failed schema "
                    "validation. Repair it to match the normal turn JSON schema."
                ),
            },
            {
                "role": "user",
                "content": failed_response.raw_text,
            },
        ],
        metadata=metadata,
        max_output_tokens=original_request.max_output_tokens,
    )


def _router_selection_failure_result(
    *,
    request: LLMRequest,
    failure: LLMRouterSelectionFailure,
) -> LLMGenerationResult:
    return LLMGenerationResult(
        ok=False,
        requested_task_type=request.task_type,
        fallback_reason=failure.error_code,
        error_code="router_selection_failed",
        error_message=failure.message,
        router_selection_failure=failure,
    )


def _quota_failure_result(
    *,
    request: LLMRequest,
    failure: LLMQuotaFailure,
    router_selection: Optional[LLMRouterSelection],
) -> LLMGenerationResult:
    return LLMGenerationResult(
        ok=False,
        requested_task_type=request.task_type,
        fallback_reason=failure.error_code,
        error_code="quota_exceeded",
        error_message=failure.message,
        quota_failure=failure,
        router_selection=router_selection,
    )


def _select_initial_router_model(
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


def _check_quota_preflight(
    *,
    quota_policy: Optional[InMemoryLLMQuotaPolicy],
    request: LLMRequest,
) -> Optional[LLMQuotaFailure]:
    if quota_policy is None:
        return None

    return quota_policy.check_request(
        requested_tokens=_estimate_request_total_tokens(request),
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


def _record_response(
    *,
    ledger: Optional[LLMCallLedger],
    response: LLMResponse,
    attempt_type: LLMCallAttemptType,
    parse_result: LLMParseResult,
) -> Optional[LLMCallLedgerEntry]:
    if ledger is None:
        return None

    return ledger.record_response(
        response=response,
        attempt_type=attempt_type,
        parse_result=parse_result,
    )


def _record_initial_router_usage(
    *,
    router: Optional[InMemoryLLMRouter],
    entry: Optional[LLMCallLedgerEntry],
) -> Optional[LLMRouterUsageUpdate]:
    if router is None or entry is None:
        return None

    return router.record_usage_from_ledger_entry(entry)


def _record_initial_quota_usage(
    *,
    quota_policy: Optional[InMemoryLLMQuotaPolicy],
    entry: Optional[LLMCallLedgerEntry],
) -> list[LLMQuotaUsageUpdate]:
    if quota_policy is None or entry is None:
        return []

    return quota_policy.record_usage_from_ledger_entry(entry)


def _record_fallback(
    *,
    ledger: Optional[LLMCallLedger],
    response: LLMResponse,
    fallback_reason: LLMParseResult,
) -> None:
    if ledger is None:
        return

    ledger.record_fallback(
        response=response,
        fallback_reason=fallback_reason,
    )


def _build_fallback_response(
    *,
    original_request: LLMRequest,
) -> tuple[LLMResponse, LLMParseResult]:
    content = _fallback_normal_turn_content(original_request=original_request)
    raw_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
    parse_result = parse_llm_raw_json(
        raw_text=raw_text,
        task_type=original_request.task_type,
    )
    if not parse_result.ok:
        raise RuntimeError(
            "Deterministic normal-turn fallback failed internal schema validation."
        )

    return (
        LLMResponse(
            provider="local-fallback",
            model="deterministic-normal-turn-v1",
            task_type=original_request.task_type,
            content=parse_result.content or content,
            usage=LLMUsage(
                input_tokens=0,
                output_tokens=_estimate_local_tokens(raw_text),
                estimated=True,
            ),
            latency_ms=0,
            raw_text=raw_text,
            fallback_used=True,
        ),
        parse_result,
    )


def _fallback_normal_turn_content(*, original_request: LLMRequest) -> dict[str, Any]:
    protagonist_name = _metadata_text(
        original_request.metadata,
        key="protagonist_name",
        default="主角",
    )
    player_action = _metadata_text(
        original_request.metadata,
        key="player_action",
        default="当前行动",
    )
    pacing_stage = _metadata_text(
        original_request.metadata,
        key="chapter_pacing_stage",
        default="setup",
    )
    choices = _fallback_choices_for_pacing_stage(pacing_stage)

    return {
        "narrative": (
            f"局势短暂失去清晰反馈，{protagonist_name}先稳住脚步，"
            f"把「{player_action}」收束为谨慎试探。为了保持故事连贯，"
            "系统没有让这一页草草跳到选择，而是先让主角重新确认环境、"
            "同伴反应和眼前线索之间的关系。\n\n"
            "这个保守推进没有制造夸张反转，却给出一个可继续追查的落点："
            "刚才的行动影响了局势里某个细小但真实的部分，也让隐藏的阻力"
            "更接近被看见。\n\n"
            f"当前页按{_fallback_pacing_label(pacing_stage)}节奏推进，"
            "当这些信息收束起来，下一步才真正变成一个会影响后续走向的选择。"
        ),
        "choices": choices,
        "state_patch": {
            "active_goal": None,
            "short_summary_append": "模型输出异常，系统以保守 fallback 推进当前场景。",
            "relationships": {},
            "inventory_add": [],
            "inventory_remove_ids": [],
            "stats_delta": {
                "danger": 1,
                "reputation": 0,
                "power": 0,
                "health": 0,
            },
            "flags_set": {"llm_fallback_turn": True},
            "chapter_progress_delta": 1,
        },
        "memory_update": {
            "new_facts": ["本回合使用 deterministic fallback 保持故事连续"],
            "open_threads": [],
            "resolved_threads": [],
        },
        "safety": {
            "safe": True,
            "reason": "deterministic fallback after provider JSON repair failure",
        },
    }


def _fallback_pacing_label(stage: str) -> str:
    return {
        "setup": "铺垫",
        "pressure": "加压",
        "reveal": "揭示",
        "turning_point": "转折",
    }.get(stage, "铺垫")


def _fallback_choices_for_pacing_stage(stage: str) -> list[dict[str, str]]:
    choices_by_stage = {
        "setup": [
            {"id": "choice_1", "label": "稳住现场，补全关键细节", "risk": "low"},
            {"id": "choice_2", "label": "接近可能的盟友，换取第一层信息", "risk": "medium"},
            {"id": "choice_3", "label": "绕开明面规则，确认隐藏入口", "risk": "high"},
        ],
        "pressure": [
            {"id": "choice_1", "label": "守住已有线索，先稳住身边人", "risk": "low"},
            {"id": "choice_2", "label": "用可控代价试探对方反应", "risk": "medium"},
            {"id": "choice_3", "label": "抢在对手前打乱当前局面", "risk": "high"},
        ],
        "reveal": [
            {"id": "choice_1", "label": "把两条线索并在一起验证", "risk": "low"},
            {"id": "choice_2", "label": "向可靠角色摊开部分真相", "risk": "medium"},
            {"id": "choice_3", "label": "跟随最危险的线索追到源头", "risk": "high"},
        ],
        "turning_point": [
            {"id": "choice_1", "label": "收束证据，准备进入下一章", "risk": "low"},
            {"id": "choice_2", "label": "逼关键人物当场表态", "risk": "medium"},
            {"id": "choice_3", "label": "赌上身份撕开本章真正缺口", "risk": "high"},
        ],
    }
    return choices_by_stage.get(stage, choices_by_stage["setup"])


def _metadata_text(metadata: dict[str, Any], *, key: str, default: str) -> str:
    value = metadata.get(key, default)
    if value is None:
        return default
    return str(value)


def _estimate_local_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _estimate_request_input_tokens(request: LLMRequest) -> int:
    text = " ".join(message.content for message in request.messages)
    return _estimate_local_tokens(text)


def _estimate_request_total_tokens(request: LLMRequest) -> int:
    return _estimate_request_input_tokens(request) + request.max_output_tokens
