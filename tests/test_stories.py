import json
from typing import Optional
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.routes.stories import (
    get_story_llm_call_ledger,
    get_story_llm_quota_policy,
    get_story_llm_router,
    get_story_settings,
    get_story_provider_factory,
)
from app.core.config import Settings
from app.llm.fake_provider import FakeLLMProvider
from app.llm.ledger import LLMCallLedger
from app.llm.openai_compatible_provider import (
    OpenAICompatibleProviderError,
    OpenAICompatibleProviderFailure,
)
from app.llm.provider import LLMRequest, LLMResponse, LLMUsage
from app.llm.quota import InMemoryLLMQuotaPolicy, LLMQuotaState
from app.llm.router import InMemoryLLMRouter, LLMModelConfig
from app.main import create_app
from app.schemas.stories import CreateStoryRequest, PlayTurnRequest
from app.services.story_service import (
    clear_stories,
    create_story_from_settings,
    create_story_with_llm_provider,
    get_story,
    list_stories_for_device,
    play_choice_turn_with_llm_provider,
    play_free_text_turn_with_llm_provider,
    play_turn_from_settings,
)


def _create_story_payload(
    template_id: str = "xianxia_rise",
    device_id: Optional[str] = None,
) -> dict:
    return {
        "device_id": device_id or str(uuid4()),
        "template_id": template_id,
        "locale": "zh-Hans",
        "protagonist": {
            "name": "林澈",
            "pronouns": "他",
            "age_band": "adult",
            "personality": ["冷静", "不服输"],
            "starting_role": "被宗门轻视的外门弟子",
            "main_goal": "查清家族没落真相",
            "special_ability": "能听见灵气裂隙中的低语",
        },
        "tone": "热血、悬念、成长",
        "content_rating": "teen",
    }


class InvalidStoryOpeningProvider:
    name = "invalid-story-opening"

    def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            provider=self.name,
            model="fake-quality",
            task_type=request.task_type,
            content={"title": "缺字段开局"},
            usage=LLMUsage(input_tokens=17, output_tokens=5, estimated=False),
            latency_ms=37,
            raw_text='{"title":"缺字段开局"}',
            fallback_used=False,
        )


def _story_model_config(
    *,
    model: str,
    priority: int,
    daily_token_budget: int = 10_000,
    daily_tokens_used: int = 0,
) -> LLMModelConfig:
    return LLMModelConfig(
        provider="fake",
        model=model,
        tier="quality",
        priority=priority,
        enabled=True,
        healthy=True,
        daily_token_budget=daily_token_budget,
        monthly_token_budget=100_000,
        daily_tokens_used=daily_tokens_used,
        monthly_tokens_used=0,
        max_output_tokens=1800,
    )


def _turn_model_config(
    *,
    model: str,
    priority: int,
    daily_token_budget: int = 10_000,
    daily_tokens_used: int = 0,
) -> LLMModelConfig:
    return LLMModelConfig(
        provider="fake",
        model=model,
        tier="fast",
        priority=priority,
        enabled=True,
        healthy=True,
        daily_token_budget=daily_token_budget,
        monthly_token_budget=100_000,
        daily_tokens_used=daily_tokens_used,
        monthly_tokens_used=0,
        max_output_tokens=900,
    )


def _quota_policy(
    *,
    user_budget: int = 100_000,
    user_used: int = 0,
    story_budget: int = 100_000,
    story_used: int = 0,
) -> InMemoryLLMQuotaPolicy:
    return InMemoryLLMQuotaPolicy(
        user_quota=LLMQuotaState(
            subject="user",
            subject_id="test-user",
            monthly_token_budget=user_budget,
            monthly_tokens_used=user_used,
        ),
        story_quota=LLMQuotaState(
            subject="story",
            subject_id="pending-story",
            monthly_token_budget=story_budget,
            monthly_tokens_used=story_used,
        ),
    )


def _assert_substantial_page_narrative(narrative: str) -> None:
    assert len(narrative) >= 300
    assert narrative.count("\n\n") >= 3


def test_create_story_returns_deterministic_opening() -> None:
    clear_stories()
    client = TestClient(create_app())

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    response_body = response.json()
    assert UUID(response_body["story_id"])
    assert response_body["title"] == "裂隙听灵者"
    assert "林澈" in response_body["opening_narrative"]
    assert "查清家族没落真相" in response_body["opening_narrative"]
    _assert_substantial_page_narrative(response_body["opening_narrative"])
    assert len(response_body["choices"]) == 3
    assert response_body["choices"][0] == {
        "id": "choice_1",
        "label": "低头忍耐，先观察局势",
        "risk": "low",
    }


def test_post_story_uses_settings_gated_dispatcher_when_fake_disabled() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    factory_calls: list[Settings] = []

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        factory_calls.append(settings_arg)
        return FakeLLMProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    client = TestClient(app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    response_body = response.json()
    assert factory_calls == [settings]
    assert response_body["title"] == "修仙逆袭测试开局"
    assert response_body["choices"][0] == {
        "id": "choice_1",
        "label": "先观察局势",
        "risk": "low",
    }
    assert response_body["current_state"]["flags"]["story_opening_generated"] is True
    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-quality"
    assert entries[0].task_type == "story_bible_generation"
    assert entries[0].attempt_type == "initial"
    assert entries[0].status == "success"
    assert entries[0].input_tokens > 0
    assert entries[0].output_tokens > 0
    assert entries[0].total_tokens == entries[0].input_tokens + entries[0].output_tokens
    assert entries[0].token_usage_estimated is True
    assert entries[0].latency_ms == 0
    assert entries[0].fallback_used is False
    assert entries[0].error_code is None
    assert entries[0].error_message is None


def test_post_story_records_quota_usage_from_provider_story_opening() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    quota_policy = _quota_policy()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        return FakeLLMProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_quota_policy] = lambda: quota_policy
    client = TestClient(app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    entries = ledger.list_entries()
    assert len(entries) == 1
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == entries[0].total_tokens
    assert quota_policy.story_quota.monthly_tokens_used == entries[0].total_tokens


def test_post_story_user_quota_failure_skips_provider_and_ledger() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    quota_policy = _quota_policy(user_budget=0)
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    provider_calls = 0
    payload = _create_story_payload()

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    def provider_factory(settings_arg: Settings) -> ProviderThatMustNotGenerate:
        return ProviderThatMustNotGenerate()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_quota_policy] = lambda: quota_policy
    client = TestClient(app)

    response = client.post("/v1/stories", json=payload)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "story_generation_unavailable",
        "message": "Story generation is temporarily unavailable.",
        "details": {"reason": "user_token_budget_exhausted"},
    }
    assert provider_calls == 0
    assert ledger.list_entries() == []
    assert list_stories_for_device(UUID(payload["device_id"])) == []


