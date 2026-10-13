import copy
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, inference_method_matrix
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_model
from openrouter_video.configuration import (
    REQUEST_SHAPES_KEY,
    configuration_status,
    project_method,
    project_semantic_values,
    projected_shape_valid,
)
from openrouter_video.evidence_registry import enrich_capabilities, load_manifest
from openrouter_video.models import (
    CapabilityFactState,
    FrameReference,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
)
from tests.projection_fixtures import synthetic_projected_model

ROOT = Path(__file__).parents[2]
CATALOGUE = json.loads(
    (ROOT / "tests/fixtures/capability-audit-catalogue.json").read_text(encoding="utf-8")
)


def current_model(slug: str) -> ModelCapabilities:
    return enrich_capabilities(
        _parse_capability(next(m for m in CATALOGUE["models"] if m["id"] == slug))
    )


@pytest.mark.parametrize("raw", CATALOGUE["models"], ids=lambda m: m["id"])
def test_every_current_model_and_method_has_supported_only_public_projection(
    raw: dict[str, Any],
) -> None:
    model = enrich_capabilities(_parse_capability(raw))
    view = cast(dict[str, Any], project_model(model, datetime.now(timezone.utc)).as_dict())
    for method in InferenceMethod:
        profile = project_method(model, method.value)
        assert (method.value in view["supported_inference_methods"]) == (
            profile["state"] == "SUPPORTED"
        )
        for name, control in profile["controls"].items():
            if control["state"] != "SUPPORTED":
                assert "values" not in control
            elif name not in {"seed", "generate_audio", "prompt"}:
                assert control["values"]


