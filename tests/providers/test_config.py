"""Configuration security and bounded-concurrency behavior."""

from vidsnap.config import TOKEN_PLAN_BASE_URL, HarnessConfig


def test_config_prefers_vidsnap_key_and_caps_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", "rotated-secret")
    monkeypatch.setenv("QWEN_API_KEY", "fallback-secret")
    monkeypatch.setenv("VIDSNAP_MODEL_CONCURRENCY", "99")

    config = HarnessConfig.from_env()

    assert config.model == "qwen3.8-max"
    assert config.base_url == TOKEN_PLAN_BASE_URL
    assert config.model_concurrency == 2
    assert config.api_key == "rotated-secret"
    assert "rotated-secret" not in repr(config)


def test_config_uses_fallback_key_and_safe_default_concurrency(monkeypatch) -> None:
    monkeypatch.delenv("VIDSNAP_QWEN_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_API_KEY", "fallback-secret")
    monkeypatch.setenv("VIDSNAP_MODEL_CONCURRENCY", "not-an-integer")

    config = HarnessConfig.from_env()

    assert config.api_key == "fallback-secret"
    assert config.model_concurrency == 1
