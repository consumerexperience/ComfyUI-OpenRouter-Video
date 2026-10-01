"""No-network host-runtime probe for the real Comfy IMAGE encoder and socket union."""

from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path

_REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPOSITORY / "src"))
sys.path.insert(0, str(_REPOSITORY.parent / "dev" / "ComfyUI-DEV"))

import torch  # noqa: E402
from comfy_execution.validation import validate_node_input  # noqa: E402
from PIL import Image  # noqa: E402

from openrouter_video.comfy.image import ImageBridgeError, to_image_data_url  # noqa: E402
from openrouter_video.image_transport import (  # noqa: E402
    PNG_DATA_PREFIX,
    is_supported_image_data_url,
)


def main() -> None:
    native = torch.tensor(
        [[[[0.0, 0.5, 1.0], [1.0, 0.5, 0.0]], [[0.25, 0.25, 0.25], [0.75, 0.75, 0.75]]]],
        dtype=torch.float32,
    )
    source = to_image_data_url(native)
    assert source.startswith(PNG_DATA_PREFIX)
    assert source == to_image_data_url(native)
    assert is_supported_image_data_url(source)
    decoded = Image.open(BytesIO(base64.b64decode(source[len(PNG_DATA_PREFIX) :])))
    decoded.load()
    assert decoded.format == "PNG" and decoded.size == (2, 2)
    assert validate_node_input("IMAGE", "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE")
    assert validate_node_input(
        "OPENROUTER_VIDEO_INPUT_REFERENCE", "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE"
    )
    assert not validate_node_input("VIDEO", "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE")
    try:
        to_image_data_url(torch.zeros((2, 2, 2, 3)))
    except ImageBridgeError as exc:
        assert "data:" not in str(exc)
    else:
        raise AssertionError("batch greater than one must fail")


if __name__ == "__main__":
    main()
