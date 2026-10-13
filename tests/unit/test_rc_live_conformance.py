from datetime import datetime, timezone
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, inference_method_matrix
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_model
from openrouter_video.configuration import profile_constraints, project_configuration
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
    with pytest.raises(ProductFailureError, match="CONFIRMED_INCOMPATIBLE"):
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


def test_standalone_audio_conflict_does_not_deny_mixed_audio_or_other_models() -> None:
    mini = observed_model("bytedance/seedance-2.0-mini")
    matrix = inference_method_matrix(mini)
    assert matrix[InferenceMethod.AR2V].value == "CONFLICT"
    assert matrix[InferenceMethod.MMR2V].value == "READY"
    assert matrix[InferenceMethod.VR2V].value == "READY"
    projected = cast(dict[str, Any], project_model(mini, datetime.now(timezone.utc)).as_dict())
    assert "AR2V" not in projected["supported_inference_methods"]
    assert "MMR2V" in projected["supported_inference_methods"]
    other = observed_model("bytedance/seedance-2.0-fast")
    assert inference_method_matrix(other)[InferenceMethod.AR2V].value == "READY"


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
