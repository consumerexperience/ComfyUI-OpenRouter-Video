"""Explicit OS credential backends; no discovery, plugins or file fallback."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Protocol

SERVICE = "OpenRouter Video for ComfyUI"
ACCOUNT = "interactive-api-access"


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


class _FixedProperties:
    """Do not apply KEYRING_PROPERTY_* overrides to the product OS backend."""

    def set_properties_from_env(self) -> None:
        pass


def secure_backend() -> CredentialBackend:
    """Never consult keyring config, environment overrides or third-party backends."""

    if sys.platform == "win32":
        from keyring.backends.Windows import WinVaultKeyring

        class WindowsVault(_FixedProperties, WinVaultKeyring):
            pass

        return WindowsVault()  # type: ignore[no-untyped-call]
    if sys.platform == "darwin":
        from keyring.backends.macOS import Keyring

        class MacVault(_FixedProperties, Keyring):
            pass

        return MacVault()
    if sys.platform == "linux":
        from keyring.backends.SecretService import Keyring as SecretServiceKeyring

        class LinuxVault(_FixedProperties, SecretServiceKeyring):
            pass

        linux_factory: Callable[[], CredentialBackend] = LinuxVault
        return linux_factory()
    raise RuntimeError("Secure credential storage is unavailable")
