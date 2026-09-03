"""Independent application-identity fixtures for contract tests."""

from openrouter_video.app_identity import APP_CATEGORIES, APP_TITLE, AppIdentity

TEST_APP_IDENTITY = AppIdentity(
    referer="https://example.invalid/openrouter-video-test",
    title=APP_TITLE,
    categories=APP_CATEGORIES,
)

EXPECTED_RELEASE_IDENTITY = AppIdentity(
    referer="https://github.com/consumerexperience/ComfyUI-OpenRouter-Video",
    title="OpenRouter Video for ComfyUI",
    categories=("video-gen",),
)

__all__ = ("EXPECTED_RELEASE_IDENTITY", "TEST_APP_IDENTITY")
