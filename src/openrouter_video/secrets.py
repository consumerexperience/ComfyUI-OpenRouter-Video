"""Credential resolution isolated from workflows and application identity."""

from __future__ import annotations

import os
from typing import Final, Protocol

from openrouter_video.errors import RequestPolicyError

_OPENROUTER_API_KEY: Final = "OPENROUTER_API_KEY"


class SecretProvider(Protocol):
    """Resolve the user-owned OpenRouter credential when a request is prepared."""

    def get_openrouter_api_key(self) -> str:
        """Return the current credential or fail locally."""


class EnvironmentSecretProvider:
    """Read exactly one named credential without retaining it as object state."""

    __slots__ = ()

    def get_openrouter_api_key(self) -> str:
        """Resolve ``OPENROUTER_API_KEY`` without enumerating the environment."""

        value = os.environ.get(_OPENROUTER_API_KEY)
        if value is None or not value.strip():
            raise RequestPolicyError("OpenRouter API credential is not configured")
        return value.strip()


__all__ = ("EnvironmentSecretProvider", "SecretProvider")
