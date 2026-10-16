"""Environment secret-provider behavior and leakage boundaries."""

from collections.abc import Generator

import pytest

from openrouter_video.errors import RequestPolicyError
from openrouter_video.secrets import (
    EnvironmentSecretProvider,
    clear_interactive_openrouter_api_key,
    openrouter_credential_source,
    set_interactive_openrouter_api_key,
)


@pytest.fixture(autouse=True)
def clear_interactive_credential() -> Generator[None, None, None]:
    clear_interactive_openrouter_api_key()
    yield
    clear_interactive_openrouter_api_key()


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


def test_interactive_credential_is_process_local_and_environment_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    set_interactive_openrouter_api_key("  SESSION_ONLY_KEY  ")
    assert EnvironmentSecretProvider().get_openrouter_api_key() == "SESSION_ONLY_KEY"
    assert openrouter_credential_source() == "INTERACTIVE"
    monkeypatch.setenv("OPENROUTER_API_KEY", "ENVIRONMENT_KEY")
    assert EnvironmentSecretProvider().get_openrouter_api_key() == "ENVIRONMENT_KEY"
    assert openrouter_credential_source() == "ENVIRONMENT"
