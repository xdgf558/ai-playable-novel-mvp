import json
from typing import Any, Optional
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.fake_provider import FakeLLMProvider
from app.llm.gateway import generate_normal_turn_with_repair
from app.llm.ledger import LLMCallLedger, LLMCallLedgerEntry
from app.llm.openai_compatible_provider import (
    OpenAICompatibleHTTPTransport,
    OpenAICompatibleLLMProvider,
    OpenAICompatibleProviderError,
    build_openai_compatible_provider_from_settings,
)
from app.llm.parser import parse_llm_raw_json
from app.llm.provider_factory import build_llm_provider_from_settings
from app.llm.story_opening import (
    assemble_story_state_from_opening_payload,
    build_story_opening_request,
    generate_story_opening,
    validate_story_opening_payload,
)
from app.llm.provider import (
    LLMRequest,
    LLMResponse,
    LLM_TASK_TYPES,
    LLMUsage,
    model_tier_for_task,
)
from app.llm.quota import InMemoryLLMQuotaPolicy, LLMQuotaState
from app.llm.router import InMemoryLLMRouter, LLMModelConfig, LLMRouterSelectionError
from app.schemas.stories import CreateStoryRequest
from app.schemas.templates import StoryTemplate
from app.services.state_manager import validate_story_state
from app.services.template_service import get_template_by_id


class _LocalOpenAITransport:
    def __init__(
        self,
        response_payload: Optional[dict[str, Any]] = None,
        *,
        error: Optional[Exception] = None,
    ) -> None:
        self.response_payload = response_payload or {}
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def send_chat_completion(
        self,
        *,
        base_url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "base_url": base_url,
                "api_key": api_key,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error

        return self.response_payload


class _LocalHTTPResponse:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.body = body
        self.status = status

    def __enter__(self) -> "_LocalHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def read(self) -> bytes:
        return self.body


def _request(
    task_type: str,
    metadata: Optional[dict] = None,
    *,
    max_output_tokens: int = 900,
) -> LLMRequest:
    return LLMRequest(
        task_type=task_type,
        messages=[
            {
                "role": "system",
                "content": "Return strict JSON for the fake provider test.",
            },
            {"role": "user", "content": "推进一个可测试的故事任务。"},
        ],
        metadata=metadata or {},
        max_output_tokens=max_output_tokens,
    )


def _valid_normal_turn_content(
    *,
    narrative: str = "本地 HTTP 模拟响应推进了一步。",
) -> dict[str, Any]:
    return {
        "narrative": narrative,
        "choices": [
            {"id": "choice_1", "label": "继续观察线索", "risk": "low"},
            {"id": "choice_2", "label": "主动试探对方", "risk": "medium"},
            {"id": "choice_3", "label": "直接逼近危险源", "risk": "high"},
        ],
        "state_patch": {
            "active_goal": None,
            "short_summary_append": "OpenAI-compatible mocked HTTP 推进了当前场景。",
            "relationships": {
                "npc_001": {
                    "affinity_delta": 1,
                    "trust_delta": 0,
                    "status": None,
                }
            },
            "inventory_add": [],
            "inventory_remove_ids": [],
            "stats_delta": {
                "danger": 1,
                "reputation": 0,
                "power": 0,
                "health": 0,
            },
            "flags_set": {"mocked_http_provider_turn": True},
            "chapter_progress_delta": 1,
        },
        "memory_update": {
            "new_facts": ["mocked HTTP provider returned a valid normal turn"],
            "open_threads": ["verify real-provider gateway path later"],
            "resolved_threads": [],
        },
        "safety": {
            "safe": True,
            "reason": "local mocked HTTP response",
        },
    }


def _configured_openai_provider(
    transport: Optional[Any] = None,
) -> OpenAICompatibleLLMProvider:
    return OpenAICompatibleLLMProvider.from_settings(
        Settings(
            llm_fake_mode=False,
            llm_provider="qwen",
            llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_api_key="secret-key",
            llm_model_fast="qwen-flash",
            llm_model_quality="qwen-plus",
            llm_timeout_seconds=45,
        ),
        transport=transport,
    )


def _story_creation_request() -> CreateStoryRequest:
    return CreateStoryRequest(
        device_id=uuid4(),
        template_id="xianxia_rise",
        locale="zh-Hans",
        protagonist={
            "name": "林澈",
            "pronouns": "他",
            "age_band": "adult",
            "personality": ["冷静", "不服输"],
            "starting_role": "被宗门轻视的外门弟子",
            "main_goal": "查清家族没落真相",
            "special_ability": "能听见灵气裂隙中的低语",
        },
        tone="热血、悬念、成长",
        content_rating="teen",
    )


def _story_template(template_id: str = "xianxia_rise") -> StoryTemplate:
    template = get_template_by_id(template_id)
    assert template is not None
    return template


def test_llm_task_type_constants_cover_phase_3_router_tasks() -> None:
    assert LLM_TASK_TYPES == (
        "story_bible_generation",
        "chapter_outline_generation",
        "normal_turn_generation",
        "state_extraction",
        "summary_generation",
        "json_repair",
        "safety_classification",
        "ending_generation",
    )
    assert model_tier_for_task("normal_turn_generation") == "fast"
    assert model_tier_for_task("json_repair") == "fast"
    assert model_tier_for_task("story_bible_generation") == "quality"
    assert model_tier_for_task("ending_generation") == "quality"


def test_llm_request_rejects_unknown_task_type() -> None:
    with pytest.raises(ValidationError):
        _request("unknown_task")


def test_story_opening_request_uses_story_creation_and_template_metadata() -> None:
    story_request = _story_creation_request()
    template = _story_template()

    llm_request = build_story_opening_request(
        story_request,
        template=template,
        max_output_tokens=1500,
    )

    assert llm_request.task_type == "story_bible_generation"
    assert llm_request.response_format == "json_object"
    assert llm_request.max_output_tokens == 1500
    assert llm_request.messages[0].role == "system"
    assert "strict JSON" in llm_request.messages[0].content
    assert "strict json" in llm_request.messages[0].content
    assert "EXAMPLE JSON OUTPUT" in llm_request.messages[0].content
    assert "\"story_bible\"" in llm_request.messages[0].content
    assert "substantial first page" in llm_request.messages[0].content
    assert "first-chapter rhythm" in llm_request.messages[0].content
    assert "meaningful branch directions" in llm_request.messages[0].content
    assert "investigative/conservative route" in llm_request.messages[0].content
    assert "copyrighted IP" in llm_request.messages[0].content
    assert json.loads(llm_request.messages[1].content) == llm_request.metadata
    assert llm_request.metadata["template_id"] == "xianxia_rise"
    assert llm_request.metadata["template_name"] == "修仙逆袭"
    assert llm_request.metadata["template_genre"] == "修仙"
    assert llm_request.metadata["template_tags"] == ["升级", "宗门", "秘境", "爽文"]
    assert llm_request.metadata["protagonist_name"] == "林澈"
    assert llm_request.metadata["protagonist_main_goal"] == "查清家族没落真相"
    assert llm_request.metadata["protagonist_special_ability"] == (
        "能听见灵气裂隙中的低语"
    )


def test_generate_story_opening_with_fake_provider_validates_payload() -> None:
    result = generate_story_opening(
        FakeLLMProvider(),
        _story_creation_request(),
        template=_story_template(),
    )

    assert result.request.task_type == "story_bible_generation"
    assert result.response.provider == "fake"
    assert result.response.model == "fake-quality"
    assert result.payload.title == "修仙逆袭测试开局"
    assert "林澈" in result.payload.opening_narrative
    assert result.payload.story_bible.world_rules == [
        "行动必须影响状态。",
        "剧情必须保持原创。",
    ]
    assert result.payload.story_bible.major_factions[0].name == "测试阵营"
    assert result.payload.story_bible.main_characters[0].id == "npc_001"
    assert result.payload.plot_plan.total_chapters == 8
    assert result.payload.plot_plan.chapters[0].index == 1
    assert len(result.payload.choices) == 3
    assert result.payload.choices[0].id == "choice_1"
    assert result.payload.initial_state_patch == {}


def test_generate_story_opening_with_router_records_quality_fallback_metadata() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-quality-primary",
                tier="quality",
                priority=10,
                daily_tokens_used=1_000,
                daily_token_budget=1_000,
            ),
            _model_config(
                model="fake-quality-fallback",
                tier="quality",
                priority=20,
                daily_token_budget=10_000,
            ),
        ]
    )

    result = generate_story_opening(
        FakeLLMProvider(),
        _story_creation_request(),
        template=_story_template(),
        router=router,
    )

    assert result.router_selection is not None
    assert result.router_selection.task_type == "story_bible_generation"
    assert result.router_selection.tier == "quality"
    assert result.router_selection.model == "fake-quality-fallback"
    assert result.router_selection.fallback_used is True
    assert result.router_selection.fallback_chain == [
        "fake/fake-quality-primary",
        "fake/fake-quality-fallback",
    ]
    assert result.router_selection.skipped_models[0].model == "fake-quality-primary"
    assert (
        result.router_selection.skipped_models[0].reason
        == "daily_budget_exhausted"
    )
    assert result.request.max_output_tokens == result.router_selection.max_output_tokens
    assert result.response.provider == "fake"
    assert result.response.model == "fake-quality-fallback"
    assert result.response.fallback_used is True


