"""Unmistakably non-production application identity fixture."""

from openrouter_video.app_identity import APP_CATEGORIES, APP_TITLE, AppIdentity

TEST_APP_IDENTITY = AppIdentity(
    referer="https://example.invalid/openrouter-video-test",
    title=APP_TITLE,
    categories=APP_CATEGORIES,
)

__all__ = ("TEST_APP_IDENTITY",)