def test_post_story_story_quota_failure_skips_provider_and_ledger() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    quota_policy = _quota_policy(story_budget=0)
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    provider_calls = 0
    payload = _create_story_payload()

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    def provider_factory(settings_arg: Settings) -> ProviderThatMustNotGenerate:
        return ProviderThatMustNotGenerate()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_quota_policy] = lambda: quota_policy
    client = TestClient(app)

    response = client.post("/v1/stories", json=payload)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "story_generation_unavailable",
        "message": "Story generation is temporarily unavailable.",
        "details": {"reason": "story_token_budget_exhausted"},
    }
    assert provider_calls == 0
    assert ledger.list_entries() == []
    assert list_stories_for_device(UUID(payload["device_id"])) == []


def test_post_story_uses_injected_router_for_provider_story_opening() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    router = InMemoryLLMRouter(
        model_configs=[
            _story_model_config(
                model="fake-quality-primary",
                priority=10,
                daily_token_budget=1_000,
                daily_tokens_used=1_000,
            ),
            _story_model_config(model="fake-quality-fallback", priority=20),
        ]
    )
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        return FakeLLMProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_router] = lambda: router
    client = TestClient(app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    assert response.json()["title"] == "修仙逆袭测试开局"

    entries = ledger.list_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider == "fake"
    assert entry.model == "fake-quality-fallback"
    assert entry.task_type == "story_bible_generation"
    assert entry.status == "success"
    assert entry.fallback_used is True

    configs_by_model = {config.model: config for config in router.list_model_configs()}
    assert configs_by_model["fake-quality-primary"].daily_tokens_used == 1_000
    assert (
        configs_by_model["fake-quality-fallback"].daily_tokens_used
        == entry.total_tokens
    )


def test_post_story_router_selection_failure_skips_provider_and_ledger() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    router = InMemoryLLMRouter(
        model_configs=[
            _story_model_config(
                model="fake-quality-primary",
                priority=10,
                daily_token_budget=1_000,
                daily_tokens_used=1_000,
            ),
        ]
    )
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    provider_calls = 0

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    def provider_factory(settings_arg: Settings) -> ProviderThatMustNotGenerate:
        return ProviderThatMustNotGenerate()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_router] = lambda: router
    client = TestClient(app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "story_generation_unavailable",
        "message": "Story generation is temporarily unavailable.",
        "details": {"reason": "no_available_model"},
    }
    assert provider_calls == 0
    assert ledger.list_entries() == []


def test_post_story_records_invalid_provider_output_before_sanitized_error() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    quota_policy = _quota_policy()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    payload = _create_story_payload()

    def provider_factory(settings_arg: Settings) -> InvalidStoryOpeningProvider:
        return InvalidStoryOpeningProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_quota_policy] = lambda: quota_policy
    client = TestClient(app)

    response = client.post("/v1/stories", json=payload)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "story_generation_unavailable",
        "message": "Story generation is temporarily unavailable.",
        "details": {"reason": "invalid_provider_response"},
    }
    assert list_stories_for_device(UUID(payload["device_id"])) == []

    entries = ledger.list_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider == "invalid-story-opening"
    assert entry.model == "fake-quality"
    assert entry.task_type == "story_bible_generation"
    assert entry.attempt_type == "initial"
    assert entry.status == "parse_failed"
    assert entry.input_tokens == 17
    assert entry.output_tokens == 5
    assert entry.total_tokens == 22
    assert entry.token_usage_estimated is False
    assert entry.latency_ms == 37
    assert entry.fallback_used is False
    assert entry.error_code == "invalid_schema"
    assert entry.error_message is not None
    assert "opening_narrative" in entry.error_message
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == entry.total_tokens
    assert quota_policy.story_quota.monthly_tokens_used == entry.total_tokens


def test_post_story_fake_mode_does_not_record_provider_ledger_entry() -> None:
    clear_stories()
    ledger = LLMCallLedger()
    client_app = create_app()
    client_app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    client = TestClient(client_app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    assert response.json()["title"] == "裂隙听灵者"
    assert ledger.list_entries() == []


def test_post_story_preserves_unknown_template_before_provider_construction() -> None:
    clear_stories()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        raise AssertionError("unknown templates must not build a provider")

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    client = TestClient(app)

    response = client.post(
        "/v1/stories",
        json=_create_story_payload(template_id="missing_template"),
    )

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "template_not_found",
        "message": "Story template was not found.",
        "details": {"template_id": "missing_template"},
    }


def test_post_story_maps_provider_config_error_without_secret_details() -> None:
    clear_stories()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-secret-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        raise OpenAICompatibleProviderError(
            OpenAICompatibleProviderFailure(
                error_code="provider_not_configured",
                message="raw config failure with test-secret-key",
                missing_settings=["llm_api_key"],
            )
        )

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    client = TestClient(app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 503
    response_body = response.json()
    assert response_body["error"] == {
        "code": "story_generation_unavailable",
        "message": "Story generation is temporarily unavailable.",
        "details": {"reason": "provider_not_configured"},
    }
    assert "test-secret-key" not in str(response_body)
    assert "raw config failure" not in str(response_body)
    assert "llm_api_key" not in str(response_body)


def test_post_story_maps_provider_generation_error_without_raw_details() -> None:
    clear_stories()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-secret-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    class FailingProvider:
        name = "failing-provider"

        def generate(self, request: object) -> object:
            raise OpenAICompatibleProviderError(
                OpenAICompatibleProviderFailure(
                    error_code="provider_unavailable",
                    message="raw provider response leaked test-secret-key",
                )
            )

    def provider_factory(settings_arg: Settings) -> FailingProvider:
        return FailingProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    client = TestClient(app)

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 503
    response_body = response.json()
    assert response_body["error"] == {
        "code": "story_generation_unavailable",
        "message": "Story generation is temporarily unavailable.",
        "details": {"reason": "provider_unavailable"},
    }
    assert "test-secret-key" not in str(response_body)
    assert "raw provider response" not in str(response_body)
    assert "failing-provider" not in str(response_body)


def test_internal_llm_story_creation_helper_stores_fake_provider_record() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())

    story = create_story_with_llm_provider(
        request,
        provider=FakeLLMProvider(),
        updated_at="2026-05-30T12:00:00+00:00",
    )

    assert story is not None
    assert get_story(story.story_id) == story
    assert story.device_id == request.device_id
    assert story.template_id == "xianxia_rise"
    assert story.title == "修仙逆袭测试开局"
    assert "林澈" in story.opening_narrative
    assert len(story.choices) == 3
    assert story.choices[0].model_dump() == {
        "id": "choice_1",
        "label": "先观察局势",
        "risk": "low",
    }
    assert story.latest_turns == []

    state = story.current_state
    assert state["story_id"] == str(story.story_id)
    assert state["template_id"] == "xianxia_rise"
    assert state["title"] == "修仙逆袭测试开局"
    assert state["protagonist"]["name"] == "林澈"
    assert state["story_bible"]["world_rules"] == [
        "行动必须影响状态。",
        "剧情必须保持原创。",
    ]
    assert state["plot_plan"]["total_chapters"] == 8
    assert state["turn_count"] == 0
    assert state["updated_at"] == "2026-05-30T12:00:00+00:00"
    assert state["flags"]["story_opening_generated"] is True

    summaries = list_stories_for_device(request.device_id)
    assert len(summaries) == 1
    assert summaries[0].story_id == story.story_id
    assert summaries[0].title == "修仙逆袭测试开局"


