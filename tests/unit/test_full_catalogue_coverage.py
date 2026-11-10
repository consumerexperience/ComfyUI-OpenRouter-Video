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


@pytest.mark.parametrize("raw", RAW, ids=lambda r: r["id"])
def test_every_exposed_exact_size_has_a_valid_conditional_request(raw: dict[str, Any]) -> None:
    m = enrich_capabilities(_parse_capability(raw))
    validator = RequestValidator()
    for method in eligible_methods(m):
        profile = project_method(m, method.value)
        control = profile["controls"]["size"]
        if control["state"] != "SUPPORTED":
            continue
        base = witness(m, method)
        durations = profile["controls"]["duration"].get("values", [None])
        for size in control["values"]:
            valid = False
            for seconds in durations:
                request = replace(
                    base, size=size, resolution=None, aspect_ratio=None, duration=seconds
                )
                try:
                    validator.validate_capabilities(request, m)
                except ProductFailureError:
                    continue
                assert payload(request)["size"] == size
                valid = True
                break
            assert valid, (m.model_id, method.value, size)


@pytest.mark.parametrize(
    "mid",
    [
        "black-forest-labs/flux-video-edit",
        "black-forest-labs/flux-video-upscale",
        "black-forest-labs/flux-3-video",
    ],
)
def test_flux_safety_control_complete_integer_domain_and_omission(mid: str) -> None:
    m = model(mid)
    base = witness(m, eligible_methods(m)[0])
    assert "provider" not in payload(base)
    for value in range(5):
        request = replace(
            base, provider_options=(ProviderOption("black-forest-labs", "safety_tolerance", value),)
        )
        RequestValidator().validate_capabilities(request, m)
        assert payload(request)["provider"] == {
            "options": {"black-forest-labs": {"safety_tolerance": value}}
        }
    for invalid in [-1, 5, True, 2.5]:
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(
                replace(
                    base,
                    provider_options=(
                        ProviderOption("black-forest-labs", "safety_tolerance", invalid),
                    ),
                ),
                m,
            )


@pytest.mark.parametrize("fit", ["contain", "cover"])
@pytest.mark.parametrize("expressiveness", ["low", "medium", "high"])
@pytest.mark.parametrize("remove", [False, True])
def test_avatar_photo_scalar_controls_are_typed_and_optional(
    fit: str, expressiveness: str, remove: bool
) -> None:
    m = model("heygen/avatar-iv")
    base = witness(m, InferenceMethod.IR2V)
    assert [option.key for option in base.provider_options] == ["voice_id"]
    options = base.provider_options + (
        ProviderOption("heygen", "fit", fit),
        ProviderOption("heygen", "expressiveness", expressiveness),
        ProviderOption("heygen", "remove_background", remove),
        ProviderOption("heygen", "motion_prompt", "Natural head movement"),
        ProviderOption("heygen", "title", "TEST ONLY"),
    )
    request = replace(base, provider_options=options)
    RequestValidator().validate_capabilities(request, m)
    assert payload(request)["provider"] == {
        "options": {"heygen": {o.key: o.value for o in options}}
    }


@pytest.mark.parametrize("mid", ["runway/gen-4.5", "runway/aleph-2"])
@pytest.mark.parametrize("value", ["auto", "low"])
def test_runway_moderation_uses_only_reviewed_object_leaves(mid: str, value: str) -> None:
    m = model(mid)
    base = witness(m, eligible_methods(m)[0])
    request = replace(
        base,
        provider_options=(
            ProviderOption("runway", "contentModeration", value, path=("publicFigureThreshold",)),
        ),
    )
    RequestValidator().validate_capabilities(request, m)
    assert payload(request)["provider"] == {
        "options": {
            "runway": {
                "contentModeration": {"publicFigureThreshold": value},
            }
        }
    }
    for field, invalid in [("publicFigureThreshold", "high"), ("unreviewedField", value)]:
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(
                replace(
                    base,
                    provider_options=(
                        ProviderOption("runway", "contentModeration", invalid, path=(field,)),
                    ),
                ),
                m,
            )


def witness(m: ModelCapabilities, method: InferenceMethod) -> GenerationRequest:
    result = request_witness(m, method)
    assert result is not None
    return result


