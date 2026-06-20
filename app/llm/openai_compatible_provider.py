from __future__ import annotations

import json
import time
from typing import Any, Callable, Literal, Optional, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.llm.provider import (
    LLMRequest,
    LLMResponse,
    LLMTaskType,
    LLMUsage,
    model_tier_for_task,
)


OpenAICompatibleProviderErrorCode = Literal[
    "provider_disabled_in_fake_mode",
    "malformed_provider_response",
    "provider_not_configured",
    "provider_unavailable",
]


class OpenAICompatibleProviderFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: OpenAICompatibleProviderErrorCode
    message: str = Field(min_length=1)
    missing_settings: list[str] = Field(default_factory=list)


class OpenAICompatibleProviderError(Exception):
    def __init__(self, failure: OpenAICompatibleProviderFailure) -> None:
        self.failure = failure
        super().__init__(failure.message)


class OpenAICompatibleProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    api_key: str = Field(min_length=1, repr=False)
    fast_model: str = Field(min_length=1)
    quality_model: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)


class OpenAICompatibleProviderMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    fast_model: str = Field(min_length=1)
    quality_model: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)
    fake_mode_guard: bool = True
    transport_configured: bool = False


class OpenAICompatibleChatTransport(Protocol):
    def send_chat_completion(
        self,
        *,
        base_url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        ...


class OpenAICompatibleHTTPTransport:
    def __init__(
        self,
        *,
        urlopen: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._urlopen = urlopen or urllib_request.urlopen

    def send_chat_completion(
        self,
        *,
        base_url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib_request.Request(
            _chat_completions_url(base_url),
            data=request_body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self._urlopen(request, timeout=timeout_seconds) as response:
                status_code = _response_status_code(response)
                response_body = response.read()
        except urllib_error.HTTPError as exc:
            raise _provider_unavailable(
                f"OpenAI-compatible provider HTTP request failed with status {exc.code}."
            ) from exc
        except urllib_error.URLError as exc:
            raise _provider_unavailable(
                "OpenAI-compatible provider HTTP request failed."
            ) from exc
        except TimeoutError as exc:
            raise _provider_unavailable(
                "OpenAI-compatible provider HTTP request timed out."
            ) from exc

        if status_code < 200 or status_code >= 300:
            raise _provider_unavailable(
                f"OpenAI-compatible provider HTTP request failed with status {status_code}."
            )

        return _decode_response_json(response_body)


class OpenAICompatibleLLMProvider:
    def __init__(
        self,
        config: OpenAICompatibleProviderConfig,
        *,
        transport: Optional[OpenAICompatibleChatTransport] = None,
    ) -> None:
        self.config = config
        self.name = config.provider
        self._transport = transport

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: Optional[OpenAICompatibleChatTransport] = None,
    ) -> "OpenAICompatibleLLMProvider":
        if settings.llm_fake_mode:
            raise OpenAICompatibleProviderError(
                OpenAICompatibleProviderFailure(
                    error_code="provider_disabled_in_fake_mode",
                    message="OpenAI-compatible provider is disabled while fake mode is enabled.",
                )
            )

        missing_settings = _missing_required_settings(settings)
        if missing_settings:
            raise OpenAICompatibleProviderError(
                OpenAICompatibleProviderFailure(
                    error_code="provider_not_configured",
                    message="OpenAI-compatible provider settings are incomplete.",
                    missing_settings=missing_settings,
                )
            )

        config = OpenAICompatibleProviderConfig(
            provider=_non_empty(settings.llm_provider),
            base_url=_non_empty(settings.llm_base_url),
            api_key=_non_empty(settings.llm_api_key),
            fast_model=_non_empty(settings.llm_model_fast),
            quality_model=_non_empty(settings.llm_model_quality),
            timeout_seconds=settings.llm_timeout_seconds,
        )

        return cls(config, transport=transport)

    def metadata(self) -> OpenAICompatibleProviderMetadata:
        return OpenAICompatibleProviderMetadata(
            provider=self.config.provider,
            base_url=self.config.base_url,
            fast_model=self.config.fast_model,
            quality_model=self.config.quality_model,
            timeout_seconds=self.config.timeout_seconds,
            transport_configured=self._transport is not None,
        )

    def model_for_task(self, task_type: LLMTaskType) -> str:
        if model_tier_for_task(task_type) == "quality":
            return self.config.quality_model

        return self.config.fast_model

    def build_chat_completion_payload(
        self,
        request: LLMRequest,
        *,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = {
            "model": model or self.model_for_task(request.task_type),
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": request.max_output_tokens,
        }
        if self.config.provider.lower() == "deepseek":
            payload["thinking"] = {"type": "disabled"}

        return payload

    def parse_chat_completion_response(
        self,
        response_payload: dict[str, Any],
        *,
        request: LLMRequest,
        model: Optional[str] = None,
        latency_ms: int = 0,
    ) -> LLMResponse:
        if not isinstance(response_payload, dict):
            raise _malformed_response(
                "OpenAI-compatible response payload must be an object."
            )

        raw_text = _extract_message_content(response_payload)
        usage = _usage_from_response_payload(
            response_payload=response_payload,
            request=request,
            raw_text=raw_text,
        )
        return LLMResponse(
            provider=self.name,
            model=model or _response_model(response_payload) or self.model_for_task(
                request.task_type
            ),
            task_type=request.task_type,
            content=_content_dict_from_raw_text(raw_text),
            usage=usage,
            latency_ms=latency_ms,
            raw_text=raw_text,
            fallback_used=False,
        )

    def generate(self, request: LLMRequest) -> LLMResponse:
        if self._transport is None:
            raise _provider_unavailable(
                "OpenAI-compatible provider transport is not configured."
            )

        model = self.model_for_task(request.task_type)
        payload = self.build_chat_completion_payload(request, model=model)
        started_at = time.perf_counter()

        try:
            response_payload = self._transport.send_chat_completion(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                payload=payload,
                timeout_seconds=self.config.timeout_seconds,
            )
        except OpenAICompatibleProviderError:
            raise
        except Exception as exc:
            raise _provider_unavailable(
                "OpenAI-compatible provider transport failed."
            ) from exc

        latency_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        return self.parse_chat_completion_response(
            response_payload,
            request=request,
            model=model,
            latency_ms=latency_ms,
        )


def build_openai_compatible_provider_from_settings(
    settings: Settings,
    *,
    urlopen: Optional[Callable[..., Any]] = None,
) -> OpenAICompatibleLLMProvider:
    if settings.llm_fake_mode or _missing_required_settings(settings):
        return OpenAICompatibleLLMProvider.from_settings(settings)

    return OpenAICompatibleLLMProvider.from_settings(
        settings,
        transport=OpenAICompatibleHTTPTransport(urlopen=urlopen),
    )


def _missing_required_settings(settings: Settings) -> list[str]:
    missing: list[str] = []
    for field_name, value in (
        ("LLM_PROVIDER", settings.llm_provider),
        ("LLM_BASE_URL", settings.llm_base_url),
        ("LLM_API_KEY", settings.llm_api_key),
        ("LLM_MODEL_FAST", settings.llm_model_fast),
        ("LLM_MODEL_QUALITY", settings.llm_model_quality),
    ):
        if value is None or str(value).strip() == "":
            missing.append(field_name)

    if settings.llm_timeout_seconds <= 0:
        missing.append("LLM_TIMEOUT_SECONDS")

    return missing


def _chat_completions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _response_status_code(response: Any) -> int:
    status_code = getattr(response, "status", None)
    if status_code is None:
        status_code = getattr(response, "code", 200)

    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise _provider_unavailable(
            "OpenAI-compatible provider HTTP response had an invalid status."
        )

    return status_code


def _decode_response_json(response_body: bytes) -> dict[str, Any]:
    try:
        decoded_body = response_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _malformed_response(
            "OpenAI-compatible HTTP response body must be UTF-8 JSON."
        ) from exc

    try:
        response_payload = json.loads(decoded_body)
    except json.JSONDecodeError as exc:
        raise _malformed_response(
            "OpenAI-compatible HTTP response body must be valid JSON."
        ) from exc

    if not isinstance(response_payload, dict):
        raise _malformed_response(
            "OpenAI-compatible HTTP response JSON must be an object."
        )

    return response_payload


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise _malformed_response("OpenAI-compatible response must include choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise _malformed_response("OpenAI-compatible response choice must be an object.")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise _malformed_response("OpenAI-compatible response choice must include message.")

    content = message.get("content")
    if not isinstance(content, str):
        raise _malformed_response(
            "OpenAI-compatible response message content must be a string."
        )

    return content


def _usage_from_response_payload(
    *,
    response_payload: dict[str, Any],
    request: LLMRequest,
    raw_text: str,
) -> LLMUsage:
    usage = response_payload.get("usage")
    if usage is None:
        return LLMUsage(
            input_tokens=_estimate_request_tokens(request),
            output_tokens=_estimate_tokens(raw_text),
            estimated=True,
        )

    if not isinstance(usage, dict):
        raise _malformed_response("OpenAI-compatible response usage must be an object.")

    prompt_tokens = _non_negative_int(usage.get("prompt_tokens"), "prompt_tokens")
    completion_tokens = _non_negative_int(
        usage.get("completion_tokens"),
        "completion_tokens",
    )

    return LLMUsage(
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        estimated=False,
    )


def _content_dict_from_raw_text(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}

    return parsed


def _response_model(response_payload: dict[str, Any]) -> Optional[str]:
    model = response_payload.get("model")
    if isinstance(model, str) and model.strip():
        return model

    return None


def _non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _malformed_response(
            f"OpenAI-compatible response usage.{field_name} must be a non-negative integer."
        )

    return value


def _estimate_request_tokens(request: LLMRequest) -> int:
    text = " ".join(message.content for message in request.messages)
    return _estimate_tokens(text)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _malformed_response(message: str) -> OpenAICompatibleProviderError:
    return OpenAICompatibleProviderError(
        OpenAICompatibleProviderFailure(
            error_code="malformed_provider_response",
            message=message,
        )
    )


def _provider_unavailable(message: str) -> OpenAICompatibleProviderError:
    return OpenAICompatibleProviderError(
        OpenAICompatibleProviderFailure(
            error_code="provider_unavailable",
            message=message,
        )
    )


def _non_empty(value: str | None) -> str:
    if value is None:
        return ""

    return str(value).strip()