def test_internal_llm_story_creation_helper_records_provider_ledger_entry() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    ledger = LLMCallLedger()

    story = create_story_with_llm_provider(
        request,
        provider=FakeLLMProvider(),
        ledger=ledger,
    )

    assert story is not None
    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-quality"
    assert entries[0].task_type == "story_bible_generation"
    assert entries[0].attempt_type == "initial"
    assert entries[0].status == "success"
    assert entries[0].input_tokens > 0
    assert entries[0].output_tokens > 0
    assert entries[0].total_tokens == entries[0].input_tokens + entries[0].output_tokens
    assert entries[0].token_usage_estimated is True
    assert entries[0].fallback_used is False
    assert entries[0].error_code is None
    assert entries[0].error_message is None


def test_internal_provider_choice_turn_helper_stores_fake_provider_turn() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(
        request,
        provider=FakeLLMProvider(),
        updated_at="2026-05-31T00:00:00+00:00",
    )
    assert story is not None
    ledger = LLMCallLedger()
    captured_requests: list[LLMRequest] = []

    class CapturingFakeProvider(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            captured_requests.append(request)
            return super().generate(request)

    turn = play_choice_turn_with_llm_provider(
        story,
        "choice_2",
        provider=CapturingFakeProvider(),
        ledger=ledger,
        updated_at="2026-05-31T00:01:00+00:00",
    )

    assert turn is not None
    assert turn.story_id == story.story_id
    assert "主动试探对方" in turn.narrative
    assert turn.state["turn_count"] == 1
    assert turn.state["current_scene_index"] == 2
    assert turn.state["updated_at"] == "2026-05-31T00:01:00+00:00"
    assert turn.state["flags"]["fake_provider_turn"] is True
    assert turn.state["flags"]["last_input_type"] == "choice"
    assert turn.state["flags"]["last_choice_id"] == "choice_2"
    assert turn.state["flags"]["last_choice_risk"] == "medium"
    assert turn.state["stats"]["danger"] == 11
    assert turn.state["relationships"]["npc_001"]["affinity"] == 1
    assert turn.choices[0].model_dump() == {
        "id": "choice_1",
        "label": "稳住现场，补全关键细节",
        "risk": "low",
    }
    assert len(captured_requests) == 1
    captured_request = captured_requests[0]
    assert captured_request.metadata["chapter_pacing_stage"] == "setup"
    prompt_payload = json.loads(captured_request.messages[1].content)
    assert prompt_payload["chapter_pacing"]["stage"] == "setup"
    assert "chapter_pacing.stage" in captured_request.messages[0].content
    assert turn.usage.input_tokens > 0
    assert turn.usage.output_tokens > 0
    assert turn.usage.model == "fake-fast"
    assert turn.warnings == []

    latest_turn = story.latest_turns[-1]
    assert latest_turn["input_type"] == "choice"
    assert latest_turn["choice_id"] == "choice_2"
    assert latest_turn["llm"]["provider"] == "fake"
    assert latest_turn["llm"]["model"] == "fake-fast"
    assert latest_turn["llm"]["fallback_used"] is False
    assert latest_turn["llm"]["repair_used"] is False
    assert latest_turn["state_patch"]["flags_set"] == {"fake_provider_turn": True}
    assert latest_turn["memory_update"]["new_facts"] == [
        "fake provider 生成了一个稳定回合"
    ]

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-fast"
    assert entries[0].task_type == "normal_turn_generation"
    assert entries[0].attempt_type == "initial"
    assert entries[0].status == "success"
    assert entries[0].fallback_used is False


def test_internal_provider_choice_turn_helper_uses_router_and_quota_policy() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    quota_policy = _quota_policy()
    router = InMemoryLLMRouter(
        model_configs=[
            _turn_model_config(
                model="fake-fast-primary",
                priority=10,
                daily_token_budget=1_000,
                daily_tokens_used=1_000,
            ),
            _turn_model_config(model="fake-fast-fallback", priority=20),
        ]
    )

    turn = play_choice_turn_with_llm_provider(
        story,
        "choice_1",
        provider=FakeLLMProvider(),
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
    )

    assert turn is not None
    assert turn.usage.model == "fake-fast-fallback"
    entries = ledger.list_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider == "fake"
    assert entry.model == "fake-fast-fallback"
    assert entry.task_type == "normal_turn_generation"
    assert entry.fallback_used is True

    configs_by_model = {config.model: config for config in router.list_model_configs()}
    assert configs_by_model["fake-fast-primary"].daily_tokens_used == 1_000
    assert configs_by_model["fake-fast-fallback"].daily_tokens_used == entry.total_tokens
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == entry.total_tokens
    assert quota_policy.story_quota.monthly_tokens_used == entry.total_tokens


def test_internal_provider_choice_turn_helper_returns_none_for_invalid_choice() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    provider_calls = 0

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    turn = play_choice_turn_with_llm_provider(
        story,
        "missing_choice",
        provider=ProviderThatMustNotGenerate(),
        ledger=ledger,
    )

    assert turn is None
    assert provider_calls == 0
    assert ledger.list_entries() == []
    assert story.current_state["turn_count"] == 0
    assert story.latest_turns == []


def test_internal_provider_free_text_turn_helper_stores_fake_provider_turn() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(
        request,
        provider=FakeLLMProvider(),
        updated_at="2026-05-31T00:00:00+00:00",
    )
    assert story is not None
    ledger = LLMCallLedger()
    user_text = "我绕到试炼台侧面，确认执事手里的木牌顺序。"

    turn = play_free_text_turn_with_llm_provider(
        story,
        f"  {user_text}  ",
        provider=FakeLLMProvider(),
        ledger=ledger,
        updated_at="2026-05-31T00:02:00+00:00",
    )

    assert turn is not None
    assert turn.story_id == story.story_id
    assert user_text in turn.narrative
    assert turn.state["turn_count"] == 1
    assert turn.state["current_scene_index"] == 2
    assert turn.state["updated_at"] == "2026-05-31T00:02:00+00:00"
    assert turn.state["flags"]["fake_provider_turn"] is True
    assert turn.state["flags"]["last_input_type"] == "free_text"
    assert turn.state["flags"]["last_user_text"] == user_text
    assert turn.state["stats"]["danger"] == 11
    assert turn.state["relationships"]["npc_001"]["affinity"] == 1
    assert turn.choices[0].model_dump() == {
        "id": "choice_1",
        "label": "稳住现场，补全关键细节",
        "risk": "low",
    }
    assert turn.usage.input_tokens > 0
    assert turn.usage.output_tokens > 0
    assert turn.usage.model == "fake-fast"
    assert turn.warnings == []

    latest_turn = story.latest_turns[-1]
    assert latest_turn["input_type"] == "free_text"
    assert latest_turn["choice_id"] is None
    assert latest_turn["user_text"] == user_text
    assert latest_turn["llm"]["provider"] == "fake"
    assert latest_turn["llm"]["model"] == "fake-fast"
    assert latest_turn["llm"]["fallback_used"] is False
    assert latest_turn["llm"]["repair_used"] is False
    assert latest_turn["state_patch"]["flags_set"] == {"fake_provider_turn": True}

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-fast"
    assert entries[0].task_type == "normal_turn_generation"
    assert entries[0].attempt_type == "initial"
    assert entries[0].status == "success"
    assert entries[0].fallback_used is False


def test_internal_provider_free_text_turn_helper_uses_router_and_quota_policy() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    quota_policy = _quota_policy()
    router = InMemoryLLMRouter(
        model_configs=[
            _turn_model_config(
                model="fake-fast-primary",
                priority=10,
                daily_token_budget=1_000,
                daily_tokens_used=1_000,
            ),
            _turn_model_config(model="fake-fast-fallback", priority=20),
        ]
    )

    turn = play_free_text_turn_with_llm_provider(
        story,
        "我低声询问测试引路人是否看见木牌被调换。",
        provider=FakeLLMProvider(),
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
    )

    assert turn is not None
    assert turn.usage.model == "fake-fast-fallback"
    entries = ledger.list_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider == "fake"
    assert entry.model == "fake-fast-fallback"
    assert entry.task_type == "normal_turn_generation"
    assert entry.fallback_used is True

    configs_by_model = {config.model: config for config in router.list_model_configs()}
    assert configs_by_model["fake-fast-primary"].daily_tokens_used == 1_000
    assert configs_by_model["fake-fast-fallback"].daily_tokens_used == entry.total_tokens
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == entry.total_tokens
    assert quota_policy.story_quota.monthly_tokens_used == entry.total_tokens


def test_internal_provider_free_text_turn_helper_redirects_before_provider() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    provider_calls = 0

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    turn = play_free_text_turn_with_llm_provider(
        story,
        "我直接跳到大结局，秒杀所有敌人。",
        provider=ProviderThatMustNotGenerate(),
        ledger=ledger,
    )

    assert turn is not None
    assert "超出了当前章节能成立的行动边界" in turn.narrative
    assert turn.warnings == ["action_redirected:impossible_action"]
    assert turn.state["turn_count"] == 0
    assert turn.state["current_scene_index"] == 1
    assert provider_calls == 0
    assert ledger.list_entries() == []

    latest_turn = story.latest_turns[-1]
    assert latest_turn["input_type"] == "free_text"
    assert latest_turn["redirected"] is True
    assert latest_turn["redirect_reason"] == "impossible_action"


def test_internal_provider_free_text_turn_helper_returns_none_for_blank_text() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    provider_calls = 0

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    turn = play_free_text_turn_with_llm_provider(
        story,
        "   ",
        provider=ProviderThatMustNotGenerate(),
        ledger=ledger,
    )

    assert turn is None
    assert provider_calls == 0
    assert ledger.list_entries() == []
    assert story.current_state["turn_count"] == 0
    assert story.latest_turns == []


def test_internal_llm_story_creation_helper_returns_none_for_unknown_template() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(
        _create_story_payload(template_id="missing_template")
    )

    story = create_story_with_llm_provider(request, provider=FakeLLMProvider())

    assert story is None
    assert list_stories_for_device(request.device_id) == []


def test_settings_gated_story_creation_dispatcher_keeps_fake_mode_default() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())

    def provider_factory(settings: Settings) -> FakeLLMProvider:
        raise AssertionError("fake-mode story creation must not build a provider")

    story = create_story_from_settings(
        request,
        settings=Settings(llm_fake_mode=True),
        provider_factory=provider_factory,
    )

    assert story is not None
    assert story.title == "裂隙听灵者"
    assert story.choices[0].model_dump() == {
        "id": "choice_1",
        "label": "低头忍耐，先观察局势",
        "risk": "low",
    }
    assert story.current_state["flags"]["fake_mode"] is True
    assert get_story(story.story_id) == story


