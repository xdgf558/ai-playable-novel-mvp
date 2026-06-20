import pytest

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolate_llm_settings_from_local_env(monkeypatch):
    monkeypatch.setenv("LLM_FAKE_MODE", "true")
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_MODEL_FAST", "fake-fast")
    monkeypatch.setenv("LLM_MODEL_QUALITY", "fake-quality")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "60")
    get_settings.cache_clear()

    try:
        yield
    finally:
        get_settings.cache_clear()
