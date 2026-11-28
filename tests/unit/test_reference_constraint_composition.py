"""Generic synthetic OpenRouter contracts, not native-provider execution claims."""

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.configuration import (
    apply_transport_input_constraints,
    input_constraint_reconciliation,
    project_method,
    projected_shape_valid,
)
from openrouter_video.errors import ProductFailureError
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import (
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
)


def contract(maximum: int | None = None) -> dict[str, Any]:
    return {
        "id": "synthetic/independent-bounds",
        "supports_text_only": True,
        "reference_kinds": ["image", "video", "audio"],
        "mixed_reference_kinds": True,
        "supported_durations": [5],
        "supported_resolutions": ["720p"],
        "supported_aspect_ratios": ["16:9"],
        "request_shape_profiles": {
            "schema_version": 1,
            "methods": {
                "MMR2V": {
                    "state": "SUPPORTED",
                    "controls": {"prompt": {"state": "SUPPORTED"}},
                    "topology": {
                        "fixed": [],
                        "reference_kinds": ["image", "video", "audio"],
                        "kind_sets": [
                            ["image", "video"],
                            ["image", "audio"],
                            ["video", "audio"],
                            ["image", "video", "audio"],
                        ],
                        "min": 2,
                        "max": maximum,
                        "per_kind_max": {"image": 9, "video": 3, "audio": 3},
                    },
                }
            },
        },
    }


def test_independent_limits_do_not_invent_a_total_and_valid_wire_is_preserved() -> None:
    model = _parse_capability(contract())
    profile = project_method(model, "MMR2V")
    assert profile["topology"]["max"] is None
    assert projected_shape_valid(profile, ("image",) * 9 + ("video",) * 3 + ("audio",) * 3)
    assert not projected_shape_valid(profile, ("image",) * 10 + ("video",))
    assert not projected_shape_valid(profile, ("audio",) * 2)
    base = request_witness(model, InferenceMethod.MMR2V)
    assert base is not None
    refs = InputReferenceCollection(
        tuple(
            InputReference(InputReferenceKind(k), f"https://example.com/{i}")
            for i, k in enumerate(("image",) * 9 + ("video",) * 3)
        )
    )
    request = replace(base, input_references=refs)
    RequestValidator().validate_capabilities(request, model)
    assert len(request.to_openrouter_payload()["input_references"]) == 12  # type: ignore[arg-type]


def test_confirmed_total_is_independent_of_per_kind_capacity() -> None:
    profile = project_method(_parse_capability(contract(4)), "MMR2V")
    assert projected_shape_valid(profile, ("image",) * 3 + ("video",))
    assert not projected_shape_valid(profile, ("image",) * 4 + ("video",))
    assert profile["topology"]["per_kind_max"]["image"] == 9


def test_required_kinds_minima_and_mutual_exclusion() -> None:
    raw = contract()
    topo = raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]
    topo.update(
        per_kind_min={"image": 3}, required_kinds=["image"], mutually_exclusive=[["video", "audio"]]
    )
    model = _parse_capability(raw)
    profile = project_method(model, "MMR2V")
    assert projected_shape_valid(profile, ("image",) * 3 + ("video",))
    assert not projected_shape_valid(profile, ("image",) * 2 + ("video",))
    assert not projected_shape_valid(profile, ("image",) * 3 + ("video", "audio"))
    assert request_witness(model, InferenceMethod.MMR2V) is not None


def test_method_scopes_do_not_share_reference_caps() -> None:
    raw = contract()
    raw["request_shape_profiles"]["methods"]["MI2V"] = deepcopy(
        raw["request_shape_profiles"]["methods"]["MMR2V"]
    )
    raw["request_shape_profiles"]["methods"]["MI2V"]["topology"].update(
        reference_kinds=["image"], kind_sets=[["image"]], max=9, per_kind_max={"image": 9}
    )
    model = _parse_capability(raw)
    assert project_method(model, "MI2V")["topology"]["max"] == 9
    assert project_method(model, "MMR2V")["topology"]["max"] is None


@pytest.mark.parametrize("images", [4, 9, 2])
def test_current_per_kind_expansion_and_contraction_supersede_stale_profile(images: int) -> None:
    raw = contract()
    legacy = raw.pop("request_shape_profiles")
    legacy["methods"]["MMR2V"]["topology"].update(
        max=3, per_kind_max={"image": 3, "video": 3, "audio": 3}
    )
    raw["per_kind_max"] = {"image": images, "video": 3, "audio": 3}
    manifest = {
        "artifact_version": "synthetic",
        "models": [
            {
                "exact_model_id": raw["id"],
                "facts": {
                    "request_shape_profiles": {
                        "value": legacy,
                        "authority": "REVIEWED",
                        "source_reference": "https://openrouter.ai/docs/guides/overview/multimodal/video-generation",
                        "observed_at": "2026-01-01T00:00:00+00:00",
                        "scope": "historical",
                    }
                },
            }
        ],
    }
    model = enrich_capabilities(_parse_capability(raw), manifest)
    profile = project_method(model, "MMR2V")
    assert profile["topology"]["per_kind_max"]["image"] == images
    if images > 3:
        assert profile["topology"]["max"] is None
    assert not any(
        r["classification"] == "CAPABILITY_UNDEREXPOSURE_DEFECT"
        for r in input_constraint_reconciliation(model, "MMR2V", profile)
    )
    damaged = deepcopy(profile)
    damaged["topology"]["per_kind_max"]["image"] = images - 1
    assert any(
        r["classification"] == "CAPABILITY_UNDEREXPOSURE_DEFECT"
        for r in input_constraint_reconciliation(model, "MMR2V", damaged)
    )


