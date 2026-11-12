"""Bounded local media metadata checks run only when staging encodes media."""

import base64
import struct
import zlib
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from openrouter_video.capabilities import RequestValidator
from openrouter_video.configuration import REQUEST_SHAPES_KEY, project_method, request_shape_profile
from openrouter_video.image_transport import image_data_url_metadata
from openrouter_video.local_media import LocalMedia, NativeMediaError
from openrouter_video.models import (
    FrameReference,
    FrameType,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
)
from tests.unit.test_full_catalogue_coverage import model, witness


def configured_model(
    mid: str, limits: dict[str, dict[str, int]], method: str = "VR2V"
) -> ModelCapabilities:
    base = model(mid)
    facts = []
    for fact in base.evidence_facts:
        if fact.key == REQUEST_SHAPES_KEY:
            profile = request_shape_profile(base)
            profile["methods"][method]["media_limits"] = limits
            fact = replace(fact, value=profile)
        facts.append(fact)
    return replace(base, evidence_facts=tuple(facts))


def _write_byte(path: Path) -> None:
    path.write_bytes(b"x")


def _write_labeled(path: Path, writes: list[str], label: str) -> None:
    writes.append(label)
    path.write_bytes(b"x")


def png_data_url(width: int, height: int, padding: int = 0) -> str:
    payload = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = b"\x00\x00\x00\rIHDR" + payload
    binary = b"\x89PNG\r\n\x1a\n" + ihdr + struct.pack(">I", zlib.crc32(ihdr[4:]))
    binary += bytes(padding)
    return "data:image/png;base64," + base64.b64encode(binary).decode("ascii")


def test_geometry_bounds_are_deferred_and_checked_before_write(tmp_path: Path) -> None:
    writes: list[Path] = []
    media = LocalMedia(
        "video/mp4",
        ".mp4",
        writes.append,
        geometry=lambda: (1920, 1080),
        max_width=1280,
    )
    assert writes == []
    with pytest.raises(NativeMediaError, match="geometry"):
        media.encode(tmp_path / "rejected.mp4")
    assert writes == []


def test_geometry_metadata_missing_fails_closed_when_bound(tmp_path: Path) -> None:
    media = LocalMedia("video/mp4", ".mp4", lambda path: None, max_pixels=100)
    with pytest.raises(NativeMediaError, match="could not be verified"):
        media.encode(tmp_path / "unknown.mp4")


def test_metadata_callbacks_returning_none_fail_closed(tmp_path: Path) -> None:
    writes: list[Path] = []
    duration = LocalMedia(
        "audio/wav",
        ".wav",
        writes.append,
        duration=cast(Callable[[], float], lambda: None),
        max_duration_seconds=4,
    )
    geometry = LocalMedia(
        "video/mp4",
        ".mp4",
        writes.append,
        geometry=cast(Callable[[], tuple[int, int]], lambda: None),
        max_width=1920,
    )
    with pytest.raises(NativeMediaError):
        duration.encode(tmp_path / "bad-duration.wav")
    with pytest.raises(NativeMediaError):
        geometry.encode(tmp_path / "bad-geometry.mp4")
    assert writes == []


def test_combined_duration_guard_runs_before_any_encoder(tmp_path: Path) -> None:
    writes: list[Path] = []
    media = LocalMedia(
        "audio/wav",
        ".wav",
        writes.append,
        combined_duration_check=lambda: (_ for _ in ()).throw(
            NativeMediaError("Combined reference duration exceeds the selected limit.")
        ),
    )
    with pytest.raises(NativeMediaError, match="Combined reference duration"):
        media.encode(tmp_path / "audio.wav")
    assert writes == []


def test_unconstrained_media_keeps_existing_deferred_behavior(tmp_path: Path) -> None:
    media = LocalMedia("video/mp4", ".mp4", _write_byte)
    assert media.encode(tmp_path / "ok.mp4") == 1
    assert replace(media).geometry is None


def test_image_metadata_helper_matches_existing_bounded_png_contract() -> None:
    assert image_data_url_metadata(png_data_url(640, 480)) == (33, 640, 480)
    assert image_data_url_metadata("https://example.com/image.png") is None