def test_story_opening_payload_validation_rejects_malformed_payload() -> None:
    request = build_story_opening_request(
        _story_creation_request(),
        template=_story_template(),
    )
    provider_response = FakeLLMProvider().generate(request)
    malformed_payload = dict(provider_response.content)
    malformed_payload["choices"] = malformed_payload["choices"][:2]

    with pytest.raises(ValidationError):
        validate_story_opening_payload(malformed_payload)


def test_story_opening_state_assembly_validates_current_story_state_shape() -> None:
    story_request = _story_creation_request()
    template = _story_template()
    story_id = uuid4()
    opening_result = generate_story_opening(
        FakeLLMProvider(),
        story_request,
        template=template,
    )

    state = assemble_story_state_from_opening_payload(
        opening_result.payload,
        story_id=story_id,
        story_request=story_request,
        template=template,
        updated_at="2026-05-30T12:00:00+00:00",
    )
    validated_state = validate_story_state(state)

    assert str(validated_state.story_id) == str(story_id)
    assert state["story_id"] == str(story_id)
    assert state["locale"] == "zh-Hans"
    assert state["template_id"] == "xianxia_rise"
    assert state["title"] == "修仙逆袭测试开局"
    assert state["protagonist"]["name"] == "林澈"
    assert state["story_bible"]["world_rules"] == [
        "行动必须影响状态。",
        "剧情必须保持原创。",
    ]
    assert state["plot_plan"]["total_chapters"] == 8
    assert state["current_chapter_index"] == 1
    assert state["current_scene_index"] == 1
    assert state["active_goal"] == "查清家族没落真相"
    assert state["short_summary"] == opening_result.payload.opening_narrative
    assert state["long_summary"] == opening_result.payload.opening_narrative
    assert state["relationships"] == {
        "npc_001": {
            "affinity": 0,
            "trust": 0,
            "status": "尚未信任主角",
        }
    }
    assert state["inventory"] == []
    assert state["stats"] == {
        "danger": 10,
        "reputation": 0,
        "power": 1,
        "health": 100,
    }
    assert state["flags"] == {
        "opening_created": True,
        "story_opening_generated": True,
        "opening_template_id": "xianxia_rise",
        "opening_initial_state_patch": {},
    }
    assert state["turn_count"] == 0
    assert state["updated_at"] == "2026-05-30T12:00:00+00:00"


def test_openai_compatible_provider_is_disabled_in_fake_mode() -> None:
    settings = Settings()

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        OpenAICompatibleLLMProvider.from_settings(settings)

    failure = exc_info.value.failure
    assert failure.error_code == "provider_disabled_in_fake_mode"
    assert failure.missing_settings == []


def test_openai_compatible_provider_reports_missing_config() -> None:
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="",
        llm_api_key="",
        llm_model_fast="",
        llm_model_quality="",
        llm_timeout_seconds=60,
    )

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        OpenAICompatibleLLMProvider.from_settings(settings)

    failure = exc_info.value.failure
    assert failure.error_code == "provider_not_configured"
    assert failure.missing_settings == [
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL_FAST",
        "LLM_MODEL_QUALITY",
    ]


def test_openai_compatible_provider_exposes_configured_metadata_without_api_key() -> None:
    provider = OpenAICompatibleLLMProvider.from_settings(
        Settings(
            llm_fake_mode=False,
            llm_provider="qwen",
            llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_api_key="secret-key",
            llm_model_fast="qwen-flash",
            llm_model_quality="qwen-plus",
            llm_timeout_seconds=45,
        )
    )

    metadata = provider.metadata()

    assert provider.name == "qwen"
    assert metadata.provider == "qwen"
    assert metadata.base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert metadata.fast_model == "qwen-flash"
    assert metadata.quality_model == "qwen-plus"
    assert metadata.timeout_seconds == 45
    assert metadata.model_dump().get("api_key") is None
    assert metadata.transport_configured is False
    assert provider.model_for_task("normal_turn_generation") == "qwen-flash"
    assert provider.model_for_task("story_bible_generation") == "qwen-plus"


def test_openai_compatible_provider_generate_is_unavailable_skeleton() -> None:
    provider = OpenAICompatibleLLMProvider.from_settings(
        Settings(
            llm_fake_mode=False,
            llm_provider="qwen",
            llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_api_key="secret-key",
            llm_model_fast="qwen-flash",
            llm_model_quality="qwen-plus",
            llm_timeout_seconds=45,
        )
    )

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        provider.generate(_request("normal_turn_generation"))

    assert exc_info.value.failure.error_code == "provider_unavailable"


def test_openai_compatible_provider_factory_wires_http_transport_without_construction_call() -> None:
    opener_calls: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout):
        opener_calls.append(
            {
                "url": request.full_url,
                "body": json.loads(request.data.decode("utf-8")),
                "timeout": timeout,
            }
        )
        return _LocalHTTPResponse(
            b'{"choices":[{"message":{"content":"{\\"summary\\": \\"factory\\"}"}}]}',
            status=200,
        )

    provider = build_openai_compatible_provider_from_settings(
        Settings(
            llm_fake_mode=False,
            llm_provider="qwen",
            llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_api_key="secret-key",
            llm_model_fast="qwen-flash",
            llm_model_quality="qwen-plus",
            llm_timeout_seconds=45,
        ),
        urlopen=fake_urlopen,
    )

    metadata = provider.metadata()

    assert opener_calls == []
    assert metadata.provider == "qwen"
    assert metadata.transport_configured is True
    assert metadata.model_dump().get("api_key") is None

    response = provider.generate(_request("summary_generation", max_output_tokens=222))

    assert response.model == "qwen-flash"
    assert response.content == {"summary": "factory"}
    assert len(opener_calls) == 1
    assert opener_calls[0]["url"].endswith("/chat/completions")
    assert opener_calls[0]["body"]["model"] == "qwen-flash"
    assert opener_calls[0]["body"]["max_tokens"] == 222
    assert opener_calls[0]["timeout"] == 45


def test_openai_compatible_provider_factory_preserves_fake_mode_guard() -> None:
    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        build_openai_compatible_provider_from_settings(Settings())

    assert exc_info.value.failure.error_code == "provider_disabled_in_fake_mode"