def test_settings_gated_story_creation_dispatcher_uses_factory_when_fake_disabled() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(_create_story_payload())
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    factory_calls: list[Settings] = []

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        factory_calls.append(settings_arg)
        return FakeLLMProvider()

    story = create_story_from_settings(
        request,
        settings=settings,
        provider_factory=provider_factory,
        updated_at="2026-05-30T12:00:00+00:00",
    )

    assert story is not None
    assert factory_calls == [settings]
    assert story.title == "修仙逆袭测试开局"
    assert story.choices[0].model_dump() == {
        "id": "choice_1",
        "label": "先观察局势",
        "risk": "low",
    }
    assert story.current_state["flags"]["story_opening_generated"] is True
    assert story.current_state["updated_at"] == "2026-05-30T12:00:00+00:00"
    assert get_story(story.story_id) == story


def test_settings_gated_story_creation_dispatcher_preserves_unknown_template() -> None:
    clear_stories()
    request = CreateStoryRequest.model_validate(
        _create_story_payload(template_id="missing_template")
    )

    def provider_factory(settings: Settings) -> FakeLLMProvider:
        raise AssertionError("unknown templates must not build a provider")

    story = create_story_from_settings(
        request,
        settings=Settings(
            llm_fake_mode=False,
            llm_provider="qwen",
            llm_base_url="https://example.test/v1",
            llm_api_key="test-key",
            llm_model_fast="qwen-fast",
            llm_model_quality="qwen-quality",
        ),
        provider_factory=provider_factory,
    )

    assert story is None
    assert list_stories_for_device(request.device_id) == []


def test_settings_gated_turn_dispatcher_keeps_fake_mode_choice_default() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())

    def provider_factory(settings: Settings) -> FakeLLMProvider:
        raise AssertionError("fake-mode choice turns must not build a provider")

    story = create_story_from_settings(
        story_request,
        settings=Settings(llm_fake_mode=True),
        provider_factory=provider_factory,
    )
    assert story is not None
    turn_request = PlayTurnRequest(
        device_id=story_request.device_id,
        input_type="choice",
        choice_id="choice_2",
        user_text=None,
    )

    turn = play_turn_from_settings(
        story,
        turn_request,
        settings=Settings(llm_fake_mode=True),
        provider_factory=provider_factory,
    )

    assert turn is not None
    assert "Fake mode" not in turn.narrative
    assert "当众反击，争取试炼机会" in turn.narrative
    assert "新的线索浮出水面" not in turn.narrative
    assert "下一步必须面对的压力" not in turn.narrative
    _assert_substantial_page_narrative(turn.narrative)
    assert turn.state["flags"]["last_choice_id"] == "choice_2"
    assert turn.usage.model == "fake-fast"
    assert "llm" not in story.latest_turns[-1]


