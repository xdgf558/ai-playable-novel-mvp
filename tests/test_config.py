from app.core.config import Settings, get_settings
from app.db.session import get_database_url


def test_fake_mode_is_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LLM_FAKE_MODE", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_fake_mode is True
    assert settings.llm_provider == "fake"
    assert settings.llm_api_key in (None, "")


def test_openai_compatible_provider_settings_can_be_configured(monkeypatch) -> None:
    monkeypatch.setenv("LLM_FAKE_MODE", "false")
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv(
        "LLM_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setenv("LLM_API_KEY", "secret-key")
    monkeypatch.setenv("LLM_MODEL_FAST", "qwen-flash")
    monkeypatch.setenv("LLM_MODEL_QUALITY", "qwen-plus")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")

    settings = Settings()

    assert settings.llm_fake_mode is False
    assert settings.llm_provider == "qwen"
    assert settings.llm_base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    assert settings.llm_api_key == "secret-key"
    assert settings.llm_model_fast == "qwen-flash"
    assert settings.llm_model_quality == "qwen-plus"
    assert settings.llm_timeout_seconds == 45


def test_database_url_placeholder_is_available(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()

    try:
        assert get_database_url().startswith("sqlite:///")
    finally:
        get_settings.cache_clear()