def test_openai_compatible_provider_factory_preserves_missing_config_errors() -> None:
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="",
        llm_api_key="",
        llm_model_fast="",
        llm_model_quality="",
        llm_timeout_seconds=0,
    )

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        build_openai_compatible_provider_from_settings(settings)

    failure = exc_info.value.failure
    assert failure.error_code == "provider_not_configured"
    assert failure.missing_settings == [
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL_FAST",
        "LLM_MODEL_QUALITY",
        "LLM_TIMEOUT_SECONDS",
    ]


def test_app_llm_provider_selection_returns_fake_provider_in_fake_mode() -> None:
    def unexpected_urlopen(request, timeout):
        raise AssertionError("provider selection must not open network access")

    provider = build_llm_provider_from_settings(
        Settings(
            llm_fake_mode=True,
            llm_provider="qwen",
            llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_api_key="secret-key",
            llm_model_fast="fake-custom-fast",
            llm_model_quality="fake-custom-quality",
            llm_timeout_seconds=45,
        ),
        urlopen=unexpected_urlopen,
    )

    assert isinstance(provider, FakeLLMProvider)
    assert provider.name == "fake"
    assert provider.fast_model == "fake-custom-fast"
    assert provider.quality_model == "fake-custom-quality"


def test_app_llm_provider_selection_returns_openai_provider_without_calling_it() -> None:
    opener_calls: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout):
        opener_calls.append({"url": request.full_url, "timeout": timeout})
        return _LocalHTTPResponse(
            b'{"choices":[{"message":{"content":"{\\"summary\\": \\"selected\\"}"}}]}',
            status=200,
        )

    provider = build_llm_provider_from_settings(
        Settings(
            llm_fake_mode=False,
            llm_provider="qwen",
            llm_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            llm_api_key="secret-key",
            llm_model_fast="qwen-flash",
            llm_model_quality="qwen-plus",
            llm_timeout_seconds=45,
        ),
        urlopen=fake_urlopen,
    )

    assert isinstance(provider, OpenAICompatibleLLMProvider)
    assert opener_calls == []

    metadata = provider.metadata()
    assert metadata.provider == "qwen"
    assert metadata.transport_configured is True
    assert metadata.model_dump().get("api_key") is None


def test_app_llm_provider_selection_preserves_openai_config_errors() -> None:
    def unexpected_urlopen(request, timeout):
        raise AssertionError("missing config must fail before transport opens network")

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        build_llm_provider_from_settings(
            Settings(
                llm_fake_mode=False,
                llm_provider="qwen",
                llm_base_url="",
                llm_api_key="",
                llm_model_fast="",
                llm_model_quality="",
                llm_timeout_seconds=0,
            ),
            urlopen=unexpected_urlopen,
        )

    failure = exc_info.value.failure
    assert failure.error_code == "provider_not_configured"
    assert failure.missing_settings == [
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL_FAST",
        "LLM_MODEL_QUALITY",
        "LLM_TIMEOUT_SECONDS",
    ]


def test_openai_compatible_provider_generate_uses_local_transport_without_network() -> None:
    content = {
        "narrative": "本地 transport 返回了一段可解析文本。",
        "choices": [{"id": "choice_1", "label": "继续", "risk": "low"}],
    }
    transport = _LocalOpenAITransport(
        {
            "model": "response-envelope-model",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(content, ensure_ascii=False),
                    }
                }
            ],
            "usage": {"prompt_tokens": 21, "completion_tokens": 34},
        }
    )
    provider = _configured_openai_provider(transport=transport)
    request = _request("normal_turn_generation", max_output_tokens=333)

    response = provider.generate(request)

    assert response.provider == "qwen"
    assert response.model == "qwen-flash"
    assert response.task_type == "normal_turn_generation"
    assert response.content == content
    assert response.usage.input_tokens == 21
    assert response.usage.output_tokens == 34
    assert response.usage.estimated is False
    assert response.fallback_used is False
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["base_url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert call["api_key"] == "secret-key"
    assert call["timeout_seconds"] == 45
    assert call["payload"] == {
        "model": "qwen-flash",
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON for the fake provider test.",
            },
            {"role": "user", "content": "推进一个可测试的故事任务。"},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 333,
    }
    assert "secret-key" not in json.dumps(call["payload"], ensure_ascii=False)


def test_openai_compatible_provider_generate_uses_quality_model_for_quality_task() -> None:
    transport = _LocalOpenAITransport(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"title": "local story bible"}',
                    }
                }
            ],
        }
    )
    provider = _configured_openai_provider(transport=transport)

    response = provider.generate(_request("story_bible_generation"))

    assert response.model == "qwen-plus"
    assert response.content == {"title": "local story bible"}
    assert transport.calls[0]["payload"]["model"] == "qwen-plus"


def test_openai_compatible_provider_generate_wraps_local_transport_errors() -> None:
    provider = _configured_openai_provider(
        transport=_LocalOpenAITransport(error=RuntimeError("local transport failed"))
    )

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        provider.generate(_request("normal_turn_generation"))

    assert exc_info.value.failure.error_code == "provider_unavailable"


def test_openai_compatible_http_transport_posts_chat_completion_request() -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = {
            key.lower(): value for key, value in request.header_items()
        }
        captured["body"] = request.data
        captured["timeout"] = timeout
        return _LocalHTTPResponse(
            b'{"choices":[{"message":{"content":"{}"}}]}',
            status=200,
        )

    transport = OpenAICompatibleHTTPTransport(urlopen=fake_urlopen)
    payload = {
        "model": "qwen-flash",
        "messages": [{"role": "user", "content": "local"}],
        "response_format": {"type": "json_object"},
        "max_tokens": 128,
    }

    response_payload = transport.send_chat_completion(
        base_url="https://example.test/compatible-mode/v1/",
        api_key="secret-key",
        payload=payload,
        timeout_seconds=45,
    )

    body_text = captured["body"].decode("utf-8")
    assert captured["url"] == "https://example.test/compatible-mode/v1/chat/completions"
    assert captured["method"] == "POST"
    assert captured["headers"]["authorization"] == "Bearer secret-key"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["headers"]["accept"] == "application/json"
    assert captured["timeout"] == 45
    assert json.loads(body_text) == payload
    assert "secret-key" not in body_text
    assert response_payload == {"choices": [{"message": {"content": "{}"}}]}


def test_openai_compatible_provider_generate_can_use_http_transport_with_local_opener() -> None:
    content = {"summary": "local http transport"}

    def fake_urlopen(request, timeout):
        return _LocalHTTPResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(content),
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 7},
                }
            ).encode("utf-8"),
            status=200,
        )

    provider = _configured_openai_provider(
        transport=OpenAICompatibleHTTPTransport(urlopen=fake_urlopen)
    )

    response = provider.generate(_request("summary_generation"))

    assert response.provider == "qwen"
    assert response.model == "qwen-flash"
    assert response.content == content
    assert response.usage.input_tokens == 5
    assert response.usage.output_tokens == 7
    assert response.usage.estimated is False


def test_openai_compatible_http_transport_rejects_http_status_failure() -> None:
    transport = OpenAICompatibleHTTPTransport(
        urlopen=lambda request, timeout: _LocalHTTPResponse(
            b'{"error":"rate limited"}',
            status=429,
        )
    )

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        transport.send_chat_completion(
            base_url="https://example.test/v1",
            api_key="secret-key",
            payload={"model": "qwen-flash", "messages": []},
            timeout_seconds=45,
        )

    assert exc_info.value.failure.error_code == "provider_unavailable"
    assert "429" in exc_info.value.failure.message


@pytest.mark.parametrize("body", [b"not json", b'["not", "object"]'])
def test_openai_compatible_http_transport_rejects_malformed_json_response(
    body: bytes,
) -> None:
    transport = OpenAICompatibleHTTPTransport(
        urlopen=lambda request, timeout: _LocalHTTPResponse(body, status=200)
    )

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        transport.send_chat_completion(
            base_url="https://example.test/v1",
            api_key="secret-key",
            payload={"model": "qwen-flash", "messages": []},
            timeout_seconds=45,
        )

    assert exc_info.value.failure.error_code == "malformed_provider_response"


