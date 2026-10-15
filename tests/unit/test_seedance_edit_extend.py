import copy
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from openrouter_video.capabilities import RequestValidator
from openrouter_video.configuration import project_method, projected_shape_valid
from openrouter_video.errors import ProductFailureError
from openrouter_video.evidence_registry import load_manifest
from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
)
from openrouter_video.pricing import CostEstimateInputs, PreflightCostEstimator
from tests.unit.test_public_projection import CATALOGUE, current_model

METHODS = (InferenceMethod.V2V_EDIT, InferenceMethod.V2V_EXTEND)
SOURCE = InputReference(InputReferenceKind.VIDEO, "https://example.com/source.mp4")


def test_manifest_delta_is_exactly_two_method_profiles_and_their_scope_note() -> None:
    data = copy.deepcopy(load_manifest())
    data.pop("content_hash")
    model = next(m for m in data["models"] if m["exact_model_id"] == "bytedance/seedance-2.5")
    fact = model["facts"]["request_shape_profiles"]
    fact["scope"] = fact["scope"].split(" Seedance 2.5 Edit/Extend omission corrected")[0]
    for method in METHODS:
        fact["value"]["methods"][method.value] = {
            "state": "UNKNOWN",
            "controls": {},
            "notes": (
                "No complete reviewed native + OpenRouter exact-shape proof. "
                "Absence is not UNSUPPORTED."
            ),
            "audit_scope": "CURRENT_MODEL_METHOD",
        }
    digest = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == "15b5eab137c54d677ac37f1bef2e5d98095715e898aa24d4a9fcca56cda9059b"


@pytest.mark.parametrize("method", METHODS)
def test_seedance_transform_requires_video_and_uses_only_reference_wire(
    method: InferenceMethod,
) -> None:
    model = current_model("bytedance/seedance-2.5")
    profile = project_method(model, method.value)
    assert profile["state"] == "SUPPORTED"
    assert profile["topology"]["fixed"] == ["source_video"]
    assert profile["controls"] == project_method(model, "MMR2V")["controls"]
    request = GenerationRequest(
        model.model_id,
        "Continue or edit the shot",
        method,
        duration=4,
        resolution="480p",
        aspect_ratio="16:9",
        source_video=SOURCE,
    )
    validator = RequestValidator()
    validator.validate_shape(request)
    validator.validate_capabilities(request, model)
    wire = request.to_openrouter_payload()
    assert wire["input_references"] == [{"type": "video_url", "video_url": {"url": SOURCE.url}}]
    assert not {
        "mode",
        "method",
        "inference_method",
        "source_role",
        "source_video",
        "frame_images",
        "draft",
    }.intersection(wire)
    for invalid in (
        replace(request, source_video=None),
        replace(
            request,
            source_video=InputReference(InputReferenceKind.IMAGE, "https://example.com/image.png"),
        ),
        replace(
            request, first_frame=FrameReference(FrameType.FIRST, "https://example.com/frame.png")
        ),
    ):
        with pytest.raises(ProductFailureError):
            validator.validate_shape(invalid)
    extra = InputReferenceCollection(
        tuple(InputReference(kind, "https://example.com/reference") for kind in InputReferenceKind)
    )
    combined = replace(request, input_references=extra)
    validator.validate_shape(combined)
    validator.validate_capabilities(combined, model)
    combined_references = combined.to_openrouter_payload()["input_references"]
    assert isinstance(combined_references, list) and len(combined_references) == 4


@pytest.mark.parametrize("method", METHODS)
def test_optional_limits_reserve_required_source_and_reject_overflow(
    method: InferenceMethod,
) -> None:
    profile = project_method(current_model("bytedance/seedance-2.5"), method.value)
    assert projected_shape_valid(profile, ())
    assert projected_shape_valid(profile, ("image",) * 30 + ("video",) * 9 + ("audio",) * 10)
    for kinds in (("image",) * 31, ("video",) * 10, ("audio",) * 11):
        assert not projected_shape_valid(profile, kinds)


def test_other_models_and_draft_do_not_gain_projection() -> None:
    for raw in CATALOGUE["models"]:
        model = current_model(raw["id"])
        if model.model_id != "bytedance/seedance-2.5":
            assert all(project_method(model, m.value)["state"] != "SUPPORTED" for m in METHODS)
    assert not any("draft" in method.value.lower() for method in InferenceMethod)


@pytest.mark.parametrize("method", METHODS)
def test_estimator_reuses_existing_video_reference_price(method: InferenceMethod) -> None:
    model = current_model("bytedance/seedance-2.5")
    estimator = PreflightCostEstimator()
    now = datetime.now(timezone.utc)
    inputs = CostEstimateInputs(
        model_id=model.model_id,
        inference_method=method,
        duration=4,
        resolution="480p",
        aspect_ratio="16:9",
        source_video_present=True,
    )
    actual = estimator.estimate(model, inputs, observed_at=now)
    reference = estimator.estimate(
        model,
        replace(
            inputs,
            inference_method=InferenceMethod.VR2V,
            source_video_present=False,
            reference_kinds=(InputReferenceKind.VIDEO,),
            reference_count=1,
        ),
        observed_at=now,
    )
    assert actual == reference
    assert actual.reason == "video_input_pricing_semantics_ambiguous"
