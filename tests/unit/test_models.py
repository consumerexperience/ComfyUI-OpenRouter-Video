from __future__ import annotations

from dataclasses import replace

from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    request_fingerprint_v1,
    request_fingerprint_v2,
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


def test_generation_request_emits_typed_frame_protocol() -> None:
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
        "frame_images": [
            {
                "type": "image_url",
                "image_url": {"url": "https://assets.example/a.png"},
                "frame_type": "first_frame",
            }
        ],
    }


def test_first_plus_last_frame_payload_preserves_temporal_order() -> None:
    request = GenerationRequest(
        "vendor/model",
        "prompt",
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/first.png"),
        last_frame=FrameReference(FrameType.LAST, "https://assets.example/last.png"),
    )

    assert request.to_openrouter_payload()["frame_images"] == [
        {
            "type": "image_url",
            "image_url": {"url": "https://assets.example/first.png"},
            "frame_type": "first_frame",
        },
        {
            "type": "image_url",
            "image_url": {"url": "https://assets.example/last.png"},
            "frame_type": "last_frame",
        },
    ]


def test_input_reference_payload_preserves_order_and_duplicate_occurrences() -> None:
    request = GenerationRequest(
        model="vendor/model",
        prompt="prompt",
        input_references=InputReferenceCollection(
            (
                InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png"),
                InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png"),
                InputReference(InputReferenceKind.VIDEO, "https://assets.example/b.mp4"),
            )
        ),
    )

    assert request.to_openrouter_payload()["input_references"] == [
        {"type": "image_url", "image_url": {"url": "https://assets.example/a.png"}},
        {"type": "image_url", "image_url": {"url": "https://assets.example/a.png"}},
        {"type": "video_url", "video_url": {"url": "https://assets.example/b.mp4"}},
    ]


def test_request_fingerprint_v2_is_structural_ordered_and_secret_free() -> None:
    ordered_references = (
        InputReference(InputReferenceKind.IMAGE, "https://secret.example/a.png"),
        InputReference(InputReferenceKind.VIDEO, "https://secret.example/b.mp4"),
    )
    first = GenerationRequest(
        "vendor/model",
        "PRIVATE_PROMPT_A",
        input_references=InputReferenceCollection(ordered_references),
    )
    same_shape = replace(
        first,
        prompt="PRIVATE_PROMPT_B",
        input_references=InputReferenceCollection(
            (
                InputReference(InputReferenceKind.IMAGE, "https://other.example/a.png"),
                InputReference(InputReferenceKind.VIDEO, "https://other.example/b.mp4"),
            )
        ),
    )
    reordered = replace(
        first,
        input_references=InputReferenceCollection(tuple(reversed(ordered_references))),
    )

    fingerprint = request_fingerprint_v2(first)
    assert fingerprint == request_fingerprint_v2(same_shape)
    assert fingerprint != request_fingerprint_v2(reordered)
    assert fingerprint.startswith("v2:") and len(fingerprint) == 67
    assert "PRIVATE" not in fingerprint and "https" not in fingerprint
    assert request_fingerprint_v2(replace(first, prompt=None)) != fingerprint
