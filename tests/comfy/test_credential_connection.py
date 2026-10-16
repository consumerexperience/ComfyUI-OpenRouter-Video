"""Connection handlers with synthetic vault and catalogue-only runtime."""

# mypy: disable-error-code="attr-defined"
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from openrouter_video import secrets
from openrouter_video.comfy import compat, routes
from openrouter_video.errors import RequestPolicyError


class Vault:
    value: str | None = None

    def get_password(self, service: str, username: str) -> str | None:
        return self.value

    def set_password(self, service: str, username: str, password: str) -> None:
        self.value = password

    def delete_password(self, service: str, username: str) -> None:
        self.value = None


@pytest.mark.parametrize("flow", ["manual", "oauth"])
def test_connect_persist_restart_catalogue_and_disconnect(
    monkeypatch: pytest.MonkeyPatch, flow: str, caplog: pytest.LogCaptureFixture
) -> None:
    vault = Vault()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        secrets, "interactive_credential_store", secrets.InteractiveCredentialStore(lambda: vault)
    )
    monkeypatch.setattr(compat, "json_response", lambda payload, *, status: (payload, status))
    calls: list[str] = []

    class Runtime:
        async def validate_connection(self) -> Any:
            calls.append("GET /videos/models")
            assert (
                secrets.EnvironmentSecretProvider().get_openrouter_api_key()
                == "TEST_ONLY_CONNECTION_CANARY"
            )
            return SimpleNamespace(models=(SimpleNamespace(model_id="test/model"),))

        catalog = validate_connection

    class Request:
        query = {"state": "test-state", "code": "test-code"}

        async def json(self) -> object:
            return {"api_key": "TEST_ONLY_CONNECTION_CANARY"}

    async def exchange(state: str, code: str) -> str:
        assert (state, code) == ("test-state", "test-code")
        return "TEST_ONLY_CONNECTION_CANARY"

    monkeypatch.setattr(routes, "get_runtime", Runtime)
    monkeypatch.setattr(routes, "exchange_pkce", exchange)
    handler = routes._connect_handler if flow == "manual" else routes._auth_callback_handler
    payload, status = asyncio.run(handler(Request()))
    assert status == 200 and payload["persistent"] is True
    assert vault.value == "TEST_ONLY_CONNECTION_CANARY"
    monkeypatch.setattr(
        secrets, "interactive_credential_store", secrets.InteractiveCredentialStore(lambda: vault)
    )
    restored, status = asyncio.run(routes._connection_handler(None))
    assert status == 200 and restored["state"] == "CONNECTED" and restored["persistent"]
    models, status = asyncio.run(routes._models_handler(None))
    assert status == 200 and "test/model" in models
    assert calls == ["GET /videos/models", "GET /videos/models"]
    # These are the only route products; no key can reach settings, receipt or UI state.
    evidence = json.dumps([payload, restored, models]) + caplog.text
    assert "TEST_ONLY_CONNECTION_CANARY" not in evidence
    disconnected, status = asyncio.run(routes._disconnect_handler(None))
    assert status == 200 and disconnected["state"] == "DISCONNECTED"
    assert vault.value is None


@pytest.mark.parametrize("flow", ["manual", "oauth"])
def test_failed_validation_keeps_existing_persistent_connection(
    monkeypatch: pytest.MonkeyPatch, flow: str
) -> None:
    vault = Vault()
    vault.value = "TEST_ONLY_OLD"
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        secrets, "interactive_credential_store", secrets.InteractiveCredentialStore(lambda: vault)
    )
    monkeypatch.setattr(compat, "json_response", lambda payload, *, status: (payload, status))

    class Runtime:
        async def validate_connection(self) -> Any:
            raise RequestPolicyError("Synthetic rejection")

    class Request:
        query = {"state": "state", "code": "code"}

        async def json(self) -> object:
            return {"api_key": "TEST_ONLY_NEW"}

    async def exchange(state: str, code: str) -> str:
        return "TEST_ONLY_NEW"

    monkeypatch.setattr(routes, "get_runtime", Runtime)
    monkeypatch.setattr(routes, "exchange_pkce", exchange)
    handler = routes._connect_handler if flow == "manual" else routes._auth_callback_handler
    payload, status = asyncio.run(handler(Request()))
    assert status >= 400
    assert vault.value == "TEST_ONLY_OLD"
    assert secrets.EnvironmentSecretProvider().get_openrouter_api_key() == "TEST_ONLY_OLD"
    assert "TEST_ONLY" not in json.dumps(payload)
