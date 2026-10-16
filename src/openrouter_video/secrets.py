"""Credential resolution isolated from workflows and application identity."""

from __future__ import annotations

import os
import threading
from typing import Final, Protocol

from openrouter_video.errors import RequestPolicyError

_OPENROUTER_API_KEY: Final = "OPENROUTER_API_KEY"


class SecretProvider(Protocol):
    """Resolve the user-owned OpenRouter credential when a request is prepared."""

    def get_openrouter_api_key(self) -> str:
        """Return the current credential or fail locally."""


class EnvironmentSecretProvider:
    """Resolve the environment credential, then the process-local interactive credential."""

    __slots__ = ()

    def get_openrouter_api_key(self) -> str:
        """Resolve ``OPENROUTER_API_KEY`` before the session-only interactive value."""

        value = os.environ.get(_OPENROUTER_API_KEY)
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = interactive_credential_store.get()
        if value is None:
            raise RequestPolicyError("OpenRouter API credential is not configured")
        return value


class InteractiveCredentialStore:
    """Hold one user credential in process memory; never persist or expose its value."""

    __slots__ = ("_lock", "_value")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._value: str | None = None

    def get(self) -> str | None:
        with self._lock:
            return self._value

    def set(self, value: str) -> None:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.strip()) > 512
            or any(ord(character) < 32 or ord(character) == 127 for character in value.strip())
        ):
            raise RequestPolicyError("OpenRouter API credential is not configured")
        with self._lock:
            self._value = value.strip()

    def clear(self) -> None:
        with self._lock:
            self._value = None


interactive_credential_store = InteractiveCredentialStore()


def set_interactive_openrouter_api_key(value: str) -> None:
    interactive_credential_store.set(value)


def clear_interactive_openrouter_api_key() -> None:
    interactive_credential_store.clear()


def interactive_openrouter_api_key() -> str | None:
    return interactive_credential_store.get()


def openrouter_credential_source() -> str:
    """Return a non-sensitive source label for the effective credential."""

    try:
        value = os.environ.get(_OPENROUTER_API_KEY)
    except Exception:
        return "NONE"
    if isinstance(value, str) and value.strip():
        return "ENVIRONMENT"
    return "INTERACTIVE" if interactive_credential_store.get() is not None else "NONE"


def openrouter_credential_state() -> str:
    """Return only whether this process has a non-empty credential value."""

    return "PRESENT" if openrouter_credential_source() != "NONE" else "MISSING"


__all__ = (
    "EnvironmentSecretProvider",
    "InteractiveCredentialStore",
    "SecretProvider",
    "clear_interactive_openrouter_api_key",
    "interactive_credential_store",
    "interactive_openrouter_api_key",
    "openrouter_credential_source",
    "openrouter_credential_state",
    "set_interactive_openrouter_api_key",
)