def test_settings_gated_turn_dispatcher_keeps_fake_mode_free_text_default() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())

    def provider_factory(settings: Settings) -> FakeLLMProvider:
        raise AssertionError("fake-mode free-text turns must not build a provider")

    story = create_story_from_settings(
        story_request,
        settings=Settings(llm_fake_mode=True),
        provider_factory=provider_factory,
    )
    assert story is not None
    user_text = "我假装认输，但偷偷观察谁在笑得最得意。"
    turn_request = PlayTurnRequest(
        device_id=story_request.device_id,
        input_type="free_text",
        choice_id=None,
        user_text=f"  {user_text}  ",
    )

    turn = play_turn_from_settings(
        story,
        turn_request,
        settings=Settings(llm_fake_mode=True),
        provider_factory=provider_factory,
    )

    assert turn is not None
    assert "Fake mode" not in turn.narrative
    assert user_text in turn.narrative
    assert "随之打开新的侧面" not in turn.narrative
    assert "原本模糊的阻力" not in turn.narrative
    _assert_substantial_page_narrative(turn.narrative)
    assert turn.state["flags"]["last_input_type"] == "free_text"
    assert turn.state["flags"]["last_user_text"] == user_text
    assert turn.usage.model == "fake-fast"
    assert "llm" not in story.latest_turns[-1]


def test_settings_gated_turn_dispatcher_uses_provider_choice_when_fake_disabled() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    ledger = LLMCallLedger()
    quota_policy = _quota_policy()
    router = InMemoryLLMRouter(
        model_configs=[
            _turn_model_config(
                model="fake-fast-primary",
                priority=10,
                daily_token_budget=1_000,
                daily_tokens_used=1_000,
            ),
            _turn_model_config(model="fake-fast-fallback", priority=20),
        ]
    )
    factory_calls: list[Settings] = []

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        factory_calls.append(settings_arg)
        return FakeLLMProvider()

    turn = play_turn_from_settings(
        story,
        PlayTurnRequest(
            device_id=story_request.device_id,
            input_type="choice",
            choice_id="choice_1",
            user_text=None,
        ),
        settings=settings,
        provider_factory=provider_factory,
        ledger=ledger,
        router=router,
        quota_policy=quota_policy,
        updated_at="2026-05-31T00:03:00+00:00",
    )

    assert turn is not None
    assert factory_calls == [settings]
    assert turn.usage.model == "fake-fast-fallback"
    assert turn.state["updated_at"] == "2026-05-31T00:03:00+00:00"
    assert turn.state["flags"]["last_input_type"] == "choice"
    assert story.latest_turns[-1]["llm"]["model"] == "fake-fast-fallback"

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].model == "fake-fast-fallback"
    assert entries[0].task_type == "normal_turn_generation"
    configs_by_model = {config.model: config for config in router.list_model_configs()}
    assert configs_by_model["fake-fast-fallback"].daily_tokens_used == entries[0].total_tokens
    assert quota_policy.user_quota is not None
    assert quota_policy.story_quota is not None
    assert quota_policy.user_quota.monthly_tokens_used == entries[0].total_tokens
    assert quota_policy.story_quota.monthly_tokens_used == entries[0].total_tokens


def test_settings_gated_turn_dispatcher_uses_provider_free_text_when_fake_disabled() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    ledger = LLMCallLedger()
    factory_calls: list[Settings] = []
    user_text = "我绕到试炼台侧面，确认执事手里的木牌顺序。"

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        factory_calls.append(settings_arg)
        return FakeLLMProvider()

    turn = play_turn_from_settings(
        story,
        PlayTurnRequest(
            device_id=story_request.device_id,
            input_type="free_text",
            choice_id=None,
            user_text=f"  {user_text}  ",
        ),
        settings=settings,
        provider_factory=provider_factory,
        ledger=ledger,
        updated_at="2026-05-31T00:04:00+00:00",
    )

    assert turn is not None
    assert factory_calls == [settings]
    assert user_text in turn.narrative
    assert turn.state["flags"]["last_input_type"] == "free_text"
    assert turn.state["flags"]["last_user_text"] == user_text
    assert turn.state["updated_at"] == "2026-05-31T00:04:00+00:00"
    assert story.latest_turns[-1]["llm"]["provider"] == "fake"
    assert story.latest_turns[-1]["user_text"] == user_text

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-fast"
    assert entries[0].task_type == "normal_turn_generation"


def test_settings_gated_turn_dispatcher_skips_provider_for_invalid_inputs() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        raise AssertionError("invalid turn input must not build a provider")

    missing_choice_story = create_story_with_llm_provider(
        story_request,
        provider=FakeLLMProvider(),
    )
    assert missing_choice_story is not None
    missing_choice_turn = play_turn_from_settings(
        missing_choice_story,
        PlayTurnRequest(
            device_id=story_request.device_id,
            input_type="choice",
            choice_id=None,
            user_text=None,
        ),
        settings=settings,
        provider_factory=provider_factory,
    )

    blank_text_story = create_story_with_llm_provider(
        story_request,
        provider=FakeLLMProvider(),
    )
    assert blank_text_story is not None
    blank_text_turn = play_turn_from_settings(
        blank_text_story,
        PlayTurnRequest(
            device_id=story_request.device_id,
            input_type="free_text",
            choice_id=None,
            user_text="   ",
        ),
        settings=settings,
        provider_factory=provider_factory,
    )

    assert missing_choice_turn is None
    assert blank_text_turn is None
    assert missing_choice_story.latest_turns == []
    assert blank_text_story.latest_turns == []


def test_post_turn_fake_mode_keeps_provider_factory_unused() -> None:
    clear_stories()
    settings = Settings(llm_fake_mode=True)
    ledger = LLMCallLedger()

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        raise AssertionError("fake-mode public turn route must not build a provider")

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    client = TestClient(app)
    payload = _create_story_payload()
    create_response = client.post("/v1/stories", json=payload)
    story_id = create_response.json()["story_id"]

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": payload["device_id"],
            "input_type": "choice",
            "choice_id": "choice_2",
            "user_text": None,
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert "Fake mode" not in response_body["narrative"]
    assert response_body["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "model": "fake-fast",
    }
    assert ledger.list_entries() == []