def test_openai_compatible_provider_builds_chat_completion_payload_without_api_key() -> None:
    provider = _configured_openai_provider()
    request = _request("normal_turn_generation", max_output_tokens=321)

    payload = provider.build_chat_completion_payload(
        request,
        model="router-selected-fast",
    )

    assert payload == {
        "model": "router-selected-fast",
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON for the fake provider test.",
            },
            {"role": "user", "content": "推进一个可测试的故事任务。"},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 321,
    }
    assert "secret-key" not in json.dumps(payload, ensure_ascii=False)


def test_deepseek_chat_completion_payload_disables_thinking_for_json_output() -> None:
    provider = OpenAICompatibleLLMProvider.from_settings(
        Settings(
            llm_fake_mode=False,
            llm_provider="deepseek",
            llm_base_url="https://api.deepseek.com",
            llm_api_key="secret-key",
            llm_model_fast="deepseek-v4-flash",
            llm_model_quality="deepseek-v4-pro",
            llm_timeout_seconds=120,
        )
    )

    payload = provider.build_chat_completion_payload(
        _request("story_bible_generation", max_output_tokens=1800)
    )

    assert payload["model"] == "deepseek-v4-pro"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["thinking"] == {"type": "disabled"}
    assert "secret-key" not in json.dumps(payload, ensure_ascii=False)


def test_openai_compatible_provider_parses_chat_completion_response_envelope() -> None:
    provider = _configured_openai_provider()
    request = _request("normal_turn_generation")
    content = {
        "narrative": "离线假响应推进了一步。",
        "choices": [
            {"id": "choice_1", "label": "继续观察", "risk": "low"},
        ],
    }
    raw_text = json.dumps(content, ensure_ascii=False)

    response = provider.parse_chat_completion_response(
        {
            "id": "chatcmpl-local",
            "model": "qwen-flash",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": raw_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 34,
                "total_tokens": 46,
            },
        },
        request=request,
        latency_ms=123,
    )

    assert response.provider == "qwen"
    assert response.model == "qwen-flash"
    assert response.task_type == "normal_turn_generation"
    assert response.content == content
    assert response.raw_text == raw_text
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 34
    assert response.usage.estimated is False
    assert response.latency_ms == 123
    assert response.fallback_used is False


def test_openai_compatible_provider_estimates_usage_when_response_usage_missing() -> None:
    provider = _configured_openai_provider()
    request = _request("summary_generation")

    response = provider.parse_chat_completion_response(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"summary": "local"}',
                    }
                }
            ],
        },
        request=request,
        model="selected-summary-model",
    )

    assert response.model == "selected-summary-model"
    assert response.content == {"summary": "local"}
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0
    assert response.usage.estimated is True


@pytest.mark.parametrize(
    "response_payload",
    [
        {"choices": []},
        {"choices": [{"message": {"content": {"not": "a string"}}}]},
        {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": -1, "completion_tokens": 2},
        },
    ],
)
def test_openai_compatible_provider_rejects_malformed_response_envelopes(
    response_payload: dict,
) -> None:
    provider = _configured_openai_provider()

    with pytest.raises(OpenAICompatibleProviderError) as exc_info:
        provider.parse_chat_completion_response(
            response_payload,
            request=_request("normal_turn_generation"),
        )

    assert exc_info.value.failure.error_code == "malformed_provider_response"


def test_in_memory_llm_router_selects_first_available_fast_model() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(model="fake-fast-backup", tier="fast", priority=20),
            _model_config(model="fake-fast-primary", tier="fast", priority=10),
            _model_config(model="fake-quality-primary", tier="quality", priority=10),
        ]
    )

    selection = router.select_model(
        task_type="normal_turn_generation",
        estimated_input_tokens=100,
        max_output_tokens=200,
    )

    assert selection.provider == "fake"
    assert selection.model == "fake-fast-primary"
    assert selection.tier == "fast"
    assert selection.max_output_tokens == 200
    assert selection.estimated_total_tokens == 300
    assert selection.fallback_used is False
    assert selection.fallback_chain == ["fake/fake-fast-primary"]
    assert selection.skipped_models == []

    quality_selection = router.select_model(task_type="story_bible_generation")
    assert quality_selection.model == "fake-quality-primary"
    assert quality_selection.tier == "quality"


def test_in_memory_llm_router_skips_exhausted_primary_fast_model() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                daily_tokens_used=1_000,
                daily_token_budget=1_000,
            ),
            _model_config(model="fake-fast-fallback", tier="fast", priority=20),
        ]
    )

    selection = router.select_model(
        task_type="normal_turn_generation",
        estimated_input_tokens=10,
        max_output_tokens=100,
    )

    assert selection.model == "fake-fast-fallback"
    assert selection.fallback_used is True
    assert selection.fallback_chain == [
        "fake/fake-fast-primary",
        "fake/fake-fast-fallback",
    ]
    assert len(selection.skipped_models) == 1
    assert selection.skipped_models[0].model == "fake-fast-primary"
    assert selection.skipped_models[0].reason == "daily_budget_exhausted"


def test_in_memory_llm_router_skips_monthly_exhausted_model() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                monthly_tokens_used=1_000,
                monthly_token_budget=1_000,
            ),
            _model_config(model="fake-fast-fallback", tier="fast", priority=20),
        ]
    )

    selection = router.select_model(
        task_type="summary_generation",
        estimated_input_tokens=10,
        max_output_tokens=100,
    )

    assert selection.model == "fake-fast-fallback"
    assert selection.fallback_used is True
    assert selection.skipped_models[0].reason == "monthly_budget_exhausted"


def test_in_memory_llm_router_skips_disabled_and_unhealthy_models() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-disabled",
                tier="fast",
                priority=10,
                enabled=False,
            ),
            _model_config(
                model="fake-fast-unhealthy",
                tier="fast",
                priority=20,
                healthy=False,
            ),
            _model_config(model="fake-fast-fallback", tier="fast", priority=30),
        ]
    )

    selection = router.select_model(task_type="safety_classification")

    assert selection.model == "fake-fast-fallback"
    assert selection.fallback_used is True
    assert [skipped.reason for skipped in selection.skipped_models] == [
        "disabled",
        "unhealthy",
    ]


def test_in_memory_llm_router_selection_error_preserves_skipped_models() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-disabled",
                tier="fast",
                priority=10,
                enabled=False,
            ),
            _model_config(
                model="fake-fast-unhealthy",
                tier="fast",
                priority=20,
                healthy=False,
            ),
            _model_config(
                model="fake-fast-exhausted",
                tier="fast",
                priority=30,
                daily_tokens_used=1_000,
                daily_token_budget=1_000,
            ),
        ]
    )

    with pytest.raises(LLMRouterSelectionError) as exc_info:
        router.select_model(
            task_type="normal_turn_generation",
            estimated_input_tokens=10,
            max_output_tokens=100,
        )

    failure = exc_info.value.failure

    assert failure.error_code == "no_available_model"
    assert failure.task_type == "normal_turn_generation"
    assert failure.tier == "fast"
    assert failure.fallback_chain == [
        "fake/fake-fast-disabled",
        "fake/fake-fast-unhealthy",
        "fake/fake-fast-exhausted",
    ]
    assert [skipped.model for skipped in failure.skipped_models] == [
        "fake-fast-disabled",
        "fake-fast-unhealthy",
        "fake-fast-exhausted",
    ]
    assert [skipped.reason for skipped in failure.skipped_models] == [
        "disabled",
        "unhealthy",
        "daily_budget_exhausted",
    ]


