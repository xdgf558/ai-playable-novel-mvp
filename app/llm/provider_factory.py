from __future__ import annotations

from typing import Any, Callable, Optional

from app.core.config import Settings
from app.llm.fake_provider import FakeLLMProvider
from app.llm.openai_compatible_provider import (
    build_openai_compatible_provider_from_settings,
)
from app.llm.provider import LLMProvider


def build_llm_provider_from_settings(
    settings: Settings,
    *,
    urlopen: Optional[Callable[..., Any]] = None,
) -> LLMProvider:
    if settings.llm_fake_mode:
        return FakeLLMProvider(
            fast_model=_settings_model_name(settings.llm_model_fast, "fake-fast"),
            quality_model=_settings_model_name(
                settings.llm_model_quality,
                "fake-quality",
            ),
        )

    return build_openai_compatible_provider_from_settings(settings, urlopen=urlopen)


def _settings_model_name(value: str | None, default: str) -> str:
    if value is None or value.strip() == "":
        return default

    return value.strip()