def test_combined_video_and_audio_budgets_are_independent_and_deferred(
    tmp_path: Path,
) -> None:
    m = configured_model(
        "alibaba/wan-2.6",
        {
            "video": {"max_combined_duration_seconds": 10},
            "audio": {"max_combined_duration_seconds": 7},
        },
    )
    writes: list[str] = []

    def source(kind: InputReferenceKind, seconds: float, label: str) -> InputReference:
        return InputReference(
            kind,
            local_media=LocalMedia(
                "video/mp4" if kind is InputReferenceKind.VIDEO else "audio/wav",
                ".mp4" if kind is InputReferenceKind.VIDEO else ".wav",
                lambda path: _write_labeled(path, writes, label),
                duration=lambda: seconds,
            ),
        )

    refs = InputReferenceCollection(
        (
            source(InputReferenceKind.VIDEO, 8, "v1"),
            source(InputReferenceKind.VIDEO, 3, "v2"),
            source(InputReferenceKind.AUDIO, 4, "a1"),
            source(InputReferenceKind.AUDIO, 3, "a2"),
        )
    )
    request = replace(witness(m, InferenceMethod.VR2V), input_references=refs)
    assert project_method(m, InferenceMethod.VR2V)["media_limits"] == {
        "video": {"max_combined_duration_seconds": 10},
        "audio": {"max_combined_duration_seconds": 7},
    }
    bound = RequestValidator().prepare_native_media(request, m)
    assert writes == []
    assert bound.input_references is not None
    video1, video2, audio1, _audio2 = bound.input_references.references
    assert video1.local_media is not None and video2.local_media is not None
    assert audio1.local_media is not None
    with pytest.raises(NativeMediaError, match="Combined reference duration"):
        video1.local_media.encode(tmp_path / "video.mp4")
    assert writes == []
    assert audio1.local_media.encode(tmp_path / "audio.wav") > 0
    assert writes == ["a1"]


def test_external_media_with_combined_budget_fails_closed_during_preparation() -> None:
    m = configured_model("alibaba/wan-2.6", {"video": {"max_combined_duration_seconds": 10}})
    request = replace(
        witness(m, InferenceMethod.VR2V),
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, "https://example.com/reference.mp4"),)
        ),
    )
    with pytest.raises(Exception, match="Combined reference duration"):
        RequestValidator().prepare_native_media(request, m)


@pytest.mark.parametrize(
    "limits",
    [
        {"video": {"max_duration_seconds": 5}},
        {"video": {"max_bytes": 100}},
        {"video": {"max_width": 100}},
    ],
)
def test_external_video_metadata_fails_closed_for_individual_bounds(
    limits: dict[str, dict[str, int]],
) -> None:
    m = configured_model("alibaba/wan-2.6", limits)
    request = replace(
        witness(m, InferenceMethod.VR2V),
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, "https://example.com/reference.mp4"),)
        ),
    )
    with pytest.raises(Exception, match="Media metadata cannot be verified"):
        RequestValidator().prepare_native_media(request, m)


def test_inline_png_image_size_and_geometry_limits_use_real_method_profile() -> None:
    m = configured_model(
        "google/gemini-omni-1.2-flash",
        {"image": {"max_width": 800, "max_bytes": 100}},
        "IR2V",
    )
    png = png_data_url(640, 480)
    request = replace(
        witness(m, InferenceMethod.IR2V),
        input_references=InputReferenceCollection((InputReference(InputReferenceKind.IMAGE, png),)),
    )
    assert project_method(m, "IR2V")["media_limits"]["image"]["max_width"] == 800
    assert RequestValidator().prepare_native_media(request, m) == request

    oversized = replace(
        request,
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.IMAGE, png_data_url(640, 480, padding=100)),)
        ),
    )
    m = configured_model("google/gemini-omni-1.2-flash", {"image": {"max_bytes": 50}}, "IR2V")
    with pytest.raises(Exception, match="size or geometry"):
        RequestValidator().prepare_native_media(oversized, m)

    too_wide = replace(
        request,
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.IMAGE, png_data_url(900, 480)),)
        ),
    )
    m = configured_model("google/gemini-omni-1.2-flash", {"image": {"max_width": 800}}, "IR2V")
    with pytest.raises(Exception, match="size or geometry"):
        RequestValidator().prepare_native_media(too_wide, m)


def test_frame_one_and_two_use_role_specific_geometry_limits() -> None:
    m = configured_model(
        "google/gemini-omni-1.2-flash",
        {"image": {"max_width": 700}},
        "FLF2V",
    )
    first_ok = replace(
        witness(m, InferenceMethod.FLF2V),
        first_frame=FrameReference(FrameType.FIRST, png_data_url(640, 480)),
        last_frame=FrameReference(FrameType.LAST, png_data_url(640, 480)),
    )
    assert RequestValidator().prepare_native_media(first_ok, m) == first_ok
    last_bad = replace(
        first_ok,
        last_frame=FrameReference(FrameType.LAST, png_data_url(800, 480)),
    )
    with pytest.raises(Exception, match="size or geometry"):
        RequestValidator().prepare_native_media(last_bad, m)
    first_bad = replace(
        first_ok,
        first_frame=FrameReference(FrameType.FIRST, png_data_url(800, 480)),
    )
    with pytest.raises(Exception, match="size or geometry"):
        RequestValidator().prepare_native_media(first_bad, m)


def test_external_image_url_fails_closed_when_geometry_is_bounded() -> None:
    m = configured_model("google/gemini-omni-1.2-flash", {"image": {"min_width": 100}}, "IR2V")
    request = replace(
        witness(m, InferenceMethod.IR2V),
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.IMAGE, "https://example.com/image.png"),)
        ),
    )
    with pytest.raises(Exception, match="Image metadata cannot be verified"):
        RequestValidator().prepare_native_media(request, m)
