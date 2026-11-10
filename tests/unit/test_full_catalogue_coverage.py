"""Current-catalogue coverage and the exact protected delta; no paid execution."""

import ast
import json
import re
import shutil
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, eligible_methods, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_selectable
from openrouter_video.configuration import project_method
from openrouter_video.errors import ProductFailureError
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import (
    GenerationRequest,
    InferenceMethod,
    ModelCapabilities,
    ProviderOption,
)

ROOT = Path(__file__).resolve().parents[2]
RAW = json.loads((ROOT / "tests/fixtures/op07-full-catalogue.json").read_text())["data"]


def witness(m: ModelCapabilities, method: InferenceMethod) -> GenerationRequest:
    result = request_witness(m, method)
    assert result is not None
    return result


def payload(request: GenerationRequest) -> dict[str, Any]:
    return cast(dict[str, Any], request.to_openrouter_payload())


def model(mid: str) -> ModelCapabilities:
    return enrich_capabilities(_parse_capability(next(m for m in RAW if m["id"] == mid)))


@pytest.mark.parametrize("raw", RAW, ids=lambda r: r["id"])
def test_every_discovered_model_has_a_real_validator_serializer_witness(
    raw: dict[str, Any],
) -> None:
    m = enrich_capabilities(_parse_capability(raw))
    methods = eligible_methods(m)
    assert methods, raw["id"]
    view = project_selectable(m, datetime.now(timezone.utc))
    assert view.supported_inference_methods == tuple(x.value for x in methods)
    for method in methods:
        request = witness(m, method)
        RequestValidator().validate_shape(request)
        RequestValidator().validate_capabilities(request, m)
        wire = payload(request)
        assert wire["model"] == raw["id"]
        assert not {"inference_method", "source_video", "Authorization", "api_key"} & wire.keys()


@pytest.mark.parametrize("raw", RAW, ids=lambda r: r["id"])
def test_positive_standard_scalar_flags_survive_projection_and_wire(raw: dict[str, Any]) -> None:
    m = enrich_capabilities(_parse_capability(raw))
    for method in eligible_methods(m):
        if method not in {InferenceMethod.T2V, InferenceMethod.I2V, InferenceMethod.FLF2V}:
            continue
        profile = project_method(m, method.value)
        base = witness(m, method)
        for control, flag, value in [
            ("seed", "seed", 123),
            ("generate_audio", "generate_audio", True),
        ]:
            if raw.get(flag) is not True:
                continue
            assert profile["controls"][control]["state"] == "SUPPORTED"
            request = (
                replace(base, seed=123) if control == "seed" else replace(base, generate_audio=True)
            )
            RequestValidator().validate_capabilities(request, m)
            assert payload(request)[control] == value


@pytest.mark.parametrize(
    "method", [InferenceMethod.T2V, InferenceMethod.I2V, InferenceMethod.FLF2V]
)
def test_omni12_full_confirmed_scalar_domains_and_wire(method: InferenceMethod) -> None:
    m = model("google/gemini-omni-1.2-flash")
    profile = project_method(m, method.value)
    assert m.supported_resolutions is not None
    assert m.supported_sizes is not None
    assert m.supported_aspect_ratios is not None
    assert profile["controls"]["resolution"]["values"] == list(m.supported_resolutions)
    assert profile["controls"]["size"]["values"] == list(m.supported_sizes)
    assert profile["controls"]["seed"]["state"] == "SUPPORTED"
    assert profile["controls"]["generate_audio"]["state"] == "SUPPORTED"
    duration = range(3, 11) if method is InferenceMethod.FLF2V else range(3, 16)
    assert profile["controls"]["duration"]["values"] == list(duration)
    base = witness(m, method)
    for seconds, resolution, ratio, audio in product(
        duration, m.supported_resolutions, m.supported_aspect_ratios, [False, True]
    ):
        req = replace(
            base,
            duration=seconds,
            resolution=resolution,
            aspect_ratio=ratio,
            size=None,
            generate_audio=audio,
            seed=137,
        )
        RequestValidator().validate_shape(req)
        RequestValidator().validate_capabilities(req, m)
        wire = payload(req)
        assert (
            wire["duration"] == seconds and wire["seed"] == 137 and wire["generate_audio"] is audio
        )
    for size in m.supported_sizes:
        req = replace(base, size=size, resolution=None, aspect_ratio=None)
        RequestValidator().validate_capabilities(req, m)
        assert payload(req)["size"] == size
    assert "2K" not in profile["controls"]["resolution"]["values"]


def test_veo_lite_known_coupling_for_both_geometry_representations() -> None:
    m = model("google/veo-3.1-lite")
    v = RequestValidator()
    assert m.supported_sizes is not None
    for method in [InferenceMethod.T2V, InferenceMethod.I2V, InferenceMethod.FLF2V]:
        base = witness(m, method)
        for seconds, res in product([4, 6, 8], ["720p", "1080p"]):
            req = replace(base, duration=seconds, resolution=res, aspect_ratio="9:16", size=None)
            valid = seconds == 8 or (res == "720p" and method is not InferenceMethod.FLF2V)
            if valid:
                v.validate_capabilities(req, m)
            else:
                with pytest.raises(ProductFailureError):
                    v.validate_capabilities(req, m)
        for size in m.supported_sizes:
            req = replace(base, duration=8, size=size, resolution=None, aspect_ratio=None)
            v.validate_capabilities(req, m)