def test_in_memory_llm_router_records_provider_usage_from_ledger_entries() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(model="fake-fast-primary", tier="fast", priority=10),
        ]
    )

    updates = router.record_usage_from_ledger_entries(
        [
            _ledger_entry(
                provider="fake",
                model="fake-fast-primary",
                input_tokens=40,
                output_tokens=60,
            ),
            _ledger_entry(
                provider="fake",
                model="fake-fast-primary",
                input_tokens=10,
                output_tokens=20,
                status="parse_failed",
            ),
            _ledger_entry(
                provider="local-fallback",
                model="deterministic-normal-turn-v1",
                input_tokens=0,
                output_tokens=80,
                attempt_type="fallback",
                status="fallback",
                fallback_used=True,
            ),
        ]
    )

    configs = router.list_model_configs()
    assert len(updates) == 2
    assert updates[0].provider == "fake"
    assert updates[0].model == "fake-fast-primary"
    assert updates[0].tokens_added == 100
    assert updates[1].tokens_added == 30
    assert configs[0].daily_tokens_used == 130
    assert configs[0].monthly_tokens_used == 130


def test_in_memory_llm_router_exhausts_budget_after_recorded_usage() -> None:
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                daily_token_budget=300,
            ),
            _model_config(model="fake-fast-fallback", tier="fast", priority=20),
        ]
    )

    first_selection = router.select_model(
        task_type="normal_turn_generation",
        estimated_input_tokens=100,
        max_output_tokens=100,
    )
    assert first_selection.model == "fake-fast-primary"

    update = router.record_usage_from_ledger_entry(
        _ledger_entry(
            provider="fake",
            model="fake-fast-primary",
            input_tokens=75,
            output_tokens=75,
        )
    )
    assert update is not None
    assert update.daily_tokens_used == 150

    second_selection = router.select_model(
        task_type="normal_turn_generation",
        estimated_input_tokens=100,
        max_output_tokens=100,
    )

    assert second_selection.model == "fake-fast-fallback"
    assert second_selection.fallback_used is True
    assert second_selection.skipped_models[0].model == "fake-fast-primary"
    assert second_selection.skipped_models[0].reason == "daily_budget_exhausted"


def test_fake_provider_returns_strict_turn_json_without_external_api() -> None:
    provider = FakeLLMProvider()
    response = provider.generate(
        _request(
            "normal_turn_generation",
            metadata={
                "protagonist_name": "林澈",
                "player_action": "我先观察执事袖口的木牌。",
            },
        )
    )

    assert response.provider == "fake"
    assert response.model == "fake-fast"
    assert response.task_type == "normal_turn_generation"
    assert response.fallback_used is False
    assert response.usage.input_tokens > 0
    assert response.usage.output_tokens > 0
    assert response.usage.estimated is True
    assert response.raw_text.startswith("{")
    assert set(response.content.keys()) == {
        "narrative",
        "choices",
        "state_patch",
        "memory_update",
        "safety",
    }
    assert "林澈" in response.content["narrative"]
    assert len(response.content["choices"]) == 3
    assert response.content["choices"][0] == {
        "id": "choice_1",
        "label": "稳住现场，补全关键细节",
        "risk": "low",
    }
    assert response.content["state_patch"] == {
        "active_goal": None,
        "short_summary_append": "Fake provider 推进了当前场景。",
        "relationships": {
            "npc_001": {
                "affinity_delta": 1,
                "trust_delta": 0,
                "status": None,
            }
        },
        "inventory_add": [],
        "inventory_remove_ids": [],
        "stats_delta": {
            "danger": 1,
            "reputation": 0,
            "power": 0,
            "health": 0,
        },
        "flags_set": {"fake_provider_turn": True},
        "chapter_progress_delta": 1,
    }
    assert response.content["safety"] == {
        "safe": True,
        "reason": "fake provider deterministic safe output",
    }


def test_fake_provider_uses_quality_model_for_story_bible_generation() -> None:
    provider = FakeLLMProvider()
    response = provider.generate(
        _request(
            "story_bible_generation",
            metadata={
                "protagonist_name": "林澈",
                "template_name": "修仙逆袭",
            },
        )
    )

    assert response.provider == "fake"
    assert response.model == "fake-quality"
    assert response.content["title"] == "修仙逆袭测试开局"
    assert "林澈" in response.content["opening_narrative"]
    assert response.content["story_bible"]["world_rules"]
    assert response.content["plot_plan"]["total_chapters"] == 8
    assert len(response.content["choices"]) == 3


def test_fake_provider_supports_all_phase_3_task_types() -> None:
    provider = FakeLLMProvider()

    for task_type in LLM_TASK_TYPES:
        response = provider.generate(_request(task_type))

        assert response.provider == "fake"
        assert response.task_type == task_type
        assert response.content
        assert response.raw_text.startswith("{")


def test_parse_llm_raw_json_validates_normal_turn_output() -> None:
    provider = FakeLLMProvider()
    response = provider.generate(_request("normal_turn_generation"))

    result = parse_llm_raw_json(
        raw_text=response.raw_text,
        task_type=response.task_type,
    )

    assert result.ok is True
    assert result.error_code is None
    assert result.error_message is None
    assert result.content is not None
    assert result.content["narrative"] == response.content["narrative"]
    assert len(result.content["choices"]) == 3
    assert result.content["state_patch"]["chapter_progress_delta"] == 1
    assert result.content["memory_update"]["new_facts"]
    assert result.content["safety"]["safe"] is True


def test_parse_llm_raw_json_returns_error_for_malformed_json() -> None:
    result = parse_llm_raw_json(
        raw_text='{"narrative": "broken"',
        task_type="normal_turn_generation",
    )

    assert result.ok is False
    assert result.content is None
    assert result.error_code == "invalid_json"
    assert result.error_message


def test_parse_llm_raw_json_returns_error_for_non_object_json() -> None:
    result = parse_llm_raw_json(
        raw_text='["not", "an", "object"]',
        task_type="normal_turn_generation",
    )

    assert result.ok is False
    assert result.content is None
    assert result.error_code == "invalid_json"
    assert result.error_message == "Provider JSON output must be an object."


def test_parse_llm_raw_json_rejects_normal_turn_missing_required_field() -> None:
    result = parse_llm_raw_json(
        raw_text='{"narrative": "缺少 choices 和 state_patch"}',
        task_type="normal_turn_generation",
    )

    assert result.ok is False
    assert result.content is None
    assert result.error_code == "invalid_schema"
    assert result.error_message


def test_parse_llm_raw_json_rejects_normal_turn_wrong_choice_count() -> None:
    provider = FakeLLMProvider()
    response = provider.generate(_request("normal_turn_generation"))
    malformed_content = dict(response.content)
    malformed_content["choices"] = malformed_content["choices"][:2]

    result = parse_llm_raw_json(
        raw_text=json.dumps(malformed_content, ensure_ascii=False),
        task_type="normal_turn_generation",
    )

    assert result.ok is False
    assert result.content is None
    assert result.error_code == "invalid_schema"
    assert result.error_message


def test_generate_normal_turn_with_repair_returns_first_valid_parse() -> None:
    provider = FakeLLMProvider()
    request = _request("normal_turn_generation")

    result = generate_normal_turn_with_repair(provider, request)

    assert result.ok is True
    assert result.repair_used is False
    assert result.fallback_used is False
    assert result.requested_task_type == "normal_turn_generation"
    assert result.response.task_type == "normal_turn_generation"
    assert result.repair_response is None
    assert result.repair_parse_result is None
    assert result.parse_result.ok is True
    assert result.initial_parse_result.ok is True
    assert result.content is not None
    assert len(result.content["choices"]) == 3