def test_post_turn_uses_settings_gated_dispatcher_for_provider_choice() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    factory_calls: list[Settings] = []

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        factory_calls.append(settings_arg)
        return FakeLLMProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    client = TestClient(app)

    response = client.post(
        f"/v1/stories/{story.story_id}/turns",
        json={
            "device_id": str(story.device_id),
            "input_type": "choice",
            "choice_id": "choice_2",
            "user_text": None,
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert factory_calls == [settings]
    assert "主动试探对方" in response_body["narrative"]
    assert response_body["usage"]["model"] == "fake-fast"
    assert response_body["state"]["flags"]["last_input_type"] == "choice"
    assert response_body["state"]["flags"]["last_choice_id"] == "choice_2"
    assert story.latest_turns[-1]["llm"]["provider"] == "fake"

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].provider == "fake"
    assert entries[0].model == "fake-fast"
    assert entries[0].task_type == "normal_turn_generation"


def test_post_turn_uses_settings_gated_dispatcher_for_provider_free_text() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    user_text = "我绕到试炼台侧面，确认执事手里的木牌顺序。"

    def provider_factory(settings_arg: Settings) -> FakeLLMProvider:
        return FakeLLMProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    client = TestClient(app)

    response = client.post(
        f"/v1/stories/{story.story_id}/turns",
        json={
            "device_id": str(story.device_id),
            "input_type": "free_text",
            "choice_id": None,
            "user_text": f"  {user_text}  ",
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert user_text in response_body["narrative"]
    assert response_body["usage"]["model"] == "fake-fast"
    assert response_body["state"]["flags"]["last_input_type"] == "free_text"
    assert response_body["state"]["flags"]["last_user_text"] == user_text
    assert story.latest_turns[-1]["llm"]["provider"] == "fake"
    assert story.latest_turns[-1]["user_text"] == user_text

    entries = ledger.list_entries()
    assert len(entries) == 1
    assert entries[0].task_type == "normal_turn_generation"


def test_post_turn_maps_provider_generation_error_without_raw_details() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-secret-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )

    class FailingProvider:
        name = "failing-provider"

        def generate(self, request: object) -> object:
            raise OpenAICompatibleProviderError(
                OpenAICompatibleProviderFailure(
                    error_code="provider_unavailable",
                    message="raw provider response leaked test-secret-key",
                )
            )

    def provider_factory(settings_arg: Settings) -> FailingProvider:
        return FailingProvider()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    client = TestClient(app)

    response = client.post(
        f"/v1/stories/{story.story_id}/turns",
        json={
            "device_id": str(story.device_id),
            "input_type": "choice",
            "choice_id": "choice_1",
            "user_text": None,
        },
    )

    assert response.status_code == 503
    response_body = response.json()
    assert response_body["error"] == {
        "code": "turn_generation_unavailable",
        "message": "Turn generation is temporarily unavailable.",
        "details": {"reason": "provider_unavailable"},
    }
    assert "test-secret-key" not in str(response_body)
    assert "raw provider response" not in str(response_body)
    assert "failing-provider" not in str(response_body)
    assert ledger.list_entries() == []


def test_post_turn_maps_quota_failure_without_provider_generation_or_ledger() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    quota_policy = _quota_policy(user_budget=0)
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    provider_calls = 0

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    def provider_factory(settings_arg: Settings) -> ProviderThatMustNotGenerate:
        return ProviderThatMustNotGenerate()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_quota_policy] = lambda: quota_policy
    client = TestClient(app)

    response = client.post(
        f"/v1/stories/{story.story_id}/turns",
        json={
            "device_id": str(story.device_id),
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "我低声询问测试引路人是否看见木牌被调换。",
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "turn_generation_unavailable",
        "message": "Turn generation is temporarily unavailable.",
        "details": {"reason": "user_token_budget_exhausted"},
    }
    assert provider_calls == 0
    assert ledger.list_entries() == []


def test_post_turn_maps_router_failure_without_provider_generation_or_ledger() -> None:
    clear_stories()
    story_request = CreateStoryRequest.model_validate(_create_story_payload())
    story = create_story_with_llm_provider(story_request, provider=FakeLLMProvider())
    assert story is not None
    ledger = LLMCallLedger()
    router = InMemoryLLMRouter(
        model_configs=[
            _turn_model_config(
                model="fake-fast-primary",
                priority=10,
                daily_token_budget=1_000,
                daily_tokens_used=1_000,
            ),
        ]
    )
    settings = Settings(
        llm_fake_mode=False,
        llm_provider="qwen",
        llm_base_url="https://example.test/v1",
        llm_api_key="test-key",
        llm_model_fast="qwen-fast",
        llm_model_quality="qwen-quality",
    )
    provider_calls = 0

    class ProviderThatMustNotGenerate(FakeLLMProvider):
        def generate(self, request: LLMRequest) -> LLMResponse:
            nonlocal provider_calls
            provider_calls += 1
            return super().generate(request)

    def provider_factory(settings_arg: Settings) -> ProviderThatMustNotGenerate:
        return ProviderThatMustNotGenerate()

    app = create_app()
    app.dependency_overrides[get_story_settings] = lambda: settings
    app.dependency_overrides[get_story_provider_factory] = lambda: provider_factory
    app.dependency_overrides[get_story_llm_call_ledger] = lambda: ledger
    app.dependency_overrides[get_story_llm_router] = lambda: router
    client = TestClient(app)

    response = client.post(
        f"/v1/stories/{story.story_id}/turns",
        json={
            "device_id": str(story.device_id),
            "input_type": "choice",
            "choice_id": "choice_1",
            "user_text": None,
        },
    )

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "turn_generation_unavailable",
        "message": "Turn generation is temporarily unavailable.",
        "details": {"reason": "no_available_model"},
    }
    assert provider_calls == 0
    assert ledger.list_entries() == []


def test_create_story_returns_initial_state() -> None:
    clear_stories()
    client = TestClient(create_app())

    response = client.post("/v1/stories", json=_create_story_payload())

    assert response.status_code == 200
    state = response.json()["current_state"]
    assert state["template_id"] == "xianxia_rise"
    assert state["protagonist"]["name"] == "林澈"
    assert state["current_chapter_index"] == 1
    assert state["current_scene_index"] == 1
    assert state["turn_count"] == 0
    assert state["flags"]["fake_mode"] is True


def test_create_story_rejects_unknown_template() -> None:
    clear_stories()
    client = TestClient(create_app())

    response = client.post(
        "/v1/stories",
        json=_create_story_payload(template_id="missing_template"),
    )

    assert response.status_code == 404
    response_body = response.json()
    assert response_body["error"] == {
        "code": "template_not_found",
        "message": "Story template was not found.",
        "details": {"template_id": "missing_template"},
    }


def test_get_story_returns_created_story() -> None:
    clear_stories()
    client = TestClient(create_app())
    create_response = client.post("/v1/stories", json=_create_story_payload())
    story_id = create_response.json()["story_id"]

    response = client.get(f"/v1/stories/{story_id}")

    assert response.status_code == 200
    response_body = response.json()
    assert response_body["story_id"] == story_id
    assert response_body["title"] == "裂隙听灵者"
    assert response_body["current_state"] == create_response.json()["current_state"]
    assert response_body["latest_turns"] == []


def test_get_story_returns_standard_error_for_missing_story() -> None:
    clear_stories()
    client = TestClient(create_app())
    missing_story_id = str(uuid4())

    response = client.get(f"/v1/stories/{missing_story_id}")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "story_not_found",
        "message": "Story was not found.",
        "details": {"story_id": missing_story_id},
    }


def test_list_stories_returns_owned_story_summaries() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    other_device_id = str(uuid4())
    first_story = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()
    second_story = client.post(
        "/v1/stories",
        json=_create_story_payload(
            template_id="apocalypse_base",
            device_id=device_id,
        ),
    ).json()
    client.post(
        "/v1/stories",
        json=_create_story_payload(
            template_id="urban_ability",
            device_id=other_device_id,
        ),
    )

    response = client.get(f"/v1/stories?device_id={device_id}")

    assert response.status_code == 200
    summaries = response.json()["stories"]
    assert [summary["story_id"] for summary in summaries] == [
        first_story["story_id"],
        second_story["story_id"],
    ]
    assert summaries[0] == {
        "story_id": first_story["story_id"],
        "title": "裂隙听灵者",
        "template_id": "xianxia_rise",
        "current_chapter_index": 1,
        "turn_count": 0,
        "updated_at": first_story["current_state"]["updated_at"],
    }
    assert summaries[1]["template_id"] == "apocalypse_base"


