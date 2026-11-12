import asyncio
import copy
import json
import shutil
import subprocess
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from openrouter_video.capabilities import (
    CapabilityModeStatus,
    RequestValidator,
    inference_method_matrix,
)
from openrouter_video.client import OpenRouterVideoClient, _parse_capability
from openrouter_video.comfy.projection import project_selectable
from openrouter_video.configuration import project_method
from openrouter_video.eligibility import eligible_methods, request_witness
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import CapabilityFactState, InferenceMethod, ModelCapabilities
from openrouter_video.transport import HttpxTransport
from tests.projection_fixtures import synthetic_projected_model
from tests.unit.test_client import _policy


@pytest.mark.parametrize("state", ["UNKNOWN", "UNSUPPORTED", "CONFLICT"])
def test_nonpositive_methods_never_selectable(state: str) -> None:
    model = synthetic_projected_model("new/not-whitelisted")
    fact = model.evidence_facts[0]
    profile = copy.deepcopy(cast(dict[str, Any], fact.value))
    for value in profile["methods"].values():
        value["state"] = state
    model = replace(model, evidence_facts=(replace(fact, value=profile),))
    assert eligible_methods(model) == ()


def test_new_id_auto_activates_only_with_confirmed_shapes_and_not_price() -> None:
    model = synthetic_projected_model("new/not-whitelisted")
    assert model.pricing_evidence is None
    assert eligible_methods(model)
    assert eligible_methods(replace(model, evidence_facts=())) == ()
    assert (
        eligible_methods(
            replace(
                model,
                evidence_facts=(
                    replace(model.evidence_facts[0], state=CapabilityFactState.CONFLICT),
                ),
            )
        )
        == ()
    )


def test_supported_label_without_required_prompt_or_media_is_not_enough() -> None:
    model = synthetic_projected_model()
    fact = model.evidence_facts[0]
    profile = copy.deepcopy(cast(dict[str, Any], fact.value))
    for value in profile["methods"].values():
        value["controls"]["prompt"]["state"] = "UNKNOWN"
    assert not eligible_methods(replace(model, evidence_facts=(replace(fact, value=profile),)))


def test_partial_support_and_roundtrip_through_real_mock_client() -> None:
    model = synthetic_projected_model("new/not-whitelisted")
    fact = model.evidence_facts[0]
    profiles = copy.deepcopy(cast(dict[str, Any], fact.value))
    for method, value in profiles["methods"].items():
        if method not in ["T2V", "I2V", "FLF2V"]:
            value["state"] = "UNKNOWN"
    model = replace(model, evidence_facts=(replace(fact, value=profiles),))
    assert eligible_methods(model) == (
        InferenceMethod.T2V,
        InferenceMethod.I2V,
        InferenceMethod.FLF2V,
    )

    async def run() -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            return httpx.Response(202, json={"id": "TEST_JOB", "status": "pending"})

        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            for method in eligible_methods(model):
                witness = request_witness(model, method)
                assert witness is not None
                RequestValidator().validate_capabilities(witness, model)
                await client.submit_video(witness)
                assert calls[-1] == witness.to_openrouter_payload()
                assert "inference_method" not in calls[-1]
        assert len(calls) == 3  # MockTransport only; zero real POST.

    asyncio.run(run())


def test_every_executable_historical_method_has_a_valid_serializer_witness() -> None:
    fixture = Path(__file__).parents[1] / "fixtures/capability-audit-catalogue.json"
    models = json.loads(fixture.read_text(encoding="utf-8"))["models"]
    for raw in models:
        model = enrich_capabilities(_parse_capability(raw))
        for method in eligible_methods(model):
            witness = request_witness(model, method)
            assert witness is not None
            RequestValidator().validate_shape(witness)
            RequestValidator().validate_capabilities(witness, model)
            assert witness.to_openrouter_payload()["model"] == model.model_id


def test_documented_unverified_seedance_methods_are_selectable_but_not_executable() -> None:
    for model_id in (
        "bytedance/seedance-2.0",
        "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0-mini",
    ):
        model = enrich_capabilities(ModelCapabilities(model_id))
        selectable = project_selectable(
            model, datetime(2026, 11, 12, tzinfo=timezone.utc)
        ).as_dict()
        selectable_methods = cast(list[str], selectable["supported_inference_methods"])
        assert "MI2V" in selectable_methods
        assert "MMR2V" in selectable_methods
        executable = {method.value for method in eligible_methods(model)}
        for method in (InferenceMethod.MI2V, InferenceMethod.MMR2V):
            profile = project_method(model, method.value)
            assert profile["state"] == profile["method_support"] == "SUPPORTED"
            if model_id.endswith("mini") and method is InferenceMethod.MMR2V:
                assert method.value in executable
                witness = request_witness(model, method)
                assert witness is not None
                assert profile["topology"]["execution_domain"] == "VERIFIED_CONFIGURATIONS"
            else:
                assert method.value not in executable
                assert request_witness(model, method) is None
                assert profile["topology"]["execution_domain"] == "UNVERIFIED"
                assert "verified_configurations" not in profile["topology"]


