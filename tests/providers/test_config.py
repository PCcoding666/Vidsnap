"""Configuration security and bounded-concurrency behavior."""

import pytest

from vidsnap.config import DASHSCOPE_ASR_BASE_URL, TOKEN_PLAN_BASE_URL, HarnessConfig


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


def test_asr_endpoint_is_a_fixed_public_dashscope_constant_apart_from_token_plan() -> None:
    assert DASHSCOPE_ASR_BASE_URL == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert DASHSCOPE_ASR_BASE_URL != TOKEN_PLAN_BASE_URL


def test_text_model_endpoint_stays_pinned_to_token_plan() -> None:
    with pytest.raises(ValueError, match="Token Plan"):
        HarnessConfig(base_url=DASHSCOPE_ASR_BASE_URL)
    with pytest.raises(ValueError, match="Token Plan"):
        HarnessConfig(base_url="https://example.invalid/compatible-mode/v1")
    assert HarnessConfig().base_url == TOKEN_PLAN_BASE_URL


def test_asr_key_prefers_the_dedicated_variable_without_touching_the_text_key(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VIDSNAP_ASR_API_KEY", "asr-secret")
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", "rotated-secret")
    monkeypatch.setenv("QWEN_API_KEY", "fallback-secret")

    config = HarnessConfig.from_env()

    assert config.resolved_asr_api_key == "asr-secret"
    assert config.api_key == "rotated-secret"
    assert config.base_url == TOKEN_PLAN_BASE_URL
    for secret in ("asr-secret", "rotated-secret", "fallback-secret"):
        assert secret not in repr(config)


@pytest.mark.parametrize(
    ("vidsnap_key", "qwen_key", "expected"),
    [
        ("rotated-secret", "fallback-secret", "rotated-secret"),
        (None, "fallback-secret", "fallback-secret"),
        ("", "fallback-secret", "fallback-secret"),
        (None, None, None),
    ],
)
def test_asr_key_falls_back_to_the_text_key_names_in_order(
    monkeypatch, vidsnap_key: str | None, qwen_key: str | None, expected: str | None
) -> None:
    monkeypatch.delenv("VIDSNAP_ASR_API_KEY", raising=False)
    for name, value in (("VIDSNAP_QWEN_API_KEY", vidsnap_key), ("QWEN_API_KEY", qwen_key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    assert HarnessConfig.from_env().resolved_asr_api_key == expected


def test_empty_asr_variable_counts_as_unset(monkeypatch) -> None:
    monkeypatch.setenv("VIDSNAP_ASR_API_KEY", "")
    monkeypatch.setenv("VIDSNAP_QWEN_API_KEY", "rotated-secret")

    assert HarnessConfig.from_env().resolved_asr_api_key == "rotated-secret"


def test_directly_built_config_resolves_the_asr_key_the_same_way() -> None:
    assert HarnessConfig(api_key="text-only").resolved_asr_api_key == "text-only"
    assert HarnessConfig(api_key="text", asr_api_key="asr").resolved_asr_api_key == "asr"
    assert HarnessConfig(api_key=None).resolved_asr_api_key is None
