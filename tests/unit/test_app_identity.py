"""Application identity invariants."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import openrouter_video.app_identity as identity_module
from openrouter_video.app_identity import (
    APP_CATEGORIES,
    APP_REFERER_STATUS,
    APP_TITLE,
    AppIdentity,
)


def test_identity_is_immutable_and_contains_only_project_metadata() -> None:
    identity = AppIdentity(
        referer="https://example.invalid/openrouter-video-test",
        title=APP_TITLE,
        categories=APP_CATEGORIES,
    )

    with pytest.raises(FrozenInstanceError):
        identity.title = "changed"  # type: ignore[misc]

    assert tuple(identity.__slots__) == ("referer", "title", "categories")
    assert APP_TITLE == "OpenRouter Video for ComfyUI"
    assert APP_CATEGORIES == ("video-gen",)


def test_production_referer_is_explicitly_unresolved() -> None:
    assert APP_REFERER_STATUS == "UNRESOLVED_RELEASE_IDENTITY"
    assert not hasattr(identity_module, "OFFICIAL_APP_IDENTITY")
    source = Path(identity_module.__file__).read_text(encoding="utf-8")
    assert "github.com/consumerexperience" not in source
    assert "example.invalid" not in source
