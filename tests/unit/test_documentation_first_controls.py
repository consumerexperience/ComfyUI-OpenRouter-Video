"""Documentation First control recovery through production decoder, validator and wire."""

from dataclasses import replace
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.configuration import input_constraint_reconciliation, project_method
from openrouter_video.errors import ProductFailureError
from openrouter_video.models import CapabilityFactState, InferenceMethod, ModelCapabilities


def documented_model(
    sizes: object = ("1280x720", "1920x1080"),
    *,
    current_recipe: bool = False,
    evidence_class: str | None = "ABSENCE_ONLY",
    state: str = "UNKNOWN",
) -> ModelCapabilities:
    size_control: dict[str, Any] = {"state": state}
    if evidence_class:
        size_control["evidence_class"] = evidence_class
    raw: dict[str, Any] = {
        "id": "synthetic/documentation-first",
        "supports_text_only": True,
        "supported_durations": [4, 8],
        "supported_resolutions": ["720p"],
        "supported_aspect_ratios": ["16:9"],
        "supported_sizes": list(sizes) if isinstance(sizes, tuple) else sizes,
        "request_shape_profiles": {
            "schema_version": 1,
            "methods": {
                "T2V": {
                    "state": "SUPPORTED",
                    "controls": {
                        "prompt": {"state": "SUPPORTED"},
                        "duration": {"state": "SUPPORTED"},
                        "resolution": {"state": "SUPPORTED"},
                        "aspect_ratio": {"state": "SUPPORTED"},
                        "size": size_control,
                    },
                    "topology": {
                        "fixed": [],
                        "reference_kinds": [],
                        "kind_sets": [[]],
                        "min": 0,
                        "max": 0,
                        "per_kind_max": {},
                    },
                }
            },
        },
    }
    model = _parse_capability(raw)
    if current_recipe:
        return model
    return replace(
        model,
        evidence_facts=tuple(
            replace(f, authority="EXACT_OFFICIAL_MODEL_PAGE")
            if f.key == "request_shape_profiles"
            else f
            for f in model.evidence_facts
        ),
    )


def test_documented_scalar_values_reach_validator_and_exact_wire_without_paid_probe() -> None:
    model = documented_model()
    profile = project_method(model, "T2V")
    assert profile["controls"]["size"]["state"] == "SUPPORTED"
    assert profile["controls"]["size"]["domain_completeness"] == "PARTIAL"
    base = request_witness(model, InferenceMethod.T2V)
    assert base is not None
    for size in ("1280x720", "1920x1080"):
        request = replace(base, size=size, resolution=None, aspect_ratio=None)
        RequestValidator().validate_capabilities(request, model)
        payload = request.to_openrouter_payload()
        assert payload["size"] == size
        assert "resolution" not in payload and "aspect_ratio" not in payload
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(base, size="100x100", resolution=None, aspect_ratio=None), model
        )


def test_new_positive_domain_expands_and_contracts_historical_absence_without_new_registry() -> (
    None
):
    expanded = project_method(documented_model(("1280x720", "1920x1080", "2560x1440")), "T2V")
    assert expanded["controls"]["size"]["values"] == ["1280x720", "1920x1080", "2560x1440"]
    contracted = project_method(documented_model(("1280x720",)), "T2V")
    assert contracted["controls"]["size"]["values"] == ["1280x720"]


@pytest.mark.parametrize("sizes", [None, False, "malformed", [1, 2]])
def test_absence_marker_does_not_promote_invalid_or_missing_domains(sizes: object) -> None:
    assert (
        project_method(documented_model(sizes), "T2V")["controls"]["size"]["state"] != "SUPPORTED"
    )


def test_explicit_current_recipe_and_route_uncertainty_remain_authoritative() -> None:
    for model in (
        documented_model(current_recipe=True),
        documented_model(evidence_class=None),
        documented_model(state="CONFLICT"),
        documented_model(state="UNSUPPORTED"),
    ):
        assert project_method(model, "T2V")["controls"]["size"]["state"] != "SUPPORTED"
    model = documented_model()
    conflicted = replace(
        model,
        evidence_facts=tuple(
            replace(f, state=CapabilityFactState.CONFLICT) if f.key == "supported_sizes" else f
            for f in model.evidence_facts
        ),
    )
    assert project_method(conflicted, "T2V")["controls"]["size"]["state"] != "SUPPORTED"


def test_positive_absence_control_loss_is_reported_as_underexposure() -> None:
    model = documented_model()
    profile = project_method(model, "T2V")
    profile["controls"]["size"] = {"state": "UNKNOWN"}
    assert any(
        row["classification"] == "CAPABILITY_UNDEREXPOSURE_DEFECT" and row["field"] == "size"
        for row in input_constraint_reconciliation(model, "T2V", profile)
    )