def test_openai_compatible_provider_with_http_transport_succeeds_through_gateway() -> None:
    captured_payloads: list[dict[str, Any]] = []
    content = _valid_normal_turn_content(
        narrative="mocked HTTP transport completed the normal turn."
    )

    def fake_urlopen(request, timeout):
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return _LocalHTTPResponse(
            json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(content, ensure_ascii=False),
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 31, "completion_tokens": 47},
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            status=200,
        )

    provider = _configured_openai_provider(
        transport=OpenAICompatibleHTTPTransport(urlopen=fake_urlopen)
    )
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(
        provider,
        _request("normal_turn_generation", max_output_tokens=333),
        ledger=ledger,
    )

    assert result.ok is True
    assert result.repair_used is False
    assert result.fallback_used is False
    assert result.response is not None
    assert result.response.provider == "qwen"
    assert result.response.model == "qwen-flash"
    assert result.response.usage.input_tokens == 31
    assert result.response.usage.output_tokens == 47
    assert result.response.usage.estimated is False
    assert result.parse_result is not None
    assert result.parse_result.ok is True
    assert result.content == result.parse_result.content
    assert result.content is not None
    assert result.content["narrative"] == "mocked HTTP transport completed the normal turn."

    entries = ledger.list_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.attempt_type == "initial"
    assert entry.status == "success"
    assert entry.provider == "qwen"
    assert entry.model == "qwen-flash"
    assert entry.task_type == "normal_turn_generation"
    assert entry.input_tokens == 31
    assert entry.output_tokens == 47
    assert entry.total_tokens == 78
    assert entry.token_usage_estimated is False
    assert entry.fallback_used is False
    assert entry.error_code is None
    assert entry.error_message is None

    assert len(captured_payloads) == 1
    assert captured_payloads[0]["model"] == "qwen-flash"
    assert captured_payloads[0]["max_tokens"] == 333
    assert "secret-key" not in json.dumps(captured_payloads[0], ensure_ascii=False)


def test_openai_compatible_provider_with_http_transport_falls_back_after_bad_output() -> None:
    response_bodies = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"narrative": "broken"',
                    }
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 13},
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"narrative": "still broken"',
                    }
                }
            ],
            "usage": {"prompt_tokens": 17, "completion_tokens": 19},
        },
    ]
    captured_payloads: list[dict[str, Any]] = []

    def fake_urlopen(request, timeout):
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return _LocalHTTPResponse(
            json.dumps(response_bodies.pop(0)).encode("utf-8"),
            status=200,
        )

    provider = _configured_openai_provider(
        transport=OpenAICompatibleHTTPTransport(urlopen=fake_urlopen)
    )
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(
        provider,
        _request(
            "normal_turn_generation",
            metadata={
                "protagonist_name": "林澈",
                "player_action": "我先确认门后的脚步声。",
            },
        ),
        ledger=ledger,
    )

    assert result.ok is True
    assert result.repair_used is True
    assert result.fallback_used is True
    assert result.fallback_reason == "invalid_json"
    assert result.initial_parse_result is not None
    assert result.initial_parse_result.error_code == "invalid_json"
    assert result.repair_parse_result is not None
    assert result.repair_parse_result.error_code == "invalid_json"
    assert result.response is not None
    assert result.response.provider == "local-fallback"
    assert result.response.model == "deterministic-normal-turn-v1"
    assert result.content is not None
    assert "林澈" in result.content["narrative"]
    assert "我先确认门后的脚步声。" in result.content["narrative"]

    entries = ledger.list_entries()
    assert [entry.attempt_type for entry in entries] == [
        "initial",
        "repair",
        "fallback",
    ]
    assert [entry.status for entry in entries] == [
        "parse_failed",
        "parse_failed",
        "fallback",
    ]
    assert entries[0].provider == "qwen"
    assert entries[0].model == "qwen-flash"
    assert entries[0].input_tokens == 11
    assert entries[0].output_tokens == 13
    assert entries[0].error_code == "invalid_json"
    assert entries[1].provider == "qwen"
    assert entries[1].model == "qwen-flash"
    assert entries[1].task_type == "json_repair"
    assert entries[1].input_tokens == 17
    assert entries[1].output_tokens == 19
    assert entries[1].error_code == "invalid_json"
    assert entries[2].provider == "local-fallback"
    assert entries[2].status == "fallback"
    assert len(captured_payloads) == 2
    assert captured_payloads[0]["model"] == "qwen-flash"
    assert captured_payloads[1]["model"] == "qwen-flash"
    assert captured_payloads[1]["messages"][1]["content"] == '{"narrative": "broken"'


def test_generate_normal_turn_with_router_uses_primary_model_metadata() -> None:
    provider = FakeLLMProvider()
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(model="fake-fast-primary", tier="fast", priority=10),
            _model_config(model="fake-fast-fallback", tier="fast", priority=20),
        ]
    )
    request = _request("normal_turn_generation")
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=ledger,
        router=router,
    )

    assert result.ok is True
    assert result.repair_used is False
    assert result.fallback_used is False
    assert result.router_selection is not None
    assert result.router_selection.model == "fake-fast-primary"
    assert result.router_selection.fallback_used is False
    assert result.initial_response.provider == "fake"
    assert result.initial_response.model == "fake-fast-primary"
    assert result.initial_response.fallback_used is False
    assert result.response.model == "fake-fast-primary"

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-fast-primary"
    assert entries[0].fallback_used is False


def test_generate_normal_turn_with_router_records_exhausted_primary_fallback_metadata() -> None:
    provider = FakeLLMProvider()
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                daily_tokens_used=1_000,
                daily_token_budget=1_000,
            ),
            _model_config(model="fake-fast-fallback", tier="fast", priority=20),
        ]
    )
    request = _request("normal_turn_generation")
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=ledger,
        router=router,
    )

    assert result.ok is True
    assert result.repair_used is False
    assert result.fallback_used is False
    assert result.router_selection is not None
    assert result.router_selection.model == "fake-fast-fallback"
    assert result.router_selection.fallback_used is True
    assert result.router_selection.fallback_chain == [
        "fake/fake-fast-primary",
        "fake/fake-fast-fallback",
    ]
    assert result.router_selection.skipped_models[0].model == "fake-fast-primary"
    assert result.router_selection.skipped_models[0].reason == "daily_budget_exhausted"
    assert result.initial_response.model == "fake-fast-fallback"
    assert result.initial_response.fallback_used is True
    assert result.response.model == "fake-fast-fallback"
    assert result.response.fallback_used is True

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].model == "fake-fast-fallback"
    assert entries[0].fallback_used is True


def test_generate_normal_turn_with_router_increments_usage_from_initial_entry() -> None:
    provider = FakeLLMProvider()
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(model="fake-fast-primary", tier="fast", priority=10),
        ]
    )
    request = _request("normal_turn_generation")
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=ledger,
        router=router,
    )

    entries = ledger.list_entries()
    configs_by_model = {config.model: config for config in router.list_model_configs()}

    assert result.ok is True
    assert result.router_usage_update is not None
    assert result.router_usage_update.model == "fake-fast-primary"
    assert result.router_usage_update.tokens_added == entries[0].total_tokens
    assert configs_by_model["fake-fast-primary"].daily_tokens_used == entries[0].total_tokens
    assert (
        configs_by_model["fake-fast-primary"].monthly_tokens_used
        == entries[0].total_tokens
    )


def test_generate_normal_turn_with_router_usage_can_exhaust_next_call() -> None:
    provider = FakeLLMProvider()
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                daily_token_budget=50,
            ),
            _model_config(model="fake-fast-fallback", tier="fast", priority=20),
        ]
    )
    request = _request("normal_turn_generation", max_output_tokens=1)

    first_result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=LLMCallLedger(),
        router=router,
    )
    second_result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=LLMCallLedger(),
        router=router,
    )

    assert first_result.router_selection is not None
    assert first_result.router_selection.model == "fake-fast-primary"
    assert first_result.router_usage_update is not None
    assert first_result.router_usage_update.daily_tokens_used > 0
    assert second_result.router_selection is not None
    assert second_result.router_selection.model == "fake-fast-fallback"
    assert second_result.router_selection.fallback_used is True
    assert second_result.router_usage_update is not None
    assert second_result.router_usage_update.model == "fake-fast-fallback"
    assert second_result.router_usage_update.tokens_added > 0
    assert second_result.router_selection.skipped_models[0].model == "fake-fast-primary"
    assert (
        second_result.router_selection.skipped_models[0].reason
        == "daily_budget_exhausted"
    )


