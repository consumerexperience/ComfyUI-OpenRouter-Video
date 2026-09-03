"""Application identity invariants."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import openrouter_video.app_identity as identity_module
from openrouter_video.app_identity import (
    APP_CATEGORIES,
    APP_REFERER,
    APP_REFERER_STATUS,
    APP_TITLE,
    OFFICIAL_APP_IDENTITY,
    AppIdentity,
)
from tests.fixtures.identity import EXPECTED_RELEASE_IDENTITY


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


def test_production_identity_is_the_exact_frozen_release_identity() -> None:
    assert APP_REFERER == "https://github.com/consumerexperience/ComfyUI-OpenRouter-Video"
    assert APP_REFERER_STATUS == "FROZEN_RELEASE_IDENTITY"
    assert OFFICIAL_APP_IDENTITY == EXPECTED_RELEASE_IDENTITY
    assert OFFICIAL_APP_IDENTITY is identity_module.OFFICIAL_APP_IDENTITY
    source = Path(identity_module.__file__).read_text(encoding="utf-8")
    assert "example.invalid" not in source
    assert not any(token in source for token in ("getenv(", "environ[", "environ.get("))


def test_official_identity_has_no_runtime_or_subject_identity_fields() -> None:
    assert tuple(OFFICIAL_APP_IDENTITY.__slots__) == ("referer", "title", "categories")
    assert not any(
        token in OFFICIAL_APP_IDENTITY.referer.lower()
        for token in ("user", "device", "install", "workflow", "session")
    )
