"""Owner F02-F06 concrete documented recipe regressions; no upstream submit."""

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.configuration import project_method
from openrouter_video.local_media import LocalMedia, NativeMediaError
from openrouter_video.models import (
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
)
from tests.unit.test_full_catalogue_coverage import model


@pytest.mark.parametrize(
    "mid,method",
    [
        ("minimax/hailuo-3", "T2V"),
        ("bytedance/seedance-2.5", "AR2V"),
        ("alibaba/happyhorse-1.0", "IR2V"),
        ("alibaba/happyhorse-1.0", "MI2V"),
    ],
)
def test_documented_method_has_serializable_witness(mid: str, method: str) -> None:
    m = model(mid)
    r = request_witness(m, InferenceMethod(method))
    assert r is not None
    v = RequestValidator()
    v.validate_shape(r)
    v.validate_capabilities(r, m)
    payload = cast(dict[str, Any], r.to_openrouter_payload())
    assert payload["model"] == mid
    if method == "AR2V":
        assert payload["input_references"][0]["type"] == "audio_url"


def _write_byte(path: Path) -> None:
    path.write_bytes(b"x")


@pytest.mark.parametrize(
    "mid", ["bytedance/seedance-2.0", "bytedance/seedance-2.0-fast", "bytedance/seedance-2.0-mini"]
)
def test_seedance_combined_video_duration_guard_before_encoding(mid: str, tmp_path: Path) -> None:
    m = model(mid)
    w = request_witness(m, InferenceMethod.MMR2V)
    assert w is not None
    refs = [InputReference(InputReferenceKind.IMAGE, "https://example.com/ref.png")]
    refs.extend(
        InputReference(
            InputReferenceKind.VIDEO,
            local_media=LocalMedia("video/mp4", ".mp4", _write_byte, duration=lambda: 12),
        )
        for _ in range(2)
    )
    r = replace(w, input_references=InputReferenceCollection(tuple(refs)))
    v = RequestValidator()
    v.validate_shape(r)
    v.validate_capabilities(r, m)
    prepared = v.prepare_native_media(r, m)
    assert prepared.input_references is not None
    ref = prepared.input_references.references[1]
    assert ref.local_media is not None
    assert (
        project_method(m, "MMR2V")["media_limits"]["video"]["max_combined_duration_seconds"] == 15
    )
    with pytest.raises(NativeMediaError, match="Combined reference duration"):
        ref.local_media.encode(tmp_path / "not-written.mp4")
    assert not (tmp_path / "not-written.mp4").exists()


@pytest.mark.parametrize(
    "fields",
    [
        dict(resolution="480p", aspect_ratio="16:9", size=None),
        dict(resolution="720p", aspect_ratio="16:9", size=None),
        dict(resolution=None, aspect_ratio=None, size="480x480"),
    ],
)
def test_grok_documented_domains_not_empirical_tuple_whitelist(fields: dict[str, Any]) -> None:
    m = model("x-ai/grok-imagine-video")
    w = request_witness(m, InferenceMethod.MI2V)
    assert w is not None
    refs = InputReferenceCollection(
        tuple(
            InputReference(InputReferenceKind.IMAGE, f"https://example.com/{i}.png")
            for i in range(7)
        )
    )
    r = replace(w, input_references=refs, duration=1, **fields)
    v = RequestValidator()
    v.validate_shape(r)
    v.validate_capabilities(r, m)
    payload = cast(dict[str, Any], r.to_openrouter_payload())
    assert len(payload["input_references"]) == 7
    assert not ({"size", "resolution"} <= payload.keys())


def test_automatic_duration_survives_exact_historical_method_domain() -> None:
    import json

    from openrouter_video.client import _parse_capability
    from openrouter_video.evidence_registry import enrich_capabilities

    raw = json.loads((Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text())[
        "data"
    ]
    row = next(r for r in raw if r["id"] == "bytedance/seedance-2.5")
    m = enrich_capabilities(_parse_capability(row | {"supported_durations": [-1, 4, 8]}))
    w = request_witness(m, InferenceMethod.T2V)
    assert w is not None
    r = replace(w, duration=-1)
    v = RequestValidator()
    v.validate_shape(r)
    v.validate_capabilities(r, m)
    assert r.to_openrouter_payload()["duration"] == -1
    without = enrich_capabilities(_parse_capability(row | {"supported_durations": [4, 8]}))
    from openrouter_video.errors import ProductFailureError

    with pytest.raises(ProductFailureError):
        v.validate_capabilities(r, without)