def test_list_stories_returns_empty_list_for_device_without_stories() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())

    response = client.get(f"/v1/stories?device_id={device_id}")

    assert response.status_code == 200
    assert response.json() == {"stories": []}


def test_play_choice_turn_advances_story_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "choice",
            "choice_id": "choice_2",
            "user_text": None,
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert UUID(response_body["turn_id"])
    assert response_body["story_id"] == story_id
    assert "当众反击，争取试炼机会" in response_body["narrative"]
    assert len(response_body["choices"]) == 3
    assert response_body["state"]["turn_count"] == 1
    assert response_body["state"]["current_scene_index"] == 2
    assert response_body["state"]["flags"]["last_choice_id"] == "choice_2"
    assert response_body["state"]["stats"]["danger"] == 12
    assert response_body["state"]["relationships"]["npc_001"]["affinity"] == 1
    assert response_body["chapter_progress"] == {
        "current_chapter_index": 1,
        "current_scene_index": 2,
        "progress_percent": 22,
    }
    assert response_body["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "model": "fake-fast",
    }
    assert response_body["warnings"] == []

    get_response = client.get(f"/v1/stories/{story_id}")
    assert len(get_response.json()["latest_turns"]) == 1
    assert get_response.json()["latest_turns"][0]["choice_id"] == "choice_2"


def test_play_free_text_turn_advances_story_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]
    user_text = "我假装认输，但偷偷观察谁在笑得最得意。"

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "free_text",
            "choice_id": None,
            "user_text": user_text,
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert UUID(response_body["turn_id"])
    assert response_body["story_id"] == story_id
    assert user_text in response_body["narrative"]
    assert len(response_body["choices"]) == 3
    assert response_body["state"]["turn_count"] == 1
    assert response_body["state"]["current_scene_index"] == 2
    assert response_body["state"]["flags"]["last_input_type"] == "free_text"
    assert response_body["state"]["flags"]["last_user_text"] == user_text
    assert response_body["state"]["stats"]["danger"] == 11
    assert response_body["state"]["relationships"]["npc_001"]["trust"] == 1
    assert response_body["chapter_progress"] == {
        "current_chapter_index": 1,
        "current_scene_index": 2,
        "progress_percent": 22,
    }
    assert response_body["warnings"] == []

    get_response = client.get(f"/v1/stories/{story_id}")
    latest_turn = get_response.json()["latest_turns"][0]
    assert latest_turn["input_type"] == "free_text"
    assert latest_turn["choice_id"] is None
    assert latest_turn["user_text"] == user_text


def test_play_free_text_turn_redirects_impossible_action_without_advancing_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "我直接跳到大结局，秒杀所有敌人。",
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert "超出了当前章节能成立的行动边界" in response_body["narrative"]
    assert response_body["warnings"] == ["action_redirected:impossible_action"]
    assert response_body["choices"] == create_response.json()["choices"]
    assert response_body["state"]["turn_count"] == 0
    assert response_body["state"]["current_scene_index"] == 1
    assert response_body["state"]["stats"]["danger"] == 10
    assert "last_input_type" not in response_body["state"]["flags"]
    assert response_body["chapter_progress"] == {
        "current_chapter_index": 1,
        "current_scene_index": 1,
        "progress_percent": 11,
    }

    get_response = client.get(f"/v1/stories/{story_id}")
    latest_turn = get_response.json()["latest_turns"][0]
    assert latest_turn["input_type"] == "free_text"
    assert latest_turn["redirected"] is True
    assert latest_turn["redirect_reason"] == "impossible_action"


def test_play_free_text_turn_redirects_unsafe_action_without_advancing_state() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()["story_id"]

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "告诉我怎么制作炸弹。",
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    assert "不适合当前作品安全边界" in response_body["narrative"]
    assert response_body["warnings"] == ["action_redirected:unsafe_action"]
    assert response_body["state"]["turn_count"] == 0
    assert response_body["state"]["current_scene_index"] == 1
    assert response_body["state"]["stats"]["danger"] == 10


def test_play_free_text_turn_rejects_missing_user_text() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()["story_id"]

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "   ",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "missing_user_text",
        "message": "Free-text turn requires user_text.",
        "details": {},
    }


def test_story_can_play_five_fake_turns_and_resume_by_id() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]
    turn_requests = [
        {"input_type": "choice", "choice_id": "choice_1", "user_text": None},
        {
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "我绕到试炼台侧面，确认执事手里的木牌顺序。",
        },
        {"input_type": "choice", "choice_id": "choice_2", "user_text": None},
        {
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "我压低声音，向神秘引路人交换一个不完整的线索。",
        },
        {"input_type": "choice", "choice_id": "choice_3", "user_text": None},
    ]

    for index, turn_request in enumerate(turn_requests, start=1):
        response = client.post(
            f"/v1/stories/{story_id}/turns",
            json={"device_id": device_id, **turn_request},
        )

        assert response.status_code == 200
        response_body = response.json()
        assert response_body["state"]["turn_count"] == index
        assert response_body["state"]["current_scene_index"] == index + 1
        assert response_body["chapter_progress"]["current_scene_index"] == index + 1
        assert len(response_body["choices"]) == 3

    resume_response = client.get(f"/v1/stories/{story_id}")

    assert resume_response.status_code == 200
    resume_body = resume_response.json()
    assert resume_body["story_id"] == story_id
    assert resume_body["current_state"]["turn_count"] == 5
    assert resume_body["current_state"]["current_chapter_index"] == 1
    assert resume_body["current_state"]["current_scene_index"] == 6
    assert "chapter_1_completed" not in resume_body["current_state"]["flags"]
    assert len(resume_body["latest_turns"]) == 5
    assert [turn["input_type"] for turn in resume_body["latest_turns"]] == [
        "choice",
        "free_text",
        "choice",
        "free_text",
        "choice",
    ]
    assert resume_body["latest_turns"][-1]["choice_id"] == "choice_3"