@pytest.mark.parametrize("mid", ["google/gemini-omni-1.2-flash", "google/veo-3.1-lite"])
def test_reconciled_google_exact_shape_controls_and_mock_wire(mid: str) -> None:
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-discovery-catalogue.json").read_text()
    )["data"]
    model = enrich_capabilities(_parse_capability(next(m for m in data if m["id"] == mid)))
    standard = (
        InferenceMethod.T2V,
        InferenceMethod.I2V,
        InferenceMethod.FLF2V,
    )

    assert set(standard) <= set(eligible_methods(model))

    async def run() -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(202, json={"id": "TEST_ONLY_JOB", "status": "pending"})

        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            for method in standard:
                witness = request_witness(model, method)
                assert witness is not None
                await client.submit_video(witness)
                wire = seen[-1]
                assert wire["model"] == mid
                assert model.supported_durations is not None
                assert model.supported_resolutions is not None
                assert model.supported_aspect_ratios is not None
                assert wire["duration"] in model.supported_durations
                assert wire["resolution"] in model.supported_resolutions
                assert wire["aspect_ratio"] in model.supported_aspect_ratios
                assert (
                    len(wire.get("frame_images", []))
                    == {"T2V": 0, "I2V": 1, "FLF2V": 2}[method.value]
                )
                assert not {
                    "provider",
                    "input_references",
                    "previous_job_id",
                }.intersection(wire)
        assert len(seen) == 3

    asyncio.run(run())


def test_ten_models_remain_discovered_and_unresolved_findings_are_not_painted_supported() -> None:
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-discovery-catalogue.json").read_text()
    )["data"]
    assert len(data) == 10
    for raw in data:
        model = enrich_capabilities(_parse_capability(raw))
        assert eligible_methods(model)
        if raw["id"] == "kwaivgi/kling-v3.0-pro":
            assert InferenceMethod.T2V in eligible_methods(model)
            from openrouter_video.configuration import project_method

            assert project_method(model, "T2V")["controls"]["resolution"]["state"] == "CONFLICT"


def test_google_frontend_fixture_matches_real_core_projection() -> None:
    from openrouter_video.comfy.projection import project_selectable

    fixture = Path(__file__).parents[1] / "fixtures"
    raw = json.loads((fixture / "op07-full-catalogue.json").read_text())["data"]
    expected = json.loads((fixture / "op07-full-parity-ui-projection.json").read_text())["models"]
    for view in expected:
        model = enrich_capabilities(
            _parse_capability(next(m for m in raw if m["id"] == view["model_id"]))
        )
        actual = project_selectable(model, datetime(2026, 11, 8, tzinfo=timezone.utc)).as_dict()
        actual.pop("capability_evidence")
        assert json.loads(json.dumps(actual)) == view


def test_op07_evidence_delta_preserves_every_other_model_and_historical_conflict() -> None:
    git = shutil.which("git")
    assert git is not None
    before = json.loads(
        subprocess.check_output(  # noqa: S603 - fixed local Git tree
            [
                git,
                "show",
                "058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9:src/openrouter_video/data/capability-evidence.json",
            ],
            text=True,
            encoding="utf-8",
        )
    )
    from openrouter_video.evidence_registry import load_manifest

    after = load_manifest()
    mapping = {m["exact_model_id"]: m for m in after["models"]}
    assert set(mapping) - {m["exact_model_id"] for m in before["models"]} == {
        "google/gemini-omni-1.2-flash",
        "google/gemini-omni-1.1-flash",
        "tbc/mischief-1",
    }
    reviewed_delta = {
        "google/veo-3.1-lite",
        "kwaivgi/kling-video-o1",
        "kwaivgi/kling-v3.0-pro",
        "kwaivgi/kling-v3.0-std",
        "black-forest-labs/flux-video-edit",
        "black-forest-labs/flux-video-upscale",
        "heygen/avatar-iv",
        "heygen/heygen-video-1",
        "runway/aleph-2",
        # Owner full-catalogue continuation: documented provider schemas and
        # MiniMax conditional prompt/duration rules, covered in focused tests.
        "runway/gen-4.5",
        "black-forest-labs/flux-3-video",
        "minimax/hailuo-2.3",
        "minimax/hailuo-3",
        "minimax/hailuo-3-max",
        "alibaba/wan-2.6",
        "alibaba/wan-2.7",
        # OP-07: preserve documented MI2V/MMR2V method support while keeping
        # unknown counts out of executable witnesses; do not promote native 9/3/3.
        "bytedance/seedance-2.0",
        "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0-mini",
    }
    seedance_quarantine = {
        "bytedance/seedance-2.0",
        "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0-mini",
    }
    for model in before["models"]:
        model_id = model["exact_model_id"]
        if model_id in seedance_quarantine:
            assert_seedance_reference_caps_quarantined(model, mapping[model_id])
            assert_reconciled_scalar_delta(
                model, mapping[model_id], allow_stale_seedance_reference_caps=True
            )
        elif model_id not in reviewed_delta:
            assert_reconciled_scalar_delta(model, mapping[model["exact_model_id"]])


