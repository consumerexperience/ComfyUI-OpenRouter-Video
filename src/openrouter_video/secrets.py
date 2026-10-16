"""Credential resolution isolated from workflows and application identity."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final, Protocol

from openrouter_video.credential_backend import ACCOUNT, SERVICE, CredentialBackend, secure_backend
from openrouter_video.errors import RequestPolicyError

_OPENROUTER_API_KEY: Final = "OPENROUTER_API_KEY"
_pending: ContextVar[str | None] = ContextVar("openrouter_pending_credential", default=None)


def _validated(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value.strip()) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in value.strip())
    ):
        raise RequestPolicyError("OpenRouter API credential is not configured")
    return value.strip()


class SecretProvider(Protocol):
    """Resolve the user-owned OpenRouter credential when a request is prepared."""

    def get_openrouter_api_key(self) -> str:
        """Return the current credential or fail locally."""


class InteractiveCredentialStore:
    """One OS-vault credential plus an explicit process-only fallback.

    OS stores protect data at rest under the signed-in OS account. They do not
    isolate a key from malicious code already running as that same account.
    Lookup is lazy and cached; importing a custom node never opens the vault.
    """

    def __init__(self, factory: Callable[[], CredentialBackend] = secure_backend) -> None:
        self._lock = threading.RLock()
        self._factory = factory
        self._backend: CredentialBackend | None = None
        self._loaded = False
        self._persistent: str | None = None
        self._session: str | None = None
        self._attention = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            backend = self._factory()
            value = backend.get_password(SERVICE, ACCOUNT)
            self._backend = backend
            self._persistent = _validated(value) if value is not None else None
        except Exception:
            self._attention = True
            self._persistent = None

    def get(self) -> str | None:
        with self._lock:
            self._load()
            return self._persistent or self._session

    def status(self) -> tuple[bool, bool]:
        with self._lock:
            self._load()
            return self._persistent is not None, self._attention

    def set(self, value: str) -> None:
        value = _validated(value)
        with self._lock:
            self._load()
            try:
                backend = self._backend or self._factory()
                backend.get_password(SERVICE, ACCOUNT)
                self._backend = backend
                backend.set_password(SERVICE, ACCOUNT, value)
                if backend.get_password(SERVICE, ACCOUNT) != value:
                    raise RuntimeError("Credential replacement could not be verified")
            except Exception:
                # A failed write may have changed the vault. Never silently leave
                # an older credential active underneath a session replacement.
                if self._backend is not None:
                    try:
                        if self._backend.get_password(SERVICE, ACCOUNT) is not None:
                            self._backend.delete_password(SERVICE, ACCOUNT)
                        if self._backend.get_password(SERVICE, ACCOUNT) is not None:
                            raise RuntimeError("Credential removal could not be verified")
                    except Exception:
                        self._persistent = None
                        self._session = None
                        self._attention = True
                        raise RequestPolicyError(
                            "OpenRouter connection needs attention. Reconnect to continue."
                        ) from None
                self._persistent = None
                self._session = value
                self._attention = False
            else:
                self._backend = backend
                self._persistent = value
                self._session = None
                self._attention = False

    def clear(self) -> None:
        with self._lock:
            self._load()
            had_session = self._session is not None
            self._persistent = None
            self._session = None
            try:
                if self._backend is not None:
                    if self._backend.get_password(SERVICE, ACCOUNT) is not None:
                        self._backend.delete_password(SERVICE, ACCOUNT)
                    if self._backend.get_password(SERVICE, ACCOUNT) is not None:
                        raise RuntimeError("Credential removal could not be verified")
                elif self._attention and not had_session:
                    raise RuntimeError("Credential store could not be accessed")
            except Exception:
                self._attention = True
                raise RequestPolicyError(
                    "OpenRouter connection needs attention. Stored connection could not be removed."
                ) from None
            self._attention = False


interactive_credential_store = InteractiveCredentialStore()


class EnvironmentSecretProvider:
    """Resolve environment > secure persistent > session-only > none."""

    __slots__ = ()

    def get_openrouter_api_key(self) -> str:
        value = os.environ.get(_OPENROUTER_API_KEY)
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = _pending.get() or interactive_credential_store.get()
        if value is None:
            raise RequestPolicyError("OpenRouter API credential is not configured")
        return value


@contextmanager
def pending_interactive_credential(value: str) -> Iterator[None]:
    """Validate a proposed key in this request without activating or persisting it."""

    token = _pending.set(_validated(value))
    try:
        yield
    finally:
        _pending.reset(token)


def set_interactive_openrouter_api_key(value: str) -> None:
    interactive_credential_store.set(value)


def clear_interactive_openrouter_api_key() -> None:
    interactive_credential_store.clear()


def interactive_openrouter_api_key() -> str | None:
    return interactive_credential_store.get()


def openrouter_credential_source() -> str:
    value = os.environ.get(_OPENROUTER_API_KEY)
    if isinstance(value, str) and value.strip():
        return "ENVIRONMENT"
    return "INTERACTIVE" if interactive_credential_store.get() is not None else "NONE"


def interactive_credential_status() -> tuple[bool, bool]:
    return interactive_credential_store.status()


def openrouter_credential_state() -> str:
    return "PRESENT" if openrouter_credential_source() != "NONE" else "MISSING"


__all__ = (
    "EnvironmentSecretProvider",
    "InteractiveCredentialStore",
    "SecretProvider",
    "clear_interactive_openrouter_api_key",
    "interactive_credential_store",
    "interactive_credential_status",
    "interactive_openrouter_api_key",
    "openrouter_credential_source",
    "openrouter_credential_state",
    "pending_interactive_credential",
    "set_interactive_openrouter_api_key",
)