def test_specialized_source_operations_and_reviewed_voice_controls() -> None:
    upscale = model("black-forest-labs/flux-video-upscale")
    req = witness(upscale, InferenceMethod.V2V_UPSCALE)
    assert req.prompt is None and req.source_video is not None
    for factor, creative in product([1.5, 1.75, 2, 2.5, 3], [0, 1]):
        current = replace(req, upscale_factor=factor, creativity=creative)
        RequestValidator().validate_capabilities(current, upscale)
        wire = payload(current)
        assert wire["upscale_factor"] == factor and wire["creativity"] == creative
        assert "prompt" not in wire
    for factor in [1.49, 3.01]:
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(replace(req, upscale_factor=factor), upscale)
    avatar = model("heygen/avatar-iv")
    req = witness(avatar, InferenceMethod.IR2V)
    req = replace(req, provider_options=(ProviderOption("heygen", "voice_id", "TEST_ONLY_VOICE"),))
    RequestValidator().validate_capabilities(req, avatar)
    assert payload(req)["provider"]["options"]["heygen"]["voice_id"] == "TEST_ONLY_VOICE"
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(
                req, provider_options=(ProviderOption("heygen", "voice_settings", "unreviewed"),)
            ),
            avatar,
        )
    assert InferenceMethod.AVATAR_AUDIO not in eligible_methods(avatar)


def test_new_structured_frame_model_activates_without_a_whitelist_or_price() -> None:
    m = _parse_capability(
        {
            "id": "future/official-new-id",
            "supported_frame_images": ["first_frame"],
            "supported_durations": [7],
            "supported_resolutions": ["720p"],
            "supported_aspect_ratios": ["9:16"],
        }
    )
    assert m.pricing_evidence is None
    assert eligible_methods(m) == (InferenceMethod.I2V,)
    assert request_witness(m, InferenceMethod.T2V) is None


def test_old_fingerprint_functions_and_submit_resume_code_preserved() -> None:
    def before(path: str) -> str:
        git = shutil.which("git")
        assert git is not None
        return subprocess.check_output(  # noqa: S603 - fixed local baseline revision and source paths
            [git, "show", "86971eac8dfbfd875716e17c1ff859b452290de2:" + path],
            cwd=ROOT,
            text=True,
            encoding="utf8",
        )

    path = "src/openrouter_video/application.py"
    actual = (ROOT / path).read_text()
    preserved = actual.replace("request_fingerprint_v4", "request_fingerprint_v3")
    preserved = preserved.replace('        "_continuation_observation",\n', "")
    preserved = preserved.replace(
        "            request = self._validator.prepare_native_media(request, capability)\n", ""
    )
    preserved = preserved.replace(
        "        self._continuation_observation = observation_client\n", ""
    )
    preserved = re.sub(
        r"            if request.previous_job_id is not None:.*?"
        r"                # End continuation preflight.\n",
        "",
        preserved,
        flags=re.S,
    )
    assert preserved == before(path)
    path = "src/openrouter_video/models.py"

    def functions(source: str) -> dict[str, str]:
        return {
            n.name: ast.dump(n, include_attributes=False)
            for n in ast.parse(source).body
            if isinstance(n, ast.FunctionDef)
        }

    a, b = functions(actual if False else (ROOT / path).read_text()), functions(before(path))
    for name in ["request_fingerprint_v1", "request_fingerprint_v2", "request_fingerprint_v3"]:
        assert a[name] == b[name]


@pytest.mark.parametrize(
    "method",
    [
        InferenceMethod.IR2V,
        InferenceMethod.MI2V,
        InferenceMethod.VR2V,
        InferenceMethod.V2V_EDIT,
        InferenceMethod.V2V_EXTEND,
    ],
)
def test_omni12_reference_and_source_operation_wire(method: InferenceMethod) -> None:
    from openrouter_video.models import InputReference, InputReferenceCollection, InputReferenceKind

    m = model("google/gemini-omni-1.2-flash")
    req = witness(m, method)
    assert req is not None
    RequestValidator().validate_capabilities(req, m)
    wire = payload(req)
    task = (
        "edit"
        if method is InferenceMethod.V2V_EDIT
        else "extend"
        if method is InferenceMethod.V2V_EXTEND
        else "reference_to_video"
    )
    assert wire["provider"]["options"]["google-ai-studio"]["task"] == task
    if method is InferenceMethod.MI2V:
        refs = InputReferenceCollection(
            tuple(
                InputReference(InputReferenceKind.IMAGE, f"https://example.com/{i}.png")
                for i in range(6)
            )
        )
        RequestValidator().validate_capabilities(replace(req, input_references=refs), m)
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(
                replace(
                    req,
                    input_references=InputReferenceCollection(
                        (*refs.references, refs.references[0])
                    ),
                ),
                m,
            )
    if method is InferenceMethod.VR2V:
        refs = InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, "https://example.com/v.mp4"),) * 3
        )
        RequestValidator().validate_capabilities(
            replace(req, input_references=refs, duration=10), m
        )
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(
                replace(req, input_references=refs, duration=11), m
            )
    if method in {InferenceMethod.V2V_EDIT, InferenceMethod.V2V_EXTEND}:
        previous = replace(
            req, source_video=None, previous_job_id="gen-vid-1234567890-12345678901234567890"
        )
        RequestValidator().validate_shape(previous)
        RequestValidator().validate_capabilities(previous, m)
        assert "input_references" not in payload(previous)
        assert payload(previous)["previous_job_id"] == previous.previous_job_id
