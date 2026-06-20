from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.llm.parser import LLMParseResult
from app.llm.provider import LLMResponse, LLMTaskType


LLMCallAttemptType = Literal["initial", "repair", "fallback"]
LLMCallStatus = Literal["success", "parse_failed", "fallback"]


class LLMCallLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_type: LLMTaskType
    attempt_type: LLMCallAttemptType
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    token_usage_estimated: bool
    status: LLMCallStatus
    latency_ms: int = Field(ge=0)
    fallback_used: bool = False
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class LLMCallLedger:
    def __init__(self) -> None:
        self._entries: list[LLMCallLedgerEntry] = []

    def record_response(
        self,
        *,
        response: LLMResponse,
        attempt_type: LLMCallAttemptType,
        parse_result: LLMParseResult,
    ) -> LLMCallLedgerEntry:
        status: LLMCallStatus = "success" if parse_result.ok else "parse_failed"
        entry = LLMCallLedgerEntry(
            task_type=response.task_type,
            attempt_type=attempt_type,
            provider=response.provider,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            token_usage_estimated=response.usage.estimated,
            status=status,
            latency_ms=response.latency_ms,
            fallback_used=response.fallback_used,
            error_code=None if parse_result.ok else parse_result.error_code,
            error_message=None if parse_result.ok else parse_result.error_message,
        )
        return self.record(entry)

    def record_fallback(
        self,
        *,
        response: LLMResponse,
        fallback_reason: LLMParseResult,
    ) -> LLMCallLedgerEntry:
        entry = LLMCallLedgerEntry(
            task_type=response.task_type,
            attempt_type="fallback",
            provider=response.provider,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            token_usage_estimated=response.usage.estimated,
            status="fallback",
            latency_ms=response.latency_ms,
            fallback_used=True,
            error_code=fallback_reason.error_code,
            error_message=fallback_reason.error_message,
        )
        return self.record(entry)

    def record(self, entry: LLMCallLedgerEntry) -> LLMCallLedgerEntry:
        self._entries.append(entry)
        return entry

    def list_entries(self) -> list[LLMCallLedgerEntry]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()


default_llm_call_ledger = LLMCallLedger()
