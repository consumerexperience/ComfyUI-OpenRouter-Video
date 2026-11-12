import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from openrouter_video.capabilities import CapabilityModeStatus, inference_method_matrix
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_model
from openrouter_video.configuration import project_method
from openrouter_video.evidence_registry import enrich_capabilities, load_manifest
from openrouter_video.models import (
    InferenceMethod,
    InputReferenceCapabilities,
    InputReferenceKind,
    ModelCapabilities,
)


def test_conflicting_reference_evidence_is_json_serializable() -> None:
    model = enrich_capabilities(
        ModelCapabilities(
            "bytedance/seedance-2.5",
            input_reference_capabilities=InputReferenceCapabilities(
                reference_kinds=frozenset({InputReferenceKind.IMAGE}),
            ),
        )
    )
    payload = project_model(model, datetime.now(timezone.utc)).as_dict()
    encoded = json.dumps(payload)
    assert "CONFLICT" in encoded
    assert "image" in encoded


def test_text_only_conflict_never_becomes_ready_or_silent_denial() -> None:
    model = enrich_capabilities(
        ModelCapabilities(
            "bytedance/seedance-2.5",
            supports_text_only=False,
        )
    )
    assert inference_method_matrix(model)[InferenceMethod.T2V] is CapabilityModeStatus.CONFLICT


def test_typed_controls_are_evidence_only_and_reject_untyped_values() -> None:
    model = _parse_capability(
        {
            "id": "future/control",
            "upscale_factor": {"min": 1.5, "max": 3},
            "creativity": [0, 1],
            "allowed_passthrough_parameters": ["safety_tolerance"],
        }
    )
    facts = {fact.key: fact for fact in model.evidence_facts}
    assert facts["upscale_factor"].value == {"type": "number", "min": 1.5, "max": 3}
    assert "wire unresolved" in facts["upscale_factor"].scope
    assert inference_method_matrix(model)[InferenceMethod.T2V] is not CapabilityModeStatus.READY
    invalid = _parse_capability(
        {
            "id": "future/control",
            "creativity": ["private-canary", 1],
            "allowed_passthrough_parameters": ["sk-or-synthetic-canary"],
        }
    )
    encoded = json.dumps(project_model(invalid, datetime.now(timezone.utc)).as_dict())
    assert "canary" not in encoded


def test_source_only_and_unknown_models_never_get_default_text_mode() -> None:
    for slug in (
        "black-forest-labs/flux-video-edit",
        "black-forest-labs/flux-video-upscale",
        "runway/aleph-2",
        "heygen/avatar-iv",
    ):
        assert (
            inference_method_matrix(enrich_capabilities(ModelCapabilities(slug)))[
                InferenceMethod.T2V
            ]
            is CapabilityModeStatus.UNSUPPORTED
        )
    assert (
        inference_method_matrix(ModelCapabilities("future/unknown"))[InferenceMethod.T2V]
        is CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
    )


def test_future_structured_model_needs_no_manifest_or_model_branch() -> None:
    model = _parse_capability(
        {
            "id": "future/structured",
            "supports_text_only": True,
            "reference_kinds": ["image", "video", "audio"],
            "mixed_reference_kinds": True,
            "supported_resolutions": ["480p"],
            "supported_durations": [4],
            "future_operation": True,
        }
    )
    matrix = inference_method_matrix(enrich_capabilities(model))
    assert matrix[InferenceMethod.MMR2V] is CapabilityModeStatus.READY
    assert matrix[InferenceMethod.T2V] is CapabilityModeStatus.READY
    assert model.supported_resolutions == ("480p",)
    assert model.supported_durations == (4,)
    assert "future_operation" in model.unmapped_capability_keys


def test_future_documented_model_can_be_enriched_by_data_only() -> None:
    model = ModelCapabilities("future/documented", supports_text_only=True)
    assert (
        inference_method_matrix(model)[InferenceMethod.MMR2V]
        is CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
    )
    manifest = load_manifest()
    template = next(
        e for e in manifest["models"] if e["exact_model_id"] == "bytedance/seedance-2.5"
    )
    updated = {
        **manifest,
        "models": [{"exact_model_id": model.model_id, "facts": template["facts"]}],
    }
    enriched = enrich_capabilities(model, updated)
    assert inference_method_matrix(enriched)[InferenceMethod.MMR2V] is CapabilityModeStatus.READY
    assert enrich_capabilities(enriched, updated) == enriched


@pytest.mark.parametrize(
    "model_id",
    [
        "bytedance/seedance-2.0",
        "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0-mini",
    ],
)
def test_seedance_20_reference_caps_are_quarantined_as_stale_evidence(model_id: str) -> None:
    model = enrich_capabilities(ModelCapabilities(model_id))
    matrix = inference_method_matrix(model)
    for method in ("MI2V", "MMR2V"):
        projected = project_method(model, method)
        topology = projected["topology"]
        assert projected["state"] == "UNKNOWN"
        assert matrix[InferenceMethod(method)] is CapabilityModeStatus.UNKNOWN
        assert topology["max"] is None
        assert topology["per_kind_max"] == {}
        assert topology["constraint_state"] == "UNKNOWN"
        stale = topology["constraint_evidence"]
        for field, scope in (("max", "total"), ("per_kind_max", "per_kind")):
            assert stale[field]["state"] == "UNKNOWN"
            assert stale[field]["classification"] == "STALE_EVIDENCE"
            assert stale[field]["scope"] == scope
            assert "OpenRouter" in stale[field]["reason"]
    assert project_method(model, "VR2V")["state"] == "SUPPORTED"
    if model_id.endswith("mini") or model_id.endswith("fast"):
        assert project_method(model, "AR2V")["state"] == "CONFLICT"
    else:
        assert project_method(model, "AR2V")["state"] == "UNSUPPORTED"


def test_seedance_25_confirmed_method_and_reference_profile_remains_usable() -> None:
    full = enrich_capabilities(ModelCapabilities("bytedance/seedance-2.5"))
    assert full.input_reference_capabilities is not None
    assert full.input_reference_capabilities.max_reference_count == 50
    assert full.supports_edit and full.supports_extend
    assert enrich_capabilities(full) == full


def test_manifest_integrity_and_conflicts_remain_explicit(tmp_path: Path) -> None:
    import json

    manifest = load_manifest()
    ids = [model["exact_model_id"] for model in manifest["models"]]
    assert len(ids) == len(set(ids))
    assert "google/gemini-omni-1.2-flash" in ids
    manifest["artifact_version"] = "tampered"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="integrity"):
        load_manifest(path)
    contradictory = enrich_capabilities(
        replace(ModelCapabilities("bytedance/seedance-2.5"), supports_edit=False)
    )
    assert any(
        f.key == "supports_edit" and f.state.value == "CONFLICT"
        for f in contradictory.evidence_facts
    )