def test_generate_normal_turn_with_router_does_not_count_local_fallback_usage() -> None:
    provider = AlwaysBrokenProvider()
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                daily_token_budget=50,
            ),
        ]
    )
    request = _request("normal_turn_generation", max_output_tokens=1)

    result = generate_normal_turn_with_repair(
        provider,
        request,
        ledger=LLMCallLedger(),
        router=router,
    )

    configs_by_model = {config.model: config for config in router.list_model_configs()}

    assert result.ok is True
    assert result.fallback_used is True
    assert result.router_usage_update is not None
    assert result.router_usage_update.tokens_added == 2
    assert configs_by_model["fake-fast-primary"].daily_tokens_used == 2
    assert configs_by_model["fake-fast-primary"].monthly_tokens_used == 2


def test_generate_normal_turn_with_router_returns_typed_failure_when_fast_models_exhausted() -> None:
    provider = AlwaysBrokenProvider()
    router = InMemoryLLMRouter(
        model_configs=[
            _model_config(
                model="fake-fast-primary",
                tier="fast",
                priority=10,
                daily_tokens_used=1_000,
                daily_token_budget=1_000,
            ),
            _model_config(
                model="fake-fast-fallback",
                tier="fast",
                priority=20,
                monthly_tokens_used=10_000,
                monthly_token_budget=10_000,
            ),
        ]
    )
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(
        provider,
        _request("normal_turn_generation", max_output_tokens=1),
        ledger=ledger,
        router=router,
    )

    assert result.ok is False
    assert result.error_code == "router_selection_failed"
    assert result.error_message == "No available model for fast tier."
    assert result.fallback_reason == "no_available_model"
    assert result.response is None
    assert result.parse_result is None
    assert result.initial_response is None
    assert result.initial_parse_result is None
    assert result.router_selection is None
    assert result.router_usage_update is None
    assert result.router_selection_failure is not None
    assert result.router_selection_failure.tier == "fast"
    assert result.router_selection_failure.fallback_chain == [
        "fake/fake-fast-primary",
        "fake/fake-fast-fallback",
    ]
    assert [skipped.reason for skipped in result.router_selection_failure.skipped_models] == [
        "daily_budget_exhausted",
        "monthly_budget_exhausted",
    ]
    assert provider.calls == []
    assert ledger.list_entries() == []


def test_generate_normal_turn_with_user_quota_failure_skips_provider_and_ledger() -> None:
    provider = AlwaysBrokenProvider()
    ledger = LLMCallLedger()
    quota_policy = InMemoryLLMQuotaPolicy(
        user_quota=LLMQuotaState(
            subject="user",
            subject_id="user_001",
            monthly_token_budget=20,
            monthly_tokens_used=20,
        )
    )

    result = generate_normal_turn_with_repair(
        provider,
        _request("normal_turn_generation", max_output_tokens=1),
        ledger=ledger,
        quota_policy=quota_policy,
    )

    assert result.ok is False
    assert result.error_code == "quota_exceeded"
    assert result.error_message == "User token budget exceeded."
    assert result.fallback_reason == "user_token_budget_exhausted"
    assert result.quota_failure is not None
    assert result.quota_failure.subject == "user"
    assert result.quota_failure.subject_id == "user_001"
    assert result.quota_failure.remaining_tokens == 0
    assert result.quota_failure.requested_tokens > 0
    assert result.response is None
    assert result.parse_result is None
    assert result.initial_response is None
    assert result.initial_parse_result is None
    assert result.router_selection is None
    assert result.router_usage_update is None
    assert provider.calls == []
    assert ledger.list_entries() == []


def test_generate_normal_turn_with_story_quota_failure_skips_provider_and_ledger() -> None:
    provider = AlwaysBrokenProvider()
    ledger = LLMCallLedger()
    quota_policy = InMemoryLLMQuotaPolicy(
        user_quota=LLMQuotaState(
            subject="user",
            subject_id="user_001",
            monthly_token_budget=10_000,
            monthly_tokens_used=0,
        ),
        story_quota=LLMQuotaState(
            subject="story",
            subject_id="story_001",
            monthly_token_budget=30,
            monthly_tokens_used=30,
        ),
    )

    result = generate_normal_turn_with_repair(
        provider,
        _request("normal_turn_generation", max_output_tokens=1),
        ledger=ledger,
        quota_policy=quota_policy,
    )

    assert result.ok is False
    assert result.error_code == "quota_exceeded"
    assert result.error_message == "Story token budget exceeded."
    assert result.fallback_reason == "story_token_budget_exhausted"
    assert result.quota_failure is not None
    assert result.quota_failure.subject == "story"
    assert result.quota_failure.subject_id == "story_001"
    assert result.quota_failure.remaining_tokens == 0
    assert result.quota_failure.requested_tokens > 0
    assert result.response is None
    assert result.parse_result is None
    assert result.initial_response is None
    assert result.initial_parse_result is None
    assert provider.calls == []
    assert ledger.list_entries() == []


def test_generate_normal_turn_with_quota_policy_increments_user_and_story_usage() -> None:
    provider = FakeLLMProvider()
    ledger = LLMCallLedger()
    user_quota = LLMQuotaState(
        subject="user",
        subject_id="user_001",
        monthly_token_budget=10_000,
        monthly_tokens_used=100,
    )
    story_quota = LLMQuotaState(
        subject="story",
        subject_id="story_001",
        monthly_token_budget=5_000,
        monthly_tokens_used=50,
    )
    quota_policy = InMemoryLLMQuotaPolicy(
        user_quota=user_quota,
        story_quota=story_quota,
    )

    result = generate_normal_turn_with_repair(
        provider,
        _request("normal_turn_generation", max_output_tokens=1),
        ledger=ledger,
        quota_policy=quota_policy,
    )

    initial_entry = ledger.list_entries()[0]
    updates_by_subject = {
        update.subject: update for update in result.quota_usage_updates
    }

    assert result.ok is True
    assert len(result.quota_usage_updates) == 2
    assert updates_by_subject["user"].subject_id == "user_001"
    assert updates_by_subject["user"].tokens_added == initial_entry.total_tokens
    assert updates_by_subject["user"].monthly_tokens_used == (
        100 + initial_entry.total_tokens
    )
    assert updates_by_subject["story"].subject_id == "story_001"
    assert updates_by_subject["story"].tokens_added == initial_entry.total_tokens
    assert updates_by_subject["story"].monthly_tokens_used == (
        50 + initial_entry.total_tokens
    )
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == (
        100 + initial_entry.total_tokens
    )
    assert quota_policy.story_quota.monthly_tokens_used == (
        50 + initial_entry.total_tokens
    )


def test_generate_normal_turn_with_quota_policy_does_not_count_local_fallback_usage() -> None:
    provider = AlwaysBrokenProvider()
    ledger = LLMCallLedger()
    quota_policy = InMemoryLLMQuotaPolicy(
        user_quota=LLMQuotaState(
            subject="user",
            subject_id="user_001",
            monthly_token_budget=10_000,
            monthly_tokens_used=0,
        ),
        story_quota=LLMQuotaState(
            subject="story",
            subject_id="story_001",
            monthly_token_budget=10_000,
            monthly_tokens_used=0,
        ),
    )

    result = generate_normal_turn_with_repair(
        provider,
        _request("normal_turn_generation", max_output_tokens=1),
        ledger=ledger,
        quota_policy=quota_policy,
    )

    entries = ledger.list_entries()
    initial_entry = entries[0]
    fallback_entry = entries[-1]

    assert result.ok is True
    assert result.fallback_used is True
    assert fallback_entry.attempt_type == "fallback"
    assert fallback_entry.total_tokens > initial_entry.total_tokens
    assert len(result.quota_usage_updates) == 2
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == initial_entry.total_tokens
    assert quota_policy.story_quota.monthly_tokens_used == initial_entry.total_tokens


