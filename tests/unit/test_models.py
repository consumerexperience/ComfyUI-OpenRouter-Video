from __future__ import annotations

from dataclasses import replace

from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    request_fingerprint_v1,
)


def test_request_fingerprint_is_versioned_and_deterministic() -> None:
    request = GenerationRequest(model="vendor/model", prompt="private prompt", duration=8)

    assert request_fingerprint_v1(request) == request_fingerprint_v1(request)
    assert request_fingerprint_v1(request).startswith("v1:")
    assert len(request_fingerprint_v1(request)) == 67


def test_request_fingerprint_excludes_sensitive_values_and_operation_identity() -> None:
    first = GenerationRequest(
        model="vendor/model",
        prompt="PRIVATE_PROMPT_A",
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/A.png"),
    )
    second = replace(
        first,
        prompt="PRIVATE_PROMPT_B",
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/B.png"),
    )

    assert request_fingerprint_v1(first) == request_fingerprint_v1(second)


def test_request_fingerprint_changes_for_each_non_sensitive_shape_dimension() -> None:
    base = GenerationRequest(model="vendor/model", prompt="prompt")
    variants = (
        replace(base, model="vendor/other"),
        replace(base, duration=5),
        replace(base, resolution="720p"),
        replace(base, aspect_ratio="16:9"),
        replace(base, size="1280x720"),
        replace(base, seed=7),
        replace(base, generate_audio=True),
        replace(
            base,
            first_frame=FrameReference(FrameType.FIRST, "https://assets.example/a.png"),
        ),
        replace(
            base,
            last_frame=FrameReference(FrameType.LAST, "https://assets.example/z.png"),
        ),
    )

    assert len({request_fingerprint_v1(base), *(request_fingerprint_v1(v) for v in variants)}) == 10


def test_generation_request_emits_only_frozen_v01_fields() -> None:
    request = GenerationRequest(
        model="vendor/model",
        prompt="prompt",
        duration=5,
        generate_audio=True,
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/a.png"),
    )

    assert request.to_openrouter_payload() == {
        "model": "vendor/model",
        "prompt": "prompt",
        "duration": 5,
        "generate_audio": True,
        "frame_images": [{"frame_type": "first_frame", "url": "https://assets.example/a.png"}],
    }
