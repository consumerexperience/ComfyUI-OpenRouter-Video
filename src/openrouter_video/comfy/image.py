"""Bounded native Comfy IMAGE to OpenRouter image data-URL bridge."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from openrouter_video.image_transport import (
    MAX_IMAGE_PIXELS,
    MAX_PNG_BYTES,
    PNG_DATA_PREFIX,
)


class ImageBridgeError(ValueError):
    """Sanitized native image conversion failure."""


def to_image_data_url(value: Any) -> str:
    """Encode one Comfy BHWC float IMAGE as a bounded, deterministic PNG."""

    shape = getattr(value, "shape", None)
    if shape is None or len(shape) != 4 or shape[0] != 1 or shape[3] not in (3, 4):
        raise ImageBridgeError("IMAGE_INPUT_INVALID: expected one RGB or RGBA image.")
    height, width = int(shape[1]), int(shape[2])
    if height < 1 or width < 1 or height * width > MAX_IMAGE_PIXELS:
        raise ImageBridgeError("IMAGE_INPUT_LIMIT: image dimensions exceed the local limit.")
    try:
        import numpy as np  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]

        pixels = value[0].detach().cpu().numpy()
        if not bool(np.isfinite(pixels).all()):
            raise ImageBridgeError("IMAGE_INPUT_INVALID: image contains non-finite pixels.")
        pixels = (np.clip(pixels, 0, 1) * 255).astype("uint8")
        image = Image.fromarray(pixels, mode="RGB" if shape[3] == 3 else "RGBA")
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=False)
        binary = buffer.getvalue()
    except ImageBridgeError:
        raise
    except (AttributeError, ImportError, TypeError, ValueError, RuntimeError, OSError):
        raise ImageBridgeError("IMAGE_INPUT_INVALID: native image could not be encoded.") from None
    if not binary or len(binary) > MAX_PNG_BYTES:
        raise ImageBridgeError("IMAGE_INPUT_LIMIT: encoded image exceeds the local limit.")
    return PNG_DATA_PREFIX + base64.b64encode(binary).decode("ascii")


__all__ = ("ImageBridgeError", "MAX_IMAGE_PIXELS", "MAX_PNG_BYTES", "to_image_data_url")