def test_llm_call_ledger_records_successful_normal_turn_attempt() -> None:
    provider = FakeLLMProvider()
    request = _request("normal_turn_generation")
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(provider, request, ledger=ledger)

    assert result.ok is True
    entries = ledger.list_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.attempt_type == "initial"
    assert entry.status == "success"
    assert entry.provider == "fake"
    assert entry.model == "fake-fast"
    assert entry.task_type == "normal_turn_generation"
    assert entry.input_tokens > 0
    assert entry.output_tokens > 0
    assert entry.total_tokens == entry.input_tokens + entry.output_tokens
    assert entry.token_usage_estimated is True
    assert entry.latency_ms >= 0
    assert entry.fallback_used is False
    assert entry.error_code is None
    assert entry.error_message is None


def test_generate_normal_turn_with_repair_retries_once_after_invalid_json() -> None:
    provider = BrokenFirstThenFakeRepairProvider()
    request = _request("normal_turn_generation")

    result = generate_normal_turn_with_repair(provider, request)

    assert result.ok is True
    assert result.repair_used is True
    assert result.fallback_used is False
    assert [call.task_type for call in provider.calls] == [
        "normal_turn_generation",
        "json_repair",
    ]
    assert provider.calls[1].metadata["repair_of_task_type"] == "normal_turn_generation"
    assert provider.calls[1].metadata["parse_error_code"] == "invalid_json"
    assert result.initial_parse_result.ok is False
    assert result.initial_parse_result.error_code == "invalid_json"
    assert result.response.task_type == "json_repair"
    assert result.repair_response is not None
    assert result.repair_response.task_type == "json_repair"
    assert result.repair_parse_result is not None
    assert result.repair_parse_result.ok is True
    assert result.parse_result.ok is True
    assert result.content is not None
    assert result.content["safety"]["safe"] is True


def test_llm_call_ledger_records_initial_failure_and_repair_success() -> None:
    provider = BrokenFirstThenFakeRepairProvider()
    request = _request("normal_turn_generation")
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(provider, request, ledger=ledger)

    assert result.ok is True
    entries = ledger.list_entries()
    assert [entry.attempt_type for entry in entries] == ["initial", "repair"]

    initial_entry = entries[0]
    assert initial_entry.status == "parse_failed"
    assert initial_entry.provider == "scripted"
    assert initial_entry.model == "broken-model"
    assert initial_entry.task_type == "normal_turn_generation"
    assert initial_entry.input_tokens == 1
    assert initial_entry.output_tokens == 1
    assert initial_entry.total_tokens == 2
    assert initial_entry.fallback_used is False
    assert initial_entry.error_code == "invalid_json"
    assert initial_entry.error_message

    repair_entry = entries[1]
    assert repair_entry.status == "success"
    assert repair_entry.provider == "scripted"
    assert repair_entry.model == "fake-fast"
    assert repair_entry.task_type == "json_repair"
    assert repair_entry.input_tokens > 0
    assert repair_entry.output_tokens > 0
    assert repair_entry.total_tokens == repair_entry.input_tokens + repair_entry.output_tokens
    assert repair_entry.fallback_used is False
    assert repair_entry.error_code is None


def test_generate_normal_turn_with_repair_returns_fallback_after_failed_repair() -> None:
    provider = AlwaysBrokenProvider()
    request = _request(
        "normal_turn_generation",
        metadata={
            "protagonist_name": "林澈",
            "player_action": "我先确认门后的脚步声。",
        },
    )

    result = generate_normal_turn_with_repair(provider, request)

    assert result.ok is True
    assert result.repair_used is True
    assert result.fallback_used is True
    assert result.fallback_reason == "invalid_json"
    assert [call.task_type for call in provider.calls] == [
        "normal_turn_generation",
        "json_repair",
    ]
    assert result.content is not None
    assert "林澈" in result.content["narrative"]
    assert "我先确认门后的脚步声。" in result.content["narrative"]
    assert len(result.content["choices"]) == 3
    assert result.content["state_patch"]["flags_set"] == {"llm_fallback_turn": True}
    assert result.content["safety"] == {
        "safe": True,
        "reason": "deterministic fallback after provider JSON repair failure",
    }
    assert result.initial_parse_result.error_code == "invalid_json"
    assert result.repair_parse_result is not None
    assert result.repair_parse_result.error_code == "invalid_json"
    assert result.parse_result.ok is True
    assert result.response.provider == "local-fallback"
    assert result.response.model == "deterministic-normal-turn-v1"
    assert result.response.task_type == "normal_turn_generation"
    assert result.response.fallback_used is True
    assert result.repair_response is not None
    assert result.repair_response.task_type == "json_repair"


def test_llm_call_ledger_records_repair_failure_and_local_fallback() -> None:
    provider = AlwaysBrokenProvider()
    request = _request("normal_turn_generation")
    ledger = LLMCallLedger()

    result = generate_normal_turn_with_repair(provider, request, ledger=ledger)

    assert result.ok is True
    assert result.fallback_used is True
    entries = ledger.list_entries()
    assert [entry.attempt_type for entry in entries] == [
        "initial",
        "repair",
        "fallback",
    ]
    assert [entry.status for entry in entries] == [
        "parse_failed",
        "parse_failed",
        "fallback",
    ]
    assert entries[0].error_code == "invalid_json"
    assert entries[1].error_code == "invalid_json"

    fallback_entry = entries[2]
    assert fallback_entry.provider == "local-fallback"
    assert fallback_entry.model == "deterministic-normal-turn-v1"
    assert fallback_entry.task_type == "normal_turn_generation"
    assert fallback_entry.input_tokens == 0
    assert fallback_entry.output_tokens > 0
    assert fallback_entry.total_tokens == fallback_entry.output_tokens
    assert fallback_entry.token_usage_estimated is True
    assert fallback_entry.latency_ms == 0
    assert fallback_entry.fallback_used is True
    assert fallback_entry.error_code == "invalid_json"
    assert fallback_entry.error_message


class BrokenFirstThenFakeRepairProvider:
    name = "scripted"

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []
        self.fake_provider = FakeLLMProvider()

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        if len(self.calls) == 1:
            return _broken_response(request, provider=self.name)

        repair_response = self.fake_provider.generate(request)
        return repair_response.model_copy(update={"provider": self.name})


class AlwaysBrokenProvider:
    name = "always-broken"

    def __init__(self) -> None:
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return _broken_response(request, provider=self.name)


def _broken_response(request: LLMRequest, *, provider: str) -> LLMResponse:
    return LLMResponse(
        provider=provider,
        model="broken-model",
        task_type=request.task_type,
        content={},
        usage=LLMUsage(input_tokens=1, output_tokens=1, estimated=True),
        latency_ms=0,
        raw_text='{"narrative": "broken"',
        fallback_used=False,
    )


def _model_config(
    *,
    model: str,
    tier: str,
    priority: int,
    daily_token_budget: int = 1_000,
    monthly_token_budget: int = 10_000,
    daily_tokens_used: int = 0,
    monthly_tokens_used: int = 0,
    enabled: bool = True,
    healthy: bool = True,
) -> LLMModelConfig:
    return LLMModelConfig(
        provider="fake",
        model=model,
        tier=tier,
        priority=priority,
        enabled=enabled,
        healthy=healthy,
        daily_token_budget=daily_token_budget,
        monthly_token_budget=monthly_token_budget,
        daily_tokens_used=daily_tokens_used,
        monthly_tokens_used=monthly_tokens_used,
        max_output_tokens=900,
    )


def _ledger_entry(
    *,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    attempt_type: str = "initial",
    status: str = "success",
    fallback_used: bool = False,
) -> LLMCallLedgerEntry:
    return LLMCallLedgerEntry(
        task_type="normal_turn_generation",
        attempt_type=attempt_type,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        token_usage_estimated=True,
        status=status,
        latency_ms=0,
        fallback_used=fallback_used,
    )
