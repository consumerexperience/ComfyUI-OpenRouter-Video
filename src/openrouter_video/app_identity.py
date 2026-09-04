"""Static application identity for the OpenRouter request boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

APP_TITLE: Final = "OpenRouter Video for ComfyUI"
APP_CATEGORIES: Final = ("video-gen",)
APP_REFERER: Final = "https://github.com/consumerexperience/ComfyUI-OpenRouter-Video"
APP_REFERER_STATUS: Final = "FROZEN_RELEASE_IDENTITY"


@dataclass(frozen=True, slots=True)
class AppIdentity:
    """Public project metadata applied identically to OpenRouter requests."""

    referer: str
    title: str
    categories: tuple[str, ...]


OFFICIAL_APP_IDENTITY: Final = AppIdentity(
    referer=APP_REFERER,
    title=APP_TITLE,
    categories=APP_CATEGORIES,
)


__all__ = (
    "APP_CATEGORIES",
    "APP_REFERER",
    "APP_REFERER_STATUS",
    "APP_TITLE",
    "AppIdentity",
    "OFFICIAL_APP_IDENTITY",
)
