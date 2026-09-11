"""Direct bridge from durable Core artifacts to native Comfy VIDEO."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openrouter_video.models import VideoArtifact

from . import compat


class VideoBridgeError(RuntimeError):
    """A durable Core artifact cannot be represented safely as native VIDEO."""


def to_native_video(artifact: VideoArtifact) -> Any:
    """Revalidate ownership/existence and return a file-backed native VIDEO."""

    root = compat.output_directory().resolve()
    try:
        path = Path(artifact.path).resolve(strict=True)
        path.relative_to(root)
        if not path.is_file() or artifact.media_type not in {"video/mp4", "video/webm"}:
            raise VideoBridgeError("Generated video artifact is unavailable.")
    except (OSError, ValueError):
        raise VideoBridgeError("Generated video artifact is unavailable.") from None
    return compat.video_from_file(path)


__all__ = ("VideoBridgeError", "to_native_video")