@pytest.mark.parametrize("mid", ["google/gemini-omni-1.2-flash", "google/veo-3.1-lite"])
def test_google_known_constraints_and_dynamic_domains(mid: str) -> None:
    from openrouter_video.errors import ProductFailureError

    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-discovery-catalogue.json").read_text()
    )["data"]
    raw = next(m for m in data if m["id"] == mid)
    model = enrich_capabilities(_parse_capability(raw))
    witness = request_witness(model, InferenceMethod.FLF2V)
    assert witness is not None
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(replace(witness, duration=15), model)
    if mid == "google/veo-3.1-lite":
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(replace(witness, duration=4), model)
    raw["supported_durations"] = [5]
    available = eligible_methods(enrich_capabilities(_parse_capability(raw)))
    assert bool(available) == (mid != "google/veo-3.1-lite")


def test_eligibility_compatibility_exports_have_no_independent_implementation() -> None:
    from openrouter_video import capabilities, eligibility

    assert eligibility.request_witness is capabilities.request_witness
    assert eligibility.eligible_methods is capabilities.eligible_methods
    assert request_witness.__module__ == "openrouter_video.capabilities"


def assert_seedance_reference_caps_quarantined(
    before: dict[str, Any], after: dict[str, Any]
) -> None:
    """The old 3-valued fields stay visible as stale evidence, never as effective limits."""
    model_id = before["exact_model_id"]
    old_profile = before["facts"]["request_shape_profiles"]
    new_profile = after["facts"]["request_shape_profiles"]
    assert new_profile["scope"].startswith(f"{old_profile['scope']};")
    assert "method support retained" in new_profile["scope"]
    assert "only exact historical Mini I+V+A configuration re-admitted" in new_profile["scope"]

    old_methods = old_profile["value"]["methods"]
    new_methods = new_profile["value"]["methods"]
    for method in ("MI2V", "MMR2V"):
        old_method = old_methods[method]
        new_method = new_methods[method]
        assert new_method["state"] == "SUPPORTED"
        old_topology = old_method["topology"]
        new_topology = new_method["topology"]
        assert new_topology["max"] == old_topology["max"] == 3
        assert new_topology["per_kind_max"] == old_topology["per_kind_max"]
        assert set(new_topology) - set(old_topology) <= {
            "constraint_evidence",
            "verified_configurations",
        }
        expected_verified = (
            [{"image": 1, "video": 1, "audio": 1}]
            if model_id.endswith("mini") and method == "MMR2V"
            else []
        )
        if expected_verified:
            assert new_topology["verified_configurations"] == expected_verified
        else:
            assert "verified_configurations" not in new_topology
        evidence = new_topology["constraint_evidence"]
        for field, scope in (("max", "total"), ("per_kind_max", "per_kind")):
            item = evidence[field]
            assert item["state"] == "UNKNOWN"
            assert item["classification"] == "STALE_EVIDENCE"
            assert item["scope"] == scope
            assert item["source"] == (
                "https://openrouter.ai/docs/guides/overview/multimodal/video-generation"
            )
            assert "native video3 does not establish total3 or image3" in item["reason"]

    effective = enrich_capabilities(ModelCapabilities(model_id))
    for method in (InferenceMethod.MI2V, InferenceMethod.MMR2V):
        assert inference_method_matrix(effective)[method] is CapabilityModeStatus.READY
        projected = project_method(effective, method.value)
        assert projected["state"] == projected["method_support"] == "SUPPORTED"
        topology = projected["topology"]
        assert topology["max"] is None
        assert topology["per_kind_max"] == {}
        assert topology["limit_completeness"] == (
            "PARTIAL"
            if model_id.endswith("mini") and method is InferenceMethod.MMR2V
            else "UNKNOWN"
        )
        assert topology["execution_domain"] == (
            "VERIFIED_CONFIGURATIONS"
            if model_id.endswith("mini") and method is InferenceMethod.MMR2V
            else "UNVERIFIED"
        )
        witness = request_witness(effective, method)
        assert (witness is not None) == (
            model_id.endswith("mini") and method is InferenceMethod.MMR2V
        )