def payload(request: GenerationRequest) -> dict[str, Any]:
    return cast(dict[str, Any], request.to_openrouter_payload())


def model(mid: str) -> ModelCapabilities:
    return enrich_capabilities(_parse_capability(next(m for m in RAW if m["id"] == mid)))


def test_runtime_submit_resume_and_lifecycle_are_unchanged_outside_estimate_guard() -> None:
    git = shutil.which("git")
    assert git is not None
    name = "src/openrouter_video/comfy/runtime.py"
    before = subprocess.check_output(  # noqa: S603 - fixed local immutable revision
        [git, "show", "058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9:" + name],
        text=True,
        encoding="utf8",
    )

    def protected(text: str) -> str:
        tree = ast.parse(text)
        runtime = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ProcessRuntime"
        )
        runtime.body = [
            node
            for node in runtime.body
            if not isinstance(node, ast.AsyncFunctionDef) or node.name != "estimate_cost"
        ]
        return ast.dump(tree, include_attributes=False)

    assert protected(before) == protected((ROOT / name).read_text(encoding="utf8"))


@pytest.mark.parametrize("method", [InferenceMethod.T2V, InferenceMethod.I2V])
def test_minimax23_full_documented_prompt_and_duration_rules(method: InferenceMethod) -> None:
    m = model("minimax/hailuo-2.3")
    base = witness(m, method)
    validator = RequestValidator()
    # The real OR route currently exposes 1080p / six seconds only. Native
    # 768P support does not authorize fabricating it in the current selector.
    validator.validate_capabilities(
        replace(base, duration=6, resolution="1080p", size=None, prompt="x" * 2000), m
    )
    for seconds in (6, 10):
        with pytest.raises(ProductFailureError):
            validator.validate_capabilities(replace(base, duration=seconds, resolution="768p"), m)
    with pytest.raises(ProductFailureError):
        validator.validate_capabilities(
            replace(base, duration=10, resolution="1080p", size=None), m
        )
    with pytest.raises(ProductFailureError):
        validator.validate_capabilities(replace(base, prompt="x" * 2001), m)
    without_prompt = replace(base, prompt=None)
    if method is InferenceMethod.I2V:
        validator.validate_shape(without_prompt)
        validator.validate_capabilities(without_prompt, m)
    else:
        with pytest.raises(ProductFailureError):
            validator.validate_capabilities(without_prompt, m)


@pytest.mark.parametrize("length,valid", [(0, False), (1, True), (4096, True), (4097, False)])
def test_flux_edit_documented_prompt_boundaries(length: int, valid: bool) -> None:
    m = model("black-forest-labs/flux-video-edit")
    request = replace(witness(m, InferenceMethod.V2V_EDIT), prompt="x" * length)
    if valid:
        RequestValidator().validate_capabilities(request, m)
    else:
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(request, m)


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


@pytest.mark.parametrize("mid", ["google/veo-3.1", "google/veo-3.1-fast", "google/veo-3.1-lite"])
@pytest.mark.parametrize("enabled", [False, True])
def test_reviewed_veo_options_use_vertex_parameters(mid: str, enabled: bool) -> None:
    m = model(mid)
    request = replace(
        witness(m, InferenceMethod.T2V),
        provider_options=(
            ProviderOption("google-vertex", "negativePrompt", "avoid blur", "parameters"),
            ProviderOption("google-vertex", "enhancePrompt", enabled, "parameters"),
        ),
    )
    RequestValidator().validate_capabilities(request, m)
    assert payload(request)["provider"] == {
        "options": {
            "google-vertex": {
                "parameters": {
                    "negativePrompt": "avoid blur",
                    "enhancePrompt": enabled,
                }
            }
        }
    }


def test_reviewed_seed_watermark_false_is_not_omitted_or_nested() -> None:
    m = model("bytedance/seedance-2.0")
    request = replace(
        witness(m, InferenceMethod.T2V),
        provider_options=(ProviderOption("seed", "watermark", False),),
    )
    RequestValidator().validate_capabilities(request, m)
    assert payload(request)["provider"] == {"options": {"seed": {"watermark": False}}}
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(request, provider_options=(ProviderOption("seed", "watermark", "false"),)), m
        )


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
    assert InferenceMethod.AVATAR_AUDIO in eligible_methods(avatar)


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
