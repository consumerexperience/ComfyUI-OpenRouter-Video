"""Synthetic vault tests: no owner credential access or external requests."""

from __future__ import annotations

import logging
import sys
import types

import pytest

from openrouter_video import secrets
from openrouter_video.credential_backend import ACCOUNT, SERVICE
from openrouter_video.errors import RequestPolicyError


class Vault:
    def __init__(self) -> None:
        self.value: str | None = None
        self.fail_read = False
        self.fail_write = False
        self.fail_delete = False

    def get_password(self, service: str, username: str) -> str | None:
        assert (service, username) == (SERVICE, ACCOUNT)
        if self.fail_read:
            raise RuntimeError("TEST_ONLY_SECRET_IN_BACKEND_ERROR")
        return self.value

    def set_password(self, service: str, username: str, password: str) -> None:
        assert (service, username) == (SERVICE, ACCOUNT)
        if self.fail_write:
            raise RuntimeError(password)
        self.value = password

    def delete_password(self, service: str, username: str) -> None:
        assert (service, username) == (SERVICE, ACCOUNT)
        if self.fail_delete:
            raise RuntimeError("TEST_ONLY_SECRET_IN_BACKEND_ERROR")
        self.value = None


@pytest.fixture
def vault(monkeypatch: pytest.MonkeyPatch) -> Vault:
    result = Vault()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        secrets, "interactive_credential_store", secrets.InteractiveCredentialStore(lambda: result)
    )
    return result


def test_save_restart_restore_and_shared_providers(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_PERSISTENT")
    assert vault.value == "TEST_ONLY_PERSISTENT"
    monkeypatch.setattr(
        secrets, "interactive_credential_store", secrets.InteractiveCredentialStore(lambda: vault)
    )
    assert secrets.openrouter_credential_source() == "INTERACTIVE"
    assert secrets.interactive_credential_status() == (True, False)
    # Each node's Generate/Resume runtime provider resolves through the same store.
    providers = [secrets.EnvironmentSecretProvider() for _ in range(4)]
    assert all(p.get_openrouter_api_key() == vault.value for p in providers)


def test_clean_install_and_environment_upgrade(
    vault: Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert secrets.openrouter_credential_state() == "MISSING"
    monkeypatch.setenv("OPENROUTER_API_KEY", "TEST_ONLY_ENV")
    assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_ENV"
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_PERSISTENT")
    assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_ENV"
    secrets.clear_interactive_openrouter_api_key()
    assert vault.value is None
    assert secrets.openrouter_credential_source() == "ENVIRONMENT"


def test_reconnect_replaces_and_disconnect_removes(vault: Vault) -> None:
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_OLD")
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_NEW")
    assert vault.value == "TEST_ONLY_NEW"
    secrets.clear_interactive_openrouter_api_key()
    assert vault.value is None
    assert secrets.openrouter_credential_source() == "NONE"


def test_unavailable_backend_session_fallback_and_disconnect(vault: Vault) -> None:
    vault.fail_write = True
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_SESSION")
    assert secrets.interactive_credential_status() == (False, False)
    assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_SESSION"
    secrets.clear_interactive_openrouter_api_key()
    assert secrets.openrouter_credential_source() == "NONE"


def test_unavailable_factory_is_session_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable() -> Vault:
        raise ImportError("No OS vault")

    store = secrets.InteractiveCredentialStore(unavailable)
    assert store.get() is None
    store.set("TEST_ONLY_SESSION")
    assert store.status() == (False, False)
    store.clear()
    assert store.get() is None


def test_corruption_lookup_and_failed_delete_are_sanitized(
    vault: Vault, caplog: pytest.LogCaptureFixture
) -> None:
    vault.value = "\x00TEST_ONLY_CORRUPT"
    assert secrets.openrouter_credential_source() == "NONE"
    assert secrets.interactive_credential_status() == (False, True)
    vault.fail_delete = True
    with caplog.at_level(logging.DEBUG), pytest.raises(RequestPolicyError) as caught:
        secrets.clear_interactive_openrouter_api_key()
    assert "TEST_ONLY" not in str(caught.value)
    assert "TEST_ONLY" not in caplog.text


def test_lookup_exception_never_crashes(vault: Vault) -> None:
    vault.fail_read = True
    assert secrets.openrouter_credential_state() == "MISSING"
    assert secrets.interactive_credential_status() == (False, True)


def test_replacement_write_failure_cannot_reactivate_old_key(vault: Vault) -> None:
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_OLD")
    vault.fail_write = True
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_NEW")
    assert vault.value is None
    assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_NEW"
    assert secrets.interactive_credential_status() == (False, False)


def test_failed_replacement_and_delete_do_not_report_success(vault: Vault) -> None:
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_OLD")
    vault.fail_write = vault.fail_delete = True
    with pytest.raises(RequestPolicyError):
        secrets.set_interactive_openrouter_api_key("TEST_ONLY_NEW")
    assert secrets.openrouter_credential_source() == "NONE"
    assert secrets.interactive_credential_status() == (False, True)


def test_validation_is_request_local_and_does_not_persist(vault: Vault) -> None:
    secrets.set_interactive_openrouter_api_key("TEST_ONLY_OLD")
    with secrets.pending_interactive_credential("TEST_ONLY_PROPOSED"):
        assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_PROPOSED"
        assert vault.value == "TEST_ONLY_OLD"
    assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_OLD"


def test_explicit_os_backend_ignores_keyring_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    import keyring

    from openrouter_video.credential_backend import secure_backend

    def forbidden() -> None:
        raise AssertionError("Automatic backend discovery is forbidden")

    monkeypatch.setattr(keyring, "get_keyring", forbidden)
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyrings.alt.file.PlaintextKeyring")
    monkeypatch.setenv("KEYRING_PROPERTY_injected_test_property", "FORBIDDEN_OVERRIDE")
    backend = secure_backend()
    assert not hasattr(backend, "injected_test_property")
    assert "keyrings.alt" not in type(backend).__module__


def test_linux_factory_constructs_same_backend_once_without_vault_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openrouter_video.credential_backend import secure_backend

    constructed: list[object] = []

    class SyntheticSecretService(Vault):
        def __init__(self) -> None:
            super().__init__()
            constructed.append(self)
            self.set_properties_from_env()

        def set_properties_from_env(self) -> None:
            raise AssertionError("Environment overrides must remain blocked")

        def get_password(self, service: str, username: str) -> str | None:
            raise AssertionError("Constructing the backend must not read the vault")

    module = types.ModuleType("keyring.backends.SecretService")
    monkeypatch.setattr(module, "Keyring", SyntheticSecretService, raising=False)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(sys, "platform", "linux")
    backend = secure_backend()
    assert isinstance(backend, SyntheticSecretService)
    assert constructed == [backend]
