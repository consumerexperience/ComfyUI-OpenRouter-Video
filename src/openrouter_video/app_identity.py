"""Static application identity for the OpenRouter request boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

APP_TITLE: Final = "OpenRouter Video for ComfyUI"
APP_CATEGORIES: Final = ("video-gen",)
APP_REFERER_STATUS: Final = "UNRESOLVED_RELEASE_IDENTITY"


@dataclass(frozen=True, slots=True)
class AppIdentity:
    """Public project metadata applied identically to OpenRouter requests."""

    referer: str
    title: str
    categories: tuple[str, ...]


__all__ = ("APP_CATEGORIES", "APP_REFERER_STATUS", "APP_TITLE", "AppIdentity")
