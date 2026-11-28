from datetime import datetime, timezone
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, inference_method_matrix, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_model, project_selectable
from openrouter_video.configuration import (
    profile_constraints,
    project_configuration,
    project_method,
)
from openrouter_video.eligibility import eligible_methods
from openrouter_video.errors import ProductFailureError
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import (
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
)


def observed_model(slug: str) -> ModelCapabilities:
    return enrich_capabilities(
        _parse_capability(
            {
                "id": slug,
                "supported_sizes": ["480x480", "480x640"],
                "supported_durations": [4, 5],
                "supported_resolutions": ["480p"],
                "supported_aspect_ratios": ["1:1"],
                "supported_frame_images": ["first_frame", "last_frame"],
            }
        )
    )


@pytest.mark.parametrize(
    "slug,method",
    [
        ("bytedance/seedance-1-5-pro", InferenceMethod.FLF2V),
        ("bytedance/seedance-2.0-mini", InferenceMethod.VR2V),
    ],
)
def test_live_exact_conflict_is_scoped_and_normalized_remains_available(
    slug: str, method: InferenceMethod
) -> None:
    model = observed_model(slug)
    rules = profile_constraints(model)
    context = {
        "inference_method": method.value,
        "geometry_authority": "EXACT",
        "generate_audio": False,
    }
    options = cast(dict[str, Any], project_configuration(model, {"duration": 4}, context))
    assert "480x480" not in options["options"]["size"]
    assert "480x640" in options["options"]["size"]
    # The complete live constraint is retained below. Public UNKNOWN Size now
    # also rejects the raw nonprojected request before that narrower guard.
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            GenerationRequest(slug, "test", method, duration=4, size="480x480"), model
        )
    normalized = project_configuration(
        model,
        {"duration": 4, "resolution": "480p", "aspect_ratio": "1:1"},
        {**context, "geometry_authority": "NORMALIZED"},
    )
    assert normalized["status"] == "READY"
    assert cast(dict[str, Any], normalized["options"])["size"] == ["480x480", "480x640"]
    assert rules and any(
        f.key == "exact_size_conformance" and f.state.value == "CONFLICT"
        for f in model.evidence_facts
    )
    assert (
        project_configuration(model, {"duration": 5, "size": "480x480"}, context)["status"]
        == "READY"
    )
    assert (
        project_configuration(
            model, {"duration": 4, "size": "480x480"}, {**context, "inference_method": "I2V"}
        )["status"]
        == "READY"
    )


def test_standalone_audio_rejection_preserves_documented_mixed_methods_and_limits() -> None:
    mini = observed_model("bytedance/seedance-2.0-mini")
    matrix = inference_method_matrix(mini)
    assert matrix[InferenceMethod.AR2V].value == "UNSUPPORTED"
    assert matrix[InferenceMethod.MMR2V].value == "READY"
    assert matrix[InferenceMethod.VR2V].value == "READY"
    projected = cast(dict[str, Any], project_model(mini, datetime.now(timezone.utc)).as_dict())
    assert "AR2V" not in projected["supported_inference_methods"]
    assert "MMR2V" in projected["supported_inference_methods"]
    assert "VR2V" in projected["supported_inference_methods"]
    mini_mixed = project_method(mini, "MMR2V")
    assert mini_mixed["state"] == mini_mixed["method_support"] == "SUPPORTED"
    assert mini_mixed["topology"]["execution_domain"] == "CONFIRMED_BOUNDS"
    assert mini_mixed["topology"]["max"] == 15
    assert mini_mixed["topology"]["per_kind_max"] == {"image": 9, "video": 3, "audio": 3}
    assert mini_mixed["topology"]["verified_configurations"] == [
        {"image": 1, "video": 1, "audio": 1}
    ]
    assert request_witness(mini, InferenceMethod.MMR2V) is not None
    assert InferenceMethod.MMR2V in eligible_methods(mini)
    fast = observed_model("bytedance/seedance-2.0-fast")
    assert inference_method_matrix(fast)[InferenceMethod.AR2V].value == "UNSUPPORTED"
    assert inference_method_matrix(fast)[InferenceMethod.MMR2V].value == "READY"
    assert inference_method_matrix(fast)[InferenceMethod.VR2V].value == "READY"
    fast_mixed = project_method(fast, "MMR2V")
    assert fast_mixed["state"] == fast_mixed["method_support"] == "SUPPORTED"
    assert fast_mixed["topology"]["execution_domain"] == "CONFIRMED_BOUNDS"
    assert fast_mixed["topology"]["max"] == 15
    assert request_witness(fast, InferenceMethod.MMR2V) is not None
    assert InferenceMethod.MMR2V in eligible_methods(fast)
    other = observed_model("bytedance/seedance-2.0")
    assert inference_method_matrix(other)[InferenceMethod.AR2V].value == "UNSUPPORTED"
    assert inference_method_matrix(other)[InferenceMethod.MMR2V].value == "READY"
    assert inference_method_matrix(other)[InferenceMethod.VR2V].value == "READY"
    other_mixed = project_method(other, "MMR2V")
    assert other_mixed["state"] == other_mixed["method_support"] == "SUPPORTED"
    assert other_mixed["topology"]["execution_domain"] == "CONFIRMED_BOUNDS"
    assert other_mixed["topology"]["max"] == 15
    assert request_witness(other, InferenceMethod.MMR2V) is not None
    for model in (mini, fast, other):
        selectable = project_selectable(model, datetime.now(timezone.utc)).as_dict()
        assert "MMR2V" in cast(list[str], selectable["supported_inference_methods"])


def test_audio_wire_matches_first_party_shape_without_synthetic_fields() -> None:
    request = GenerationRequest(
        "synthetic/audio",
        "test",
        InferenceMethod.AR2V,
        duration=4,
        resolution="480p",
        aspect_ratio="1:1",
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.AUDIO, "https://example.com/reference.wav"),)
        ),
    )
    wire = request.to_openrouter_payload()
    assert wire["input_references"] == [
        {"type": "audio_url", "audio_url": {"url": "https://example.com/reference.wav"}}
    ]
    assert not {"method", "inference_method", "source_role", "source_video", "size"}.intersection(
        wire
    )
