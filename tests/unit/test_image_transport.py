"""IMAGE-only data URL validation without network or paid operations."""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator
from openrouter_video.errors import ProductFailureError
from openrouter_video.image_transport import PNG_DATA_PREFIX, is_supported_image_data_url
from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
)


def _png_data_url() -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    image = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x80\x40\x20"))
        + chunk(b"IEND", b"")
    )
    return PNG_DATA_PREFIX + base64.b64encode(image).decode("ascii")


def test_png_data_url_is_bounded_and_image_only() -> None:
    source = _png_data_url()
    assert is_supported_image_data_url(source)
    assert base64.b64decode(source.removeprefix(PNG_DATA_PREFIX)).startswith(b"\x89PNG")
    assert not is_supported_image_data_url(source + "not-base64")
    assert not is_supported_image_data_url("data:image/jpeg;base64," + source.split(",", 1)[1])
    assert not is_supported_image_data_url("data:video/mp4;base64," + source.split(",", 1)[1])


def test_data_url_keeps_frame_and_ordered_reference_semantics() -> None:
    source = _png_data_url()
    validator = RequestValidator()
    first = GenerationRequest(
        "vendor/model",
        "prompt",
        InferenceMethod.I2V,
        first_frame=FrameReference(FrameType.FIRST, source),
    )
    validator.validate_shape(first)
    assert (
        cast(list[dict[str, Any]], first.to_openrouter_payload()["frame_images"])[0]["image_url"][
            "url"
        ]
        == source
    )
    assert (
        cast(list[dict[str, Any]], first.to_openrouter_payload()["frame_images"])[0]["frame_type"]
        == "first_frame"
    )

    references = (InputReference(InputReferenceKind.IMAGE, source),) * 2
    request = GenerationRequest(
        "vendor/model",
        "prompt",
        InferenceMethod.MI2V,
        input_references=InputReferenceCollection(references),
    )
    validator.validate_shape(request)
    assert request.to_openrouter_payload()["input_references"] == [
        {"type": "image_url", "image_url": {"url": source}},
        {"type": "image_url", "image_url": {"url": source}},
    ]
    assert "inference_method" not in request.to_openrouter_payload()


def test_https_remains_valid_but_video_data_url_fails_without_leaking_payload() -> None:
    validator = RequestValidator()
    https = GenerationRequest(
        "vendor/model",
        "prompt",
        InferenceMethod.IR2V,
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.IMAGE, "https://assets.example/image.png"),)
        ),
    )
    validator.validate_shape(https)
    assert (
        cast(list[dict[str, Any]], https.to_openrouter_payload()["input_references"])[0][
            "image_url"
        ]["url"]
        == "https://assets.example/image.png"
    )

    source = _png_data_url()
    video = GenerationRequest(
        "vendor/model",
        "prompt",
        InferenceMethod.VR2V,
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, source),)
        ),
    )
    with pytest.raises(ProductFailureError) as caught:
        validator.validate_shape(video)
    assert source not in str(caught.value)