@pytest.mark.parametrize(
    ("model_id", "method"),
    [("alibaba/wan-3.0-prime", "I2V"), ("alibaba/wan-3.0", "I2V"), ("alibaba/wan-3.0", "FLF2V")],
)
def test_documented_wan_frame_ratio_domain_reaches_normalized_wire(
    model_id: str, method: str
) -> None:
    import json
    from pathlib import Path

    from openrouter_video.evidence_registry import enrich_capabilities

    rows = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text()
    )["data"]
    model = enrich_capabilities(_parse_capability(next(r for r in rows if r["id"] == model_id)))
    profile = project_method(model, method)
    control = profile["controls"]["aspect_ratio"]
    assert control["state"] == "SUPPORTED"
    assert set(control["values"]) == set(model.supported_aspect_ratios or ())
    base = request_witness(model, InferenceMethod(method))
    assert base is not None
    for value in control["values"]:
        request = replace(base, aspect_ratio=value, size=None)
        RequestValidator().validate_capabilities(request, model)
        payload = request.to_openrouter_payload()
        assert payload["aspect_ratio"] == value
        assert "ratio" not in payload
        assert len(cast(list[object], payload["frame_images"])) == (2 if method == "FLF2V" else 1)


def test_documented_single_image_reference_does_not_require_a_model_upper_count() -> None:
    model = _parse_capability(
        {
            "id": "synthetic/documented-single-reference",
            "reference_kinds": ["image"],
            "supports_text_only": True,
            "supported_durations": [4],
            "supported_resolutions": ["720p"],
            "supported_aspect_ratios": ["16:9"],
        }
    )
    profile = project_method(model, "IR2V")
    assert profile["state"] == "SUPPORTED"
    assert profile["topology"]["max"] == 1  # Single-image method semantics, not a model cap.
    witness = request_witness(model, InferenceMethod.IR2V)
    assert witness is not None
    RequestValidator().validate_capabilities(witness, model)
    assert len(cast(list[object], witness.to_openrouter_payload()["input_references"])) == 1
    # Multi-image quantities are not inferred from a single-reference capability.
    assert request_witness(model, InferenceMethod.MI2V) is None


@pytest.mark.parametrize(("method", "ceiling"), [("IR2V", 0), ("MI2V", 1)])
def test_impossible_explicit_per_kind_ceiling_is_not_advertised_ready(
    method: str, ceiling: int
) -> None:
    from openrouter_video.capabilities import CapabilityModeStatus, inference_method_matrix

    model = _parse_capability(
        {
            "id": "synthetic/zero-ceiling",
            "reference_kinds": ["image"],
            "per_kind_max": {"image": ceiling},
        }
    )
    assert project_method(model, method)["state"] == "CONFLICT"
    assert inference_method_matrix(model)[InferenceMethod(method)] is not CapabilityModeStatus.READY
    assert request_witness(model, InferenceMethod(method)) is None


def test_positive_mixed_primitive_without_numeric_ceiling_remains_available_and_diagnostic() -> (
    None
):
    model = _parse_capability(
        {
            "id": "synthetic/documented-mixed",
            "reference_kinds": ["image", "video", "audio"],
            "mixed_reference_kinds": True,
            "supported_durations": [4],
            "supported_resolutions": ["480p"],
        }
    )
    profile = project_method(model, "MMR2V")
    assert profile["state"] == "SUPPORTED"
    assert profile["topology"]["max"] is None
    assert profile["topology"]["execution_domain"] == "DOCUMENTED_CONTRACT"
    assert profile["topology"]["limit_completeness"] == "UNKNOWN"
    witness = request_witness(model, InferenceMethod.MMR2V)
    assert witness is not None
    RequestValidator().validate_capabilities(witness, model)
    assert len(cast(list[object], witness.to_openrouter_payload()["input_references"])) >= 2
    assert any(
        r["classification"] == "MISSING_UPSTREAM_CONTRACT"
        for r in input_constraint_reconciliation(model, "MMR2V", profile)
    )


@pytest.mark.parametrize("audio_capability", [False, None])
def test_canonical_pipeline_accepts_no_audio_default_when_model_has_no_audio_capability(
    audio_capability: bool | None,
) -> None:
    from openrouter_video.models import GenerationRequest

    model = _parse_capability(
        {
            "id": "synthetic/silent",
            "supports_text_only": True,
            "generate_audio": audio_capability,
            "supported_durations": [4],
        }
    )
    request = GenerationRequest(model.model_id, "Offline integration test", duration=4)
    assert request.generate_audio is False
    RequestValidator().validate_capabilities(request, model)
    assert request.to_openrouter_payload()["generate_audio"] is False
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(replace(request, generate_audio=True), model)
