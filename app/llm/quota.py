from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.llm.ledger import LLMCallLedgerEntry


LLMQuotaSubject = Literal["user", "story"]
LLMQuotaFailureCode = Literal[
    "user_token_budget_exhausted",
    "story_token_budget_exhausted",
]


class LLMQuotaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: LLMQuotaSubject
    subject_id: str = Field(min_length=1)
    monthly_token_budget: int = Field(ge=0)
    monthly_tokens_used: int = Field(default=0, ge=0)

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.monthly_token_budget - self.monthly_tokens_used)

    def failure_for_request(self, *, requested_tokens: int) -> Optional["LLMQuotaFailure"]:
        if self.monthly_tokens_used + requested_tokens <= self.monthly_token_budget:
            return None

        return LLMQuotaFailure(
            subject=self.subject,
            subject_id=self.subject_id,
            monthly_token_budget=self.monthly_token_budget,
            monthly_tokens_used=self.monthly_tokens_used,
            requested_tokens=requested_tokens,
            remaining_tokens=self.remaining_tokens,
            error_code=_failure_code_for_subject(self.subject),
            message=_failure_message_for_subject(self.subject),
        )


class LLMQuotaFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: LLMQuotaSubject
    subject_id: str = Field(min_length=1)
    monthly_token_budget: int = Field(ge=0)
    monthly_tokens_used: int = Field(ge=0)
    requested_tokens: int = Field(ge=0)
    remaining_tokens: int = Field(ge=0)
    error_code: LLMQuotaFailureCode
    message: str = Field(min_length=1)


class LLMQuotaError(Exception):
    def __init__(self, failure: LLMQuotaFailure) -> None:
        self.failure = failure
        super().__init__(failure.message)


class LLMQuotaUsageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: LLMQuotaSubject
    subject_id: str = Field(min_length=1)
    tokens_added: int = Field(ge=0)
    monthly_tokens_used: int = Field(ge=0)
    remaining_tokens: int = Field(ge=0)


class InMemoryLLMQuotaPolicy:
    def __init__(
        self,
        *,
        user_quota: Optional[LLMQuotaState] = None,
        story_quota: Optional[LLMQuotaState] = None,
    ) -> None:
        self.user_quota = user_quota
        self.story_quota = story_quota

    def check_request(self, *, requested_tokens: int) -> Optional[LLMQuotaFailure]:
        if requested_tokens < 0:
            raise ValueError("requested_tokens must be non-negative.")

        for quota in (self.user_quota, self.story_quota):
            if quota is None:
                continue

            failure = quota.failure_for_request(requested_tokens=requested_tokens)
            if failure is not None:
                return failure

        return None

    def record_usage_from_ledger_entry(
        self,
        entry: LLMCallLedgerEntry,
    ) -> list[LLMQuotaUsageUpdate]:
        if entry.attempt_type == "fallback":
            return []

        updates: list[LLMQuotaUsageUpdate] = []
        for quota in (self.user_quota, self.story_quota):
            if quota is None:
                continue

            quota.monthly_tokens_used += entry.total_tokens
            updates.append(
                LLMQuotaUsageUpdate(
                    subject=quota.subject,
                    subject_id=quota.subject_id,
                    tokens_added=entry.total_tokens,
                    monthly_tokens_used=quota.monthly_tokens_used,
                    remaining_tokens=quota.remaining_tokens,
                )
            )

        return updates


def _failure_code_for_subject(subject: LLMQuotaSubject) -> LLMQuotaFailureCode:
    if subject == "user":
        return "user_token_budget_exhausted"

    return "story_token_budget_exhausted"


def _failure_message_for_subject(subject: LLMQuotaSubject) -> str:
    if subject == "user":
        return "User token budget exceeded."

    return "Story token budget exceeded."
