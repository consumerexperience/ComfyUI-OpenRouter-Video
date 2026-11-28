"""Reviewed native limits are enforced before encoding, without weakening caps."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from openrouter_video.capabilities import RequestValidator
from openrouter_video.local_media import MAX_OBJECT_BYTES, LocalMedia, NativeMediaError
from openrouter_video.models import (
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
)
from tests.unit.test_full_catalogue_coverage import model, witness


def test_reviewed_source_limit_is_deferred_and_does_not_mutate_input(tmp_path: Path) -> None:
    writes: list[Path] = []
    media = LocalMedia("video/mp4", ".mp4", writes.append, duration=lambda: 16)
    source = InputReference(InputReferenceKind.VIDEO, local_media=media)
    m = model("black-forest-labs/flux-video-edit")
    request = replace(witness(m, InferenceMethod.V2V_EDIT), source_video=source)
    bound = RequestValidator().prepare_native_media(request, m)
    assert writes == []
    assert media.max_duration_seconds is None
    assert bound.source_video is not None
    constrained = bound.source_video.local_media
    assert constrained is not None
    assert constrained.max_duration_seconds == 15
    assert constrained.max_bytes == 50 * 1024 * 1024
    with pytest.raises(NativeMediaError, match="duration limit"):
        constrained.encode(tmp_path / "unused.mp4")
    assert writes == []


@pytest.mark.parametrize("duration", [None, lambda: float("nan"), lambda: 0, lambda: 4])
def test_unknown_or_invalid_duration_never_calls_encoder(
    tmp_path: Path, duration: Callable[[], float] | None
) -> None:
    writes: list[Path] = []
    media = LocalMedia("video/mp4", ".mp4", writes.append, duration, 3)
    with pytest.raises(NativeMediaError):
        media.encode(tmp_path / "unused.mp4")
    assert writes == []


def test_valid_boundary_duration_and_size(tmp_path: Path) -> None:
    def write(path: Path) -> None:
        path.write_bytes(b"123")

    media = LocalMedia("video/mp4", ".mp4", write, lambda: 3, 3, 3)
    assert media.encode(tmp_path / "ok.mp4") == 3
    with pytest.raises(NativeMediaError, match="object limit"):
        replace(media, max_bytes=2).encode(tmp_path / "large.mp4")
    assert LocalMedia.__dataclass_fields__["max_bytes"].default == MAX_OBJECT_BYTES


@pytest.mark.parametrize(("duration", "expected_limit"), [(10, 20), (3, 27), (None, 20)])
def test_extension_reserves_output_within_thirty_second_total(
    duration: int | None, expected_limit: int, tmp_path: Path
) -> None:
    def write(path: Path) -> None:
        path.write_bytes(b"video")

    m = model("google/gemini-omni-1.2-flash")
    source = InputReference(
        InputReferenceKind.VIDEO,
        local_media=LocalMedia("video/mp4", ".mp4", write, lambda: expected_limit),
    )
    request = replace(
        witness(m, InferenceMethod.V2V_EXTEND), source_video=source, duration=duration
    )
    bound = RequestValidator().prepare_native_media(request, m)
    assert bound.source_video is not None and bound.source_video.local_media is not None
    media = bound.source_video.local_media
    assert media.max_duration_seconds == expected_limit
    assert media.encode(tmp_path / "boundary.mp4") == 5
    with pytest.raises(NativeMediaError, match="duration limit"):
        replace(media, duration=lambda: expected_limit + 0.01).encode(tmp_path / "unused.mp4")


@pytest.mark.parametrize("duration,valid", [(1.99, False), (2, True), (30, True), (30.01, False)])
def test_wan_reference_video_bounds_are_checked_before_encoding(
    duration: float, valid: bool, tmp_path: Path
) -> None:
    writes: list[Path] = []

    def write(path: Path) -> None:
        writes.append(path)
        path.write_bytes(b"video")

    original = LocalMedia("video/mp4", ".mp4", write, duration=lambda: duration)
    m = model("alibaba/wan-2.6")
    request = replace(
        witness(m, InferenceMethod.VR2V),
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, local_media=original),)
        ),
    )
    bound = RequestValidator().prepare_native_media(request, m)
    assert bound.input_references is not None
    media = bound.input_references.references[0].local_media
    assert (
        media is not None and media.min_duration_seconds == 2 and media.max_duration_seconds == 30
    )
    assert original.min_duration_seconds is None
    if valid:
        assert media.encode(tmp_path / "video.mp4") == 5
    else:
        with pytest.raises(NativeMediaError, match="duration limit"):
            media.encode(tmp_path / "unused.mp4")
        assert not writes