def test_audit_is_immutable_and_every_material_finding_remains_addressable() -> None:
    audit = json.loads(
        (ROOT / "contracts/product/evidence/capability-truth-audit-v1.json").read_text(
            encoding="utf-8"
        )
    )
    recorded = audit.pop("content_hash")
    assert (
        hashlib.sha256(
            json.dumps(audit, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == recorded
    )
    assert (
        len({(c["model"], c["method"]) for c in audit["claims"] if c["capability"] == "method"})
        == audit["method_rows"]
    )
    assert all(f["id"] for f in audit["findings"])


@pytest.mark.parametrize("state", ["UNKNOWN", "UNSUPPORTED", "CONFLICT"])
def test_nonpositive_method_and_controls_fail_closed_without_collapsing_state(state: str) -> None:
    model = synthetic_projected_model("future/fixture")
    fact = model.evidence_facts[0]
    shapes = copy.deepcopy(cast(dict[str, Any], fact.value))
    shapes["methods"]["AR2V"]["state"] = state
    shapes["methods"]["T2V"]["controls"]["seed"]["state"] = state
    model = replace(model, evidence_facts=(replace(fact, value=shapes),))
    assert project_method(model, "AR2V")["state"] == state
    assert (
        "AR2V" not in project_model(model, datetime.now(timezone.utc)).supported_inference_methods
    )
    assert project_semantic_values(model, "T2V", {"seed": "malformed"})["seed"] is None
    with pytest.raises(ValueError):
        project_semantic_values(model, "AR2V", {})


def test_new_catalogue_model_does_not_gain_public_methods_from_primitives() -> None:
    model = ModelCapabilities("future/unknown", supports_text_only=True)
    assert (
        inference_method_matrix(model)[InferenceMethod.T2V].value == "READY"
    )  # conceptual ontology
    assert project_model(model, datetime.now(timezone.utc)).supported_inference_methods == ()
    assert project_method(model, "T2V")["state"] == "UNKNOWN"


def test_future_evidence_update_exposes_method_and_new_domain_without_runtime_branch() -> None:
    model = current_model("bytedance/seedance-2.0-mini")
    fact = next(f for f in model.evidence_facts if f.key == REQUEST_SHAPES_KEY)
    shapes = copy.deepcopy(cast(dict[str, Any], fact.value))
    shapes["methods"]["AR2V"] = {
        "state": "SUPPORTED",
        "controls": {},
        "topology": {
            "fixed": [],
            "reference_kinds": ["audio"],
            "kind_sets": [["audio"]],
            "min": 1,
            "max": 1,
            "per_kind_max": {"audio": 1},
        },
    }
    future = replace(
        model,
        model_id="future/reviewed",
        evidence_facts=tuple(
            replace(f, value=shapes) if f is fact else f for f in model.evidence_facts
        ),
    )
    assert "AR2V" in project_model(future, datetime.now(timezone.utc)).supported_inference_methods
    assert inference_method_matrix(future)[InferenceMethod.AR2V].value == "READY"
    assert (
        "AR2V" not in project_model(model, datetime.now(timezone.utc)).supported_inference_methods
    )


@pytest.mark.parametrize("slug", ["bytedance/seedance-2.0-mini", "bytedance/seedance-2.0-fast"])
def test_audio_only_conflict_does_not_remove_confirmed_mixed_audio(slug: str) -> None:
    model = current_model(slug)
    assert project_method(model, "AR2V")["state"] == "CONFLICT"
    mixed = project_method(model, "MMR2V")
    assert mixed["state"] == "SUPPORTED"
    assert projected_shape_valid(mixed, ("image", "video", "audio"))
    assert not projected_shape_valid(mixed, ("audio", "audio"))
    assert not projected_shape_valid(mixed, ("audio",))
    assert not projected_shape_valid(mixed, ("image", "video", "audio", "audio"))


def test_hailuo_and_grok_joint_domains_are_not_cartesian_and_unrelated_modes_survive() -> None:
    hailuo = current_model("minimax/hailuo-2.3")
    assert project_method(hailuo, "T2V")["controls"]["duration"]["values"] == [6]
    assert project_method(hailuo, "I2V")["controls"]["duration"]["values"] == [6]
    grok = current_model("x-ai/grok-imagine-video")
    profile = project_method(grok, "MI2V")
    context = {"geometry_authority": "NORMALIZED", "inference_method": "MI2V", "reference_count": 2}
    relations = tuple(profile["configuration_relations"])
    assert (
        configuration_status(
            relations, {"resolution": "480p", "duration": 1, "aspect_ratio": "16:9"}, context
        )
        == "READY"
    )
    assert (
        configuration_status(
            relations, {"resolution": "480p", "duration": 10, "aspect_ratio": "16:9"}, context
        )
        == "CONFIRMED_INCOMPATIBLE"
    )
    assert (
        configuration_status(
            relations,
            {"resolution": "480p", "duration": 1, "aspect_ratio": "16:9"},
            {**context, "reference_count": 3},
        )
        == "CONFIRMED_INCOMPATIBLE"
    )
    assert 15 in project_method(grok, "T2V")["controls"]["duration"]["values"]
    assert "480p" in project_method(grok, "I2V")["controls"]["resolution"]["values"]
    assert project_method(grok, "I2V")["controls"]["aspect_ratio"]["state"] == "UNKNOWN"


def test_hidden_values_and_roles_are_omitted_before_serializer_without_method_coercion() -> None:
    model = current_model("x-ai/grok-imagine-video-1.5-lite")
    values = project_semantic_values(
        model,
        "T2V",
        {
            "duration": 1,
            "resolution": "480p",
            "aspect_ratio": "16:9",
            "size": "stale",
            "seed": "malformed",
            "generate_audio": True,
            "first_frame": object(),
            "direct_references": object(),
            "input_references": object(),
        },
    )
    assert all(
        values[name] is None
        for name in (
            "size",
            "seed",
            "generate_audio",
            "first_frame",
            "direct_references",
            "input_references",
        )
    )
    request = GenerationRequest(
        model.model_id,
        "test",
        duration=values["duration"],
        resolution=values["resolution"],
        aspect_ratio=values["aspect_ratio"],
        generate_audio=values["generate_audio"],
    )
    wire = request.to_openrouter_payload()
    assert not {
        "seed",
        "size",
        "generate_audio",
        "frame_images",
        "input_references",
        "inference_method",
    }.intersection(wire)
    RequestValidator().validate_capabilities(request, model)
    with pytest.raises(ValueError):
        project_semantic_values(model, "invalid-method", {})


def test_exact_enum_and_authority_are_scoped_and_explicit_supported_false_is_preserved() -> None:
    model = current_model("runway/gen-4.5")
    assert project_method(model, "T2V")["controls"]["size"]["values"] == ["1280x720", "720x1280"]
    values = project_semantic_values(
        model,
        "T2V",
        {
            "size": "1280x720",
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "geometry_authority": "EXACT",
        },
    )
    assert values["size"] == "1280x720" and values["resolution"] is values["aspect_ratio"] is None
    mini = current_model("bytedance/seedance-2.0-mini")
    assert (
        project_semantic_values(mini, "MMR2V", {"generate_audio": False})["generate_audio"] is False
    )
    assert (
        GenerationRequest("synthetic/valid", "test", generate_audio=False).to_openrouter_payload()[
            "generate_audio"
        ]
        is False
    )


def test_accepted_native_mixed_and_image_reference_semantic_requests_still_validate() -> None:
    mini = current_model("bytedance/seedance-2.0-mini")
    mixed = GenerationRequest(
        mini.model_id,
        "test",
        InferenceMethod.MMR2V,
        duration=4,
        resolution="480p",
        aspect_ratio="16:9",
        input_references=InputReferenceCollection(
            tuple(
                InputReference(kind, "https://example.com/reference") for kind in InputReferenceKind
            )
        ),
    )
    RequestValidator().validate_shape(mixed)
    RequestValidator().validate_capabilities(mixed, mini)
    grok = current_model("x-ai/grok-imagine-video")
    images = InputReferenceCollection(
        tuple(
            InputReference(InputReferenceKind.IMAGE, "https://example.com/image.png")
            for _ in range(2)
        )
    )
    RequestValidator().validate_capabilities(
        GenerationRequest(
            grok.model_id,
            "test",
            InferenceMethod.MI2V,
            duration=1,
            resolution="480p",
            aspect_ratio="16:9",
            generate_audio=None,
            input_references=images,
        ),
        grok,
    )
    lite = current_model("x-ai/grok-imagine-video-1.5-lite")
    RequestValidator().validate_capabilities(
        GenerationRequest(
            lite.model_id,
            "test",
            InferenceMethod.I2V,
            duration=1,
            resolution="480p",
            generate_audio=None,
            first_frame=FrameReference(FrameType.FIRST, "https://example.com/image.png"),
        ),
        lite,
    )


def test_existing_live_conflicts_and_manifest_integrity_are_not_rewritten() -> None:
    manifest = load_manifest()
    mini = current_model("bytedance/seedance-2.0-mini")
    assert any(
        f.key == "exact_size_conformance" and f.state is CapabilityFactState.CONFLICT
        for f in mini.evidence_facts
    )
    assert any(
        f.key == "inference_method_conformance" and f.state is CapabilityFactState.CONFLICT
        for f in mini.evidence_facts
    )
    assert manifest["models"]


def test_supported_seed_domain_is_explicit_and_out_of_domain_values_are_omitted() -> None:
    model = synthetic_projected_model()
    assert project_semantic_values(model, "T2V", {"seed": "42"})["seed"] == 42
    assert project_semantic_values(model, "T2V", {"seed": 1000})["seed"] is None
    assert project_semantic_values(model, "T2V", {"seed": -1})["seed"] is None