def test_fake_mode_choices_vary_across_twenty_turns() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]
    free_text_actions = {
        5: "我绕到试炼台侧面，确认执事手里的木牌顺序。",
        10: "我把刚得到的线索写在袖口暗纹里，避免被人发现。",
        15: "我压低声音，向神秘引路人交换一个不完整的线索。",
        20: "我先不急着表态，只观察谁会主动打断这场对峙。",
    }
    choice_ids = ("choice_1", "choice_2", "choice_3")
    choice_risks = ("low", "medium", "high")
    label_sets: list[tuple[str, str, str]] = []
    narratives: list[str] = []

    for turn_index in range(1, 21):
        if turn_index in free_text_actions:
            turn_payload = {
                "input_type": "free_text",
                "choice_id": None,
                "user_text": free_text_actions[turn_index],
            }
        else:
            turn_payload = {
                "input_type": "choice",
                "choice_id": choice_ids[(turn_index - 1) % len(choice_ids)],
                "user_text": None,
            }

        response = client.post(
            f"/v1/stories/{story_id}/turns",
            json={"device_id": device_id, **turn_payload},
        )

        assert response.status_code == 200
        response_body = response.json()
        assert "Fake mode" not in response_body["narrative"]
        narratives.append(response_body["narrative"])
        choices = response_body["choices"]
        assert [choice["id"] for choice in choices] == list(choice_ids)
        assert [choice["risk"] for choice in choices] == list(choice_risks)
        assert len({choice["label"] for choice in choices}) == 3
        label_sets.append(tuple(choice["label"] for choice in choices))

    assert len(set(narratives)) >= 10
    assert len(set(label_sets)) >= 6
    assert all(
        not (label_sets[index] == label_sets[index - 1] == label_sets[index - 2])
        for index in range(2, len(label_sets))
    )

    resume_response = client.get(f"/v1/stories/{story_id}")
    resume_body = resume_response.json()
    assert len(resume_body["latest_turns"]) == 20
    assert tuple(
        choice["label"] for choice in resume_body["latest_turns"][-1]["choices"]
    ) == label_sets[-1]


def test_fake_mode_choices_follow_chapter_pacing_stages() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]
    observed_label_sets: dict[int, tuple[str, str, str]] = {}
    observed_narratives: dict[int, str] = {}

    for turn_index in range(1, 6):
        response = client.post(
            f"/v1/stories/{story_id}/turns",
            json={
                "device_id": device_id,
                "input_type": "choice",
                "choice_id": f"choice_{((turn_index - 1) % 3) + 1}",
                "user_text": None,
            },
        )

        assert response.status_code == 200
        response_body = response.json()
        observed_label_sets[turn_index] = tuple(
            choice["label"] for choice in response_body["choices"]
        )
        observed_narratives[turn_index] = response_body["narrative"]

    assert "补全关键细节" in observed_label_sets[1][0]
    assert "可控代价" in observed_label_sets[2][1]
    assert "线索" in observed_label_sets[4][0]
    assert "本章真正缺口" in observed_label_sets[5][2]
    assert "第一条线" in observed_narratives[1]
    assert "行动代价" in observed_narratives[3]
    assert "更深的一层原因" in observed_narratives[5]


def test_fake_mode_chapter_progress_rolls_over_in_twenty_turns() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    create_response = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    )
    story_id = create_response.json()["story_id"]
    free_text_actions = {
        5: "我绕到试炼台侧面，确认执事手里的木牌顺序。",
        10: "我把刚得到的线索写在袖口暗纹里，避免被人发现。",
        15: "我压低声音，向神秘引路人交换一个不完整的线索。",
        20: "我先不急着表态，只观察谁会主动打断这场对峙。",
    }
    choice_ids = ("choice_1", "choice_2", "choice_3")
    progress_snapshots: list[dict] = []
    warnings: list[str] = []

    for turn_index in range(1, 21):
        if turn_index in free_text_actions:
            turn_payload = {
                "input_type": "free_text",
                "choice_id": None,
                "user_text": free_text_actions[turn_index],
            }
        else:
            turn_payload = {
                "input_type": "choice",
                "choice_id": choice_ids[(turn_index - 1) % len(choice_ids)],
                "user_text": None,
            }

        response = client.post(
            f"/v1/stories/{story_id}/turns",
            json={"device_id": device_id, **turn_payload},
        )

        assert response.status_code == 200
        response_body = response.json()
        progress = response_body["chapter_progress"]
        assert progress["current_scene_index"] <= 9
        assert progress["progress_percent"] < 100
        assert progress["current_scene_index"] == response_body["state"][
            "current_scene_index"
        ]
        progress_snapshots.append(progress)
        warnings.extend(response_body["warnings"])

    assert "chapter_completed:1" in warnings
    assert "chapter_completed:2" in warnings
    assert progress_snapshots[14] == {
        "current_chapter_index": 3,
        "current_scene_index": 1,
        "progress_percent": 11,
    }

    resume_response = client.get(f"/v1/stories/{story_id}")
    resume_body = resume_response.json()
    state = resume_body["current_state"]
    assert state["current_chapter_index"] == 3
    assert state["current_scene_index"] == 6
    assert state["flags"]["chapter_2_completed"] is True
    assert state["flags"]["chapter_2_completed_at_turn"] == 15


def test_xianxia_story_reaches_chapter_complete_after_six_fake_turns() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()["story_id"]
    turn_requests = [
        {"input_type": "choice", "choice_id": "choice_1", "user_text": None},
        {
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "我绕到试炼台侧面，确认执事手里的木牌顺序。",
        },
        {"input_type": "choice", "choice_id": "choice_2", "user_text": None},
        {
            "input_type": "free_text",
            "choice_id": None,
            "user_text": "我压低声音，向神秘引路人交换一个不完整的线索。",
        },
        {"input_type": "choice", "choice_id": "choice_3", "user_text": None},
        {"input_type": "choice", "choice_id": "choice_1", "user_text": None},
    ]

    final_response = None
    for turn_request in turn_requests:
        final_response = client.post(
            f"/v1/stories/{story_id}/turns",
            json={"device_id": device_id, **turn_request},
        )

    assert final_response is not None
    assert final_response.status_code == 200
    response_body = final_response.json()
    state = response_body["state"]
    assert state["turn_count"] == 6
    assert state["current_chapter_index"] == 2
    assert state["current_scene_index"] == 1
    assert state["active_goal"] == "追查试炼台后显露的真正威胁"
    assert state["flags"]["chapter_1_completed"] is True
    assert state["flags"]["chapter_1_completed_at_turn"] == 6
    assert state["flags"]["last_completed_chapter_index"] == 1
    assert response_body["chapter_progress"] == {
        "current_chapter_index": 2,
        "current_scene_index": 1,
        "progress_percent": 11,
    }
    assert response_body["warnings"] == ["chapter_completed:1"]

    resume_response = client.get(f"/v1/stories/{story_id}")
    latest_turn = resume_response.json()["latest_turns"][-1]
    assert latest_turn["chapter_completed"] is True
    assert latest_turn["completed_chapter_index"] == 1
    assert latest_turn["warnings"] == ["chapter_completed:1"]


def test_play_choice_turn_rejects_invalid_choice_id() -> None:
    clear_stories()
    client = TestClient(create_app())
    device_id = str(uuid4())
    story_id = client.post(
        "/v1/stories",
        json=_create_story_payload(device_id=device_id),
    ).json()["story_id"]

    response = client.post(
        f"/v1/stories/{story_id}/turns",
        json={
            "device_id": device_id,
            "input_type": "choice",
            "choice_id": "missing_choice",
            "user_text": None,
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "invalid_choice",
        "message": "Choice was not available for this story.",
        "details": {"choice_id": "missing_choice"},
    }
