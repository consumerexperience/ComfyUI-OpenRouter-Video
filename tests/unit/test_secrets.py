"""Environment secret-provider behavior and leakage boundaries."""

import pytest

from openrouter_video.errors import RequestPolicyError
from openrouter_video.secrets import EnvironmentSecretProvider


def test_environment_provider_reads_only_explicit_present_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "  TEST_ONLY_OPENROUTER_KEY_CANARY  ")
    provider = EnvironmentSecretProvider()

    assert provider.get_openrouter_api_key() == "TEST_ONLY_OPENROUTER_KEY_CANARY"
    assert "TEST_ONLY_OPENROUTER_KEY_CANARY" not in repr(provider)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_empty_key_fails_locally(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENROUTER_API_KEY", value)

    with pytest.raises(RequestPolicyError) as caught:
        EnvironmentSecretProvider().get_openrouter_api_key()

    assert str(caught.value) == "OpenRouter API credential is not configured"
    if value:
        assert value not in str(caught.value)
