from datetime import datetime, timezone
from typing import Any, cast

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_selectable
from openrouter_video.configuration import (
    input_constraint_reconciliation,
    project_method,
    projected_shape_valid,
)
from openrouter_video.models import InferenceMethod


def partial_contract() -> dict[str, Any]:
    return {
        "id": "synthetic/documented-subset",
        "reference_kinds": ["image", "video", "audio"],
        "mixed_reference_kinds": True,
        "request_shape_profiles": {
            "schema_version": 1,
            "methods": {
                "MMR2V": {
                    "state": "SUPPORTED",
                    "review_sources": [
                        "https://openrouter.ai/docs/cookbook/video-generation/reference-to-video"
                    ],
                    "controls": {
                        "prompt": {"state": "SUPPORTED"},
                        "duration": {
                            "state": "SUPPORTED",
                            "values": [4],
                            "domain_completeness": "PARTIAL",
                        },
                    },
                    "topology": {
                        "fixed": [],
                        "reference_kinds": ["image", "video", "audio"],
                        "kind_sets": [["image", "video"], ["image", "video", "audio"]],
                        "min": 2,
                        "max": None,
                        "per_kind_max": {},
                        "verified_configurations": [{"image": 1, "video": 1, "audio": 1}],
                        "constraint_evidence": {
                            "max": {
                                "state": "UNKNOWN",
                                "scope": "total",
                                "source": "https://openrouter.ai/test",
                                "classification": "MISSING_UPSTREAM_CONTRACT",
                            },
                            "per_kind_max": {
                                "state": "UNKNOWN",
                                "scope": "per_kind",
                                "source": "https://openrouter.ai/test",
                            },
                            "verified_configurations": {
                                "state": "SUPPORTED",
                                "scope": "method",
                                "source": "https://openrouter.ai/test",
                                "reason": "Synthetic exact documented configuration",
                            },
                        },
                    },
                }
            },
        },
    }


def test_documented_method_and_partial_values_survive_missing_catalogue_limits() -> None:
    model = _parse_capability(partial_contract())
    p = project_method(model, "MMR2V")
    assert p["state"] == p["method_support"] == "SUPPORTED"
    assert p["topology"]["max"] is None
    assert p["topology"]["execution_domain"] == "VERIFIED_CONFIGURATIONS"
    assert p["topology"]["limit_completeness"] == "PARTIAL"
    assert p["controls"]["duration"]["values"] == [4]
    assert projected_shape_valid(p, ("image", "video", "audio"))
    assert not projected_shape_valid(p, ("image", "video"))
    assert not projected_shape_valid(p, ("image", "image", "video", "audio"))
    witness = request_witness(model, InferenceMethod.MMR2V)
    assert witness is not None and witness.duration == 4
    RequestValidator().validate_capabilities(witness, model)
    payload = cast(dict[str, Any], witness.to_openrouter_payload())
    assert [r["type"] for r in payload["input_references"]] == [
        "image_url",
        "video_url",
        "audio_url",
    ]


def test_unknown_upper_bound_is_not_unlimited_or_loss_of_operation() -> None:
    raw = partial_contract()
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"].pop("verified_configurations")
    model = _parse_capability(raw)
    p = project_method(model, "MMR2V")
    assert p["state"] == "SUPPORTED" and p["topology"]["execution_domain"] == "UNVERIFIED"
    assert request_witness(model, InferenceMethod.MMR2V) is None
    assert (
        "MMR2V" in project_selectable(model, datetime.now(timezone.utc)).supported_inference_methods
    )
    assert not projected_shape_valid(p, ("image", "video", "audio"))


def test_current_domain_expands_partial_observation_without_promoting_it_to_maximum() -> None:
    raw = partial_contract()
    raw.update(supported_durations=[4, 5, 6], per_kind_max={"image": 9, "video": 3, "audio": 3})
    model = _parse_capability(raw)
    p = project_method(model, "MMR2V")
    assert p["controls"]["duration"]["values"] == [4, 5, 6]
    assert p["topology"]["max"] is None
    assert p["topology"]["execution_domain"] == "CONFIRMED_BOUNDS"
    assert projected_shape_valid(p, ("image",) * 9 + ("video",) * 3 + ("audio",) * 3)
    # This is synthetic structured OpenRouter evidence, never a Seedance-native promotion.


def test_explicit_restriction_and_actual_removal_override_old_positive_examples() -> None:
    raw = partial_contract()
    raw.update(max_reference_count=2)
    model = _parse_capability(raw)
    p = project_method(model, "MMR2V")
    assert not projected_shape_valid(p, ("image", "video", "audio"))
    raw["request_shape_profiles"]["methods"]["MMR2V"]["state"] = "UNSUPPORTED"
    removed = _parse_capability(raw)
    assert project_method(removed, "MMR2V")["state"] == "UNSUPPORTED"
    assert request_witness(removed, InferenceMethod.MMR2V) is None


def test_conflicting_or_unproven_configuration_cannot_admit_paid_request() -> None:
    raw = partial_contract()
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]["constraint_state"] = "CONFLICT"
    p = project_method(_parse_capability(raw), "MMR2V")
    assert p["state"] == "CONFLICT"
    assert not projected_shape_valid(p, ("image", "video", "audio"))
    raw = partial_contract()
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]["constraint_evidence"][
        "verified_configurations"
    ]["source"] = "https://native.example/model"
    assert request_witness(_parse_capability(raw), InferenceMethod.MMR2V) is None


def test_registered_positive_evidence_loss_is_machine_detected_without_catalogue_count_field() -> (
    None
):
    model = _parse_capability(partial_contract())
    p = project_method(model, "MMR2V")
    p["state"] = "UNKNOWN"
    rows = input_constraint_reconciliation(model, "MMR2V", p)
    assert any(
        r["classification"] == "CAPABILITY_UNDEREXPOSURE_DEFECT" and r["field"] == "method_support"
        for r in rows
    )


def test_total_only_transport_bound_admits_references_with_actual_source_reservation() -> None:
    raw = partial_contract()
    raw.update(reference_kinds=["video"], max_reference_count=3)
    entry = raw["request_shape_profiles"]["methods"].pop("MMR2V")
    entry["topology"] = {
        "fixed": ["source_video"],
        "reference_kinds": ["video"],
        "kind_sets": [[], ["video"]],
        "min": 0,
        "max": None,
        "per_kind_max": {},
    }
    raw["request_shape_profiles"]["methods"]["V2V_EDIT"] = entry
    p = project_method(_parse_capability(raw), "V2V_EDIT")
    assert p["topology"]["execution_domain"] == "CONFIRMED_BOUNDS"
    assert projected_shape_valid(p, ("video", "video"), source_present=True)
    assert not projected_shape_valid(p, ("video", "video", "video"), source_present=True)
    assert projected_shape_valid(p, ("video", "video", "video"), source_present=False)


def test_malformed_or_explicitly_withdrawn_scalar_is_not_reactivated_by_old_subset() -> None:
    raw = partial_contract()
    raw["supported_durations"] = "malformed"
    p = project_method(_parse_capability(raw), "MMR2V")
    assert p["controls"]["duration"]["state"] == "UNKNOWN"
    assert "values" not in p["controls"]["duration"]
    raw["supported_durations"] = False
    p = project_method(_parse_capability(raw), "MMR2V")
    assert p["controls"]["duration"]["state"] == "UNSUPPORTED"
