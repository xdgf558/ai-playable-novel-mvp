from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.llm.ledger import LLMCallLedgerEntry
from app.llm.provider import LLMModelTier, LLMTaskType, model_tier_for_task


LLMRouterSkipReason = Literal[
    "disabled",
    "unhealthy",
    "daily_budget_exhausted",
    "monthly_budget_exhausted",
]
LLMRouterSelectionErrorCode = Literal["no_available_model"]


class LLMModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    tier: LLMModelTier
    priority: int = Field(ge=0)
    enabled: bool = True
    healthy: bool = True
    daily_token_budget: int = Field(ge=0)
    monthly_token_budget: int = Field(ge=0)
    daily_tokens_used: int = Field(default=0, ge=0)
    monthly_tokens_used: int = Field(default=0, ge=0)
    max_output_tokens: int = Field(default=900, ge=1, le=4000)
    notes: Optional[str] = None

    @property
    def identity(self) -> str:
        return f"{self.provider}/{self.model}"

    def skip_reason(self, *, required_tokens: int) -> Optional[LLMRouterSkipReason]:
        if not self.enabled:
            return "disabled"
        if not self.healthy:
            return "unhealthy"
        if self.daily_tokens_used + required_tokens > self.daily_token_budget:
            return "daily_budget_exhausted"
        if self.monthly_tokens_used + required_tokens > self.monthly_token_budget:
            return "monthly_budget_exhausted"

        return None


class LLMRouterSkippedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reason: LLMRouterSkipReason


class LLMRouterSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: LLMTaskType
    tier: LLMModelTier
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_output_tokens: int = Field(ge=1, le=4000)
    estimated_input_tokens: int = Field(ge=0)
    estimated_total_tokens: int = Field(ge=0)
    fallback_used: bool = False
    fallback_chain: list[str]
    skipped_models: list[LLMRouterSkippedModel] = Field(default_factory=list)


class LLMRouterUsageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    tokens_added: int = Field(ge=0)
    daily_tokens_used: int = Field(ge=0)
    monthly_tokens_used: int = Field(ge=0)


class LLMRouterSelectionFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: LLMTaskType
    tier: LLMModelTier
    estimated_input_tokens: int = Field(ge=0)
    requested_max_output_tokens: Optional[int] = Field(default=None, ge=1, le=4000)
    fallback_chain: list[str]
    skipped_models: list[LLMRouterSkippedModel] = Field(default_factory=list)
    error_code: LLMRouterSelectionErrorCode = "no_available_model"
    message: str = Field(min_length=1)


class LLMRouterSelectionError(Exception):
    def __init__(self, failure: LLMRouterSelectionFailure) -> None:
        self.failure = failure
        super().__init__(failure.message)


class InMemoryLLMRouter:
    def __init__(self, model_configs: Optional[list[LLMModelConfig]] = None) -> None:
        configs = (
            model_configs
            if model_configs is not None
            else list(default_fake_model_configs())
        )
        self._model_configs = sorted(
            [config.model_copy(deep=True) for config in configs],
            key=lambda config: (
                config.tier,
                config.priority,
                config.provider,
                config.model,
            ),
        )

    def select_model(
        self,
        *,
        task_type: LLMTaskType,
        estimated_input_tokens: int = 0,
        max_output_tokens: Optional[int] = None,
    ) -> LLMRouterSelection:
        if estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be non-negative.")

        tier = model_tier_for_task(task_type)
        skipped_models: list[LLMRouterSkippedModel] = []
        fallback_chain: list[str] = []

        for config in self._configs_for_tier(tier):
            output_cap = _output_cap(config=config, requested=max_output_tokens)
            required_tokens = estimated_input_tokens + output_cap
            fallback_chain.append(config.identity)
            skip_reason = config.skip_reason(required_tokens=required_tokens)
            if skip_reason is not None:
                skipped_models.append(
                    LLMRouterSkippedModel(
                        provider=config.provider,
                        model=config.model,
                        reason=skip_reason,
                    )
                )
                continue

            return LLMRouterSelection(
                task_type=task_type,
                tier=tier,
                provider=config.provider,
                model=config.model,
                max_output_tokens=output_cap,
                estimated_input_tokens=estimated_input_tokens,
                estimated_total_tokens=required_tokens,
                fallback_used=bool(skipped_models),
                fallback_chain=fallback_chain,
                skipped_models=skipped_models,
            )

        raise LLMRouterSelectionError(
            LLMRouterSelectionFailure(
                task_type=task_type,
                tier=tier,
                estimated_input_tokens=estimated_input_tokens,
                requested_max_output_tokens=max_output_tokens,
                fallback_chain=fallback_chain,
                skipped_models=skipped_models,
                message=f"No available model for {tier} tier.",
            )
        )

    def list_model_configs(self) -> list[LLMModelConfig]:
        return [config.model_copy(deep=True) for config in self._model_configs]

    def record_usage_from_ledger_entry(
        self,
        entry: LLMCallLedgerEntry,
    ) -> Optional[LLMRouterUsageUpdate]:
        if entry.attempt_type == "fallback":
            return None

        config = self._find_model_config(provider=entry.provider, model=entry.model)
        if config is None:
            return None

        config.daily_tokens_used += entry.total_tokens
        config.monthly_tokens_used += entry.total_tokens

        return LLMRouterUsageUpdate(
            provider=config.provider,
            model=config.model,
            tokens_added=entry.total_tokens,
            daily_tokens_used=config.daily_tokens_used,
            monthly_tokens_used=config.monthly_tokens_used,
        )

    def record_usage_from_ledger_entries(
        self,
        entries: list[LLMCallLedgerEntry],
    ) -> list[LLMRouterUsageUpdate]:
        updates: list[LLMRouterUsageUpdate] = []
        for entry in entries:
            update = self.record_usage_from_ledger_entry(entry)
            if update is not None:
                updates.append(update)

        return updates

    def _configs_for_tier(self, tier: LLMModelTier) -> list[LLMModelConfig]:
        return [config for config in self._model_configs if config.tier == tier]

    def _find_model_config(
        self,
        *,
        provider: str,
        model: str,
    ) -> Optional[LLMModelConfig]:
        for config in self._model_configs:
            if config.provider == provider and config.model == model:
                return config

        return None


def default_fake_model_configs() -> tuple[LLMModelConfig, ...]:
    return (
        LLMModelConfig(
            provider="fake",
            model="fake-fast",
            tier="fast",
            priority=10,
            daily_token_budget=100_000,
            monthly_token_budget=1_000_000,
            max_output_tokens=900,
        ),
        LLMModelConfig(
            provider="fake",
            model="fake-fast-backup",
            tier="fast",
            priority=20,
            daily_token_budget=100_000,
            monthly_token_budget=1_000_000,
            max_output_tokens=900,
        ),
        LLMModelConfig(
            provider="fake",
            model="fake-quality",
            tier="quality",
            priority=10,
            daily_token_budget=50_000,
            monthly_token_budget=500_000,
            max_output_tokens=1800,
        ),
        LLMModelConfig(
            provider="fake",
            model="fake-quality-backup",
            tier="quality",
            priority=20,
            daily_token_budget=50_000,
            monthly_token_budget=500_000,
            max_output_tokens=1800,
        ),
    )


def _output_cap(*, config: LLMModelConfig, requested: Optional[int]) -> int:
    if requested is None:
        return config.max_output_tokens

    if requested < 1:
        raise ValueError("max_output_tokens must be positive when provided.")

    return min(requested, config.max_output_tokens)


default_llm_router = InMemoryLLMRouter()