def assert_reconciled_scalar_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    allow_stale_seedance_reference_caps: bool = False,
) -> None:
    """Current positive scalar reconciliation cannot alter topology or other facts."""
    import copy

    catalogue = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text(encoding="utf8")
    )["data"]
    raw = next(m for m in catalogue if m["id"] == before["exact_model_id"])
    restored = copy.deepcopy(after)
    if allow_stale_seedance_reference_caps:
        assert before["exact_model_id"] in {
            "bytedance/seedance-2.0",
            "bytedance/seedance-2.0-fast",
            "bytedance/seedance-2.0-mini",
        }
        profile = restored["facts"]["request_shape_profiles"]
        profile["scope"] = before["facts"]["request_shape_profiles"]["scope"]
    old_methods = before["facts"]["request_shape_profiles"]["value"]["methods"]
    new_methods = restored["facts"]["request_shape_profiles"]["value"]["methods"]
    for method, old in old_methods.items():
        new = new_methods[method]
        if allow_stale_seedance_reference_caps and method in {"MI2V", "MMR2V"}:
            assert new["state"] == "SUPPORTED"
            if "method_support" in new:
                assert new["method_support"] == "SUPPORTED"
                if "method_support" not in old:
                    new.pop("method_support")
            new["state"] = old["state"]
            new["topology"] = old["topology"]
            if new.get("notes") != old.get("notes"):
                new["notes"] = old.get("notes")
        if old.get("controls", {}).get("aspect_ratio") != new.get("controls", {}).get(
            "aspect_ratio"
        ):
            assert old["controls"]["aspect_ratio"]["state"] == "UNKNOWN"
            assert new["controls"]["aspect_ratio"]["state"] == "UNSUPPORTED"
            assert (before["exact_model_id"], method) in {
                ("x-ai/grok-imagine-video-1.5-lite", "I2V"),
                ("x-ai/grok-imagine-video-1.5", "I2V"),
                ("x-ai/grok-imagine-video", "I2V"),
                ("alibaba/happyhorse-1.0", "I2V"),
                ("alibaba/happyhorse-1.1", "I2V"),
            }
            new["controls"]["aspect_ratio"] = old["controls"]["aspect_ratio"]
        if before["exact_model_id"] != "bytedance/seedance-2.0" and (
            old.get("controls", {}).get("size") != new.get("controls", {}).get("size")
        ):
            assert old["controls"]["size"]["state"] == "UNKNOWN"
            assert new["controls"]["size"]["state"] == "SUPPORTED"
            assert new["controls"]["size"]["values"] == raw["supported_sizes"]
            assert all(
                old["controls"][axis]["state"] == "SUPPORTED"
                for axis in ("resolution", "aspect_ratio")
            )
            for relation in old.get("relations", []):
                scope = relation.get("when", {}).get("inference_method", [method])
                scope = scope if isinstance(scope, list) else [scope]
                if method in scope:
                    assert not {"resolution", "aspect_ratio"} & set(relation["axes"])
            assert (before["exact_model_id"], method) != ("x-ai/grok-imagine-video", "IR2V")
            new["controls"]["size"] = old["controls"]["size"]
        if "provider_options" in new.get("controls", {}) and "provider_options" not in old.get(
            "controls", {}
        ):
            supported = new["controls"].pop("provider_options")
            assert supported["state"] == "SUPPORTED"
            for provider, options in supported["providers"].items():
                assert provider in {"seed", "google-vertex"}
                assert set(options) <= set(raw["allowed_passthrough_parameters"])
                assert set(options) <= {
                    "watermark",
                    "negativePrompt",
                    "enhancePrompt",
                    "output_format",
                }
                if "output_format" in options:
                    assert before["exact_model_id"] == "bytedance/seedance-2.5"
                    assert options["output_format"] == {
                        "type": "string",
                        "values": ["mp4", "mov"],
                        "omitted_default": "mp4",
                    }
        for control, flag in (("seed", "seed"), ("generate_audio", "generate_audio")):
            if old.get("controls", {}).get(control) != new.get("controls", {}).get(control):
                assert raw.get(flag) is True
                assert old["controls"][control]["state"] == "UNKNOWN"
                assert new["controls"][control]["state"] == "SUPPORTED"
                new["controls"][control] = old["controls"][control]
        if before["exact_model_id"] == "bytedance/seedance-2.0" and old["state"] == "SUPPORTED":
            for control, field in (
                ("resolution", "supported_resolutions"),
                ("size", "supported_sizes"),
            ):
                assert new["controls"][control]["values"] == raw[field]
                new["controls"][control] = old["controls"][control]
        if "review_sources" in new:
            assert set(old.get("review_sources", [])) <= set(new["review_sources"])
            new["review_sources"] = old.get("review_sources", [])
    assert restored == before