def test_new_model_with_only_live_per_kind_contract_needs_no_registry() -> None:
    raw = contract()
    raw.pop("request_shape_profiles")
    raw["per_kind_max"] = {"image": 9, "video": 3, "audio": 3}
    model = _parse_capability(raw)
    profile = project_method(model, "MMR2V")
    assert profile["state"] == "SUPPORTED" and profile["topology"]["max"] is None
    assert request_witness(model, InferenceMethod.MMR2V) is not None


def test_unknown_capacity_blocks_submit_instead_of_fabricating_maximum() -> None:
    raw = contract()
    topo = raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]
    topo["per_kind_max"] = {}
    topo["constraint_state"] = "UNKNOWN"
    model = _parse_capability(raw)
    assert project_method(model, "MMR2V")["state"] == "UNKNOWN"
    assert request_witness(model, InferenceMethod.MMR2V) is None


@pytest.mark.parametrize(
    "declaration,extra",
    [
        (
            {"per_kind_min": {"state": "UNKNOWN", "scope": "per_kind"}},
            {"per_kind_max": {"image": 9, "video": 3, "audio": 3}},
        ),
        ({"max": {"state": "UNKNOWN"}}, {"max_reference_count": "invalid"}),
        ({"max": "oops"}, {}),
    ],
)
def test_unresolved_and_malformed_fields_never_reactivate(
    declaration: dict[str, Any], extra: dict[str, Any]
) -> None:
    raw = contract()
    raw.update(extra)
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]["constraint_evidence"] = (
        declaration
    )
    model = _parse_capability(raw)
    assert project_method(model, "MMR2V")["state"] == "UNKNOWN"
    assert request_witness(model, InferenceMethod.MMR2V) is None


def test_total_underexposure_is_detected_and_complete_recipe_needs_no_coarse_duplicate() -> None:
    raw = contract()
    raw.pop("reference_kinds")
    raw.pop("mixed_reference_kinds")
    model = _parse_capability(raw)
    profile = project_method(model, "MMR2V")
    assert profile["state"] == "SUPPORTED"
    assert request_witness(model, InferenceMethod.MMR2V) is not None
    damaged = deepcopy(profile)
    damaged["topology"]["max"] = 3
    assert any(
        r["classification"] == "CAPABILITY_UNDEREXPOSURE_DEFECT"
        for r in input_constraint_reconciliation(model, "MMR2V", damaged)
    )


def test_confirmed_method_restriction_is_not_a_false_underexposure_defect() -> None:
    raw = contract(4)
    raw["per_kind_max"] = {"image": 9, "video": 3, "audio": 3}
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]["per_kind_max"]["image"] = 6
    model = _parse_capability(raw)
    profile = project_method(model, "MMR2V")
    assert profile["topology"]["max"] == 4
    assert profile["topology"]["per_kind_max"]["image"] == 6
    assert not any(
        r["classification"] == "CAPABILITY_UNDEREXPOSURE_DEFECT"
        for r in input_constraint_reconciliation(model, "MMR2V", profile)
    )


def test_advertised_capacity_is_not_arbitrarily_capped_by_schema_guard() -> None:
    raw = contract()
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]["per_kind_max"]["image"] = 1001
    model = _parse_capability(raw)
    profile = project_method(model, "MMR2V")
    assert profile["topology"]["per_kind_max"]["image"] == 1001
    assert request_witness(model, InferenceMethod.MMR2V) is not None


def test_transport_count_reserves_actual_source_without_inventing_method_total() -> None:
    topo = {
        "fixed": ["source_video"],
        "reference_kinds": ["video"],
        "kind_sets": [[], ["video"]],
        "min": 0,
        "max": None,
        "per_kind_max": {},
        "transport_max": 3,
        "transport_per_kind_max": {"video": 3},
    }
    assert apply_transport_input_constraints(topo, True)["max"] == 2
    assert apply_transport_input_constraints(topo, False)["max"] == 3
    assert projected_shape_valid({"topology": topo}, ("video",) * 2, True)
    assert not projected_shape_valid({"topology": topo}, ("video",) * 3, True)
    assert projected_shape_valid({"topology": topo}, ("video",) * 3, False)


def test_live_transport_contract_is_enforced_through_real_validator() -> None:
    raw = contract()
    raw.update(max_reference_count=3, per_kind_max={"video": 3}, reference_kinds=["video"])
    raw["request_shape_profiles"]["methods"] = {
        "V2V_EDIT": {
            "state": "SUPPORTED",
            "controls": {"prompt": {"state": "SUPPORTED"}},
            "topology": {
                "fixed": ["source_video"],
                "reference_kinds": ["video"],
                "kind_sets": [[], ["video"]],
                "min": 0,
                "max": None,
                "per_kind_max": {},
            },
        }
    }
    model = _parse_capability(raw)
    base = request_witness(model, InferenceMethod.V2V_EDIT)
    assert base is not None and base.source_video is not None
    refs = tuple(
        InputReference(InputReferenceKind.VIDEO, f"https://example.com/{i}.mp4") for i in range(3)
    )
    RequestValidator().validate_capabilities(
        replace(base, input_references=InputReferenceCollection(refs[:2])), model
    )
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(base, input_references=InputReferenceCollection(refs)), model
        )


def test_contradictory_confirmed_bounds_are_conflict_not_supported() -> None:
    raw = contract()
    raw["request_shape_profiles"]["methods"]["MMR2V"]["topology"]["per_kind_min"] = {"image": 10}
    model = _parse_capability(raw)
    assert project_method(model, "MMR2V")["state"] == "CONFLICT"
    assert request_witness(model, InferenceMethod.MMR2V) is None
