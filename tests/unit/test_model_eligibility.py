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
    RequestValidator,
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


def test_documented_seedance_methods_are_selectable_and_wire_compatible() -> None:
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
            assert method.value in executable
            witness = request_witness(model, method)
            assert witness is not None
            assert profile["topology"]["execution_domain"] == "CONFIRMED_BOUNDS"
            expected = (
                {"image": 9}
                if method is InferenceMethod.MI2V
                else {
                    "image": 9,
                    "video": 3,
                    "audio": 3,
                }
            )
            assert profile["topology"]["per_kind_max"] == expected
            assert profile["topology"]["max"] == sum(expected.values())
            RequestValidator().validate_shape(witness)
            RequestValidator().validate_capabilities(witness, model)


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
        # OP-07 documentation-first native/OpenRouter reconciliation for Wan 3.
        "alibaba/wan-3.0",
        "alibaba/wan-3.0-prime",
        # OP-07 and documentation-first continuation: Seedance reference ceilings
        # are compatible with the OpenRouter input_references wire and are enforced.
        "bytedance/seedance-2.0",
        "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0-mini",
    }
    seedance_documented_bounds = {
        "bytedance/seedance-2.0",
        "bytedance/seedance-2.0-fast",
        "bytedance/seedance-2.0-mini",
    }
    for model in before["models"]:
        model_id = model["exact_model_id"]
        if model_id == "alibaba/happyhorse-1.1":
            assert_happyhorse_11_reference_methods(mapping[model_id])
        if model_id in {"alibaba/wan-3.0", "alibaba/wan-3.0-prime"}:
            assert_wan_3_documented_methods(mapping[model_id])
        if model_id in seedance_documented_bounds:
            assert_seedance_documented_reference_caps(model, mapping[model_id])
            assert_reconciled_scalar_delta(
                model, mapping[model_id], allow_documented_seedance_reference_caps=True
            )
        elif model_id not in reviewed_delta:
            assert_reconciled_scalar_delta(
                model,
                mapping[model["exact_model_id"]],
                allow_happyhorse_11_reference_methods=(model_id == "alibaba/happyhorse-1.1"),
            )


def assert_happyhorse_11_reference_methods(model: dict[str, Any]) -> None:
    """Pin the documentation-first I2V reference ceilings and normalized fields."""
    from openrouter_video.configuration import project_method
    from openrouter_video.evidence_registry import enrich_capabilities

    effective = enrich_capabilities(ModelCapabilities(model["exact_model_id"]))
    expected = {"IR2V": (1, {"image": 1}), "MI2V": (9, {"image": 9})}
    for method, (maximum, per_kind) in expected.items():
        profile = project_method(effective, method)
        assert profile["state"] == profile["method_support"] == "SUPPORTED"
        assert profile["topology"]["max"] == maximum
        assert profile["topology"]["per_kind_max"] == per_kind
        assert profile["topology"]["constraint_evidence"]["max"]["classification"] == (
            "DERIVED_PER_KIND_CEILING"
        )
        assert profile["controls"]["size"]["state"] == "UNKNOWN"
        assert profile["controls"]["aspect_ratio"]["state"] == "SUPPORTED"
        assert set(profile["controls"]["aspect_ratio"]["values"]) == set(
            ("16:9", "9:16", "3:4", "4:3", "1:1", "9:21", "21:9")
        )


def assert_wan_3_documented_methods(model: dict[str, Any]) -> None:
    """Pin the reviewed Wan 3 method and ratio additions and keep their history."""
    model_id = model["exact_model_id"]
    methods = model["facts"]["request_shape_profiles"]["value"]["methods"]
    if model_id.endswith("prime"):
        assert "reference_kinds" not in model["facts"]
        assert "mixed_reference_kinds" not in model["facts"]
        expected_supported = {"T2V", "I2V"}
    else:
        assert model["facts"]["reference_kinds"]["value"] == ["image", "video", "audio"]
        assert model["facts"]["mixed_reference_kinds"]["value"] is True
        expected_supported = {
            "T2V",
            "I2V",
            "FLF2V",
            "IR2V",
            "MI2V",
            "VR2V",
            "AR2V",
            "MMR2V",
        }
    assert {name for name, value in methods.items() if value["state"] == "SUPPORTED"} == (
        expected_supported
    )
    ratio_methods = {"I2V"} if model_id.endswith("prime") else {"I2V", "FLF2V"}
    for method in ratio_methods:
        profile = methods[method]
        ratio = profile["controls"]["aspect_ratio"]
        assert ratio["state"] == "UNKNOWN"
        assert ratio["evidence_class"] == "ABSENCE_ONLY"
        assert "official Wan3 API supports output ratio" in ratio["notes"]
        assert any(
            item.get("control") == "aspect_ratio"
            and "Source image owns native aspect" in item.get("superseded_note", "")
            for item in profile.get("historical_findings", [])
        )


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


def assert_seedance_documented_reference_caps(
    before: dict[str, Any], after: dict[str, Any]
) -> None:
    """Documented compatible provider limits are enforced, not labeled live-tested."""
    model_id = before["exact_model_id"]
    methods = after["facts"]["request_shape_profiles"]["value"]["methods"]
    for method in ("MI2V", "VR2V", "MMR2V"):
        profile = methods[method]
        expected = {
            "MI2V": {"image": 9},
            "VR2V": {"video": 3},
            "MMR2V": {"image": 9, "video": 3, "audio": 3},
        }[method]
        assert profile["state"] == "SUPPORTED"
        assert profile["topology"]["max"] == sum(expected.values())
        assert profile["topology"]["per_kind_max"] == expected
        assert profile["topology"]["constraint_evidence"]["max"]["classification"] == (
            "DERIVED_PER_KIND_CEILING"
        )
        assert profile["topology"]["constraint_evidence"]["per_kind_max"]["classification"] == (
            "PROVIDER_DOCUMENTED_COMPATIBLE"
        )
    # Mini history remains preserved as a witnessed example, not an exclusive ceiling.
    if model_id.endswith("mini"):
        assert methods["MMR2V"]["topology"]["verified_configurations"] == [
            {"image": 1, "video": 1, "audio": 1}
        ]


def assert_reconciled_scalar_delta(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    allow_documented_seedance_reference_caps: bool = False,
    allow_happyhorse_11_reference_methods: bool = False,
) -> None:
    """Current positive scalar reconciliation cannot alter topology or other facts."""
    import copy

    catalogue = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text(encoding="utf8")
    )["data"]
    raw = next(m for m in catalogue if m["id"] == before["exact_model_id"])
    restored = copy.deepcopy(after)
    if allow_documented_seedance_reference_caps:
        assert before["exact_model_id"] in {
            "bytedance/seedance-2.0",
            "bytedance/seedance-2.0-fast",
            "bytedance/seedance-2.0-mini",
        }
        profile = restored["facts"]["request_shape_profiles"]
        profile["scope"] = before["facts"]["request_shape_profiles"]["scope"]
    old_methods = before["facts"]["request_shape_profiles"]["value"]["methods"]
    new_methods = restored["facts"]["request_shape_profiles"]["value"]["methods"]
    profile_scope = restored["facts"]["request_shape_profiles"]["scope"]
    old_scope = before["facts"]["request_shape_profiles"]["scope"]
    if profile_scope != old_scope:
        assert profile_scope == (
            f"{old_scope}; documentation-first reference-domain delta 2026-11-12 "
            "(see method review_sources; no live verification claim)."
        )
        restored["facts"]["request_shape_profiles"]["scope"] = old_scope
    for method, old in old_methods.items():
        new = new_methods[method]
        if allow_happyhorse_11_reference_methods and method in {"IR2V", "MI2V"}:
            assert before["exact_model_id"] == "alibaba/happyhorse-1.1"
            assert new["state"] == "SUPPORTED"
            assert new["topology"]["max"] == (1 if method == "IR2V" else 9)
            assert new["topology"]["per_kind_max"] == {"image": 1 if method == "IR2V" else 9}
            assert new["controls"]["aspect_ratio"]["state"] == "SUPPORTED"
            assert new["controls"]["size"]["state"] == "UNKNOWN"
            new_methods[method] = old
            new = old
        historical = new.pop("historical_findings", None)
        if historical is not None:
            assert before["exact_model_id"] in {"alibaba/wan-3.0", "alibaba/wan-3.0-prime"}
            assert method == "I2V" or (
                before["exact_model_id"] == "alibaba/wan-3.0" and method == "FLF2V"
            )
            assert any(
                item.get("control") == "aspect_ratio"
                and "Source image owns native aspect" in item.get("superseded_note", "")
                for item in historical
            )
        if new.get("evidence_class") == "ABSENCE_ONLY":
            assert new["state"] == "UNKNOWN"
            new.pop("evidence_class")
        # These typed historical UNKNOWN stubs explicitly describe absence of
        # evidence. They do not change a control's effective state or domain.
        controls = new.get("controls", {})
        old_controls = old.get("controls", {})
        for control, current in list(controls.items()):
            if current.get("evidence_class") == "ABSENCE_ONLY":
                assert current["state"] == "UNKNOWN"
                if control in old_controls:
                    assert old_controls[control]["state"] == "UNKNOWN"
                    controls[control] = old_controls[control]
                else:
                    controls.pop(control)
        if allow_documented_seedance_reference_caps and method in {"MI2V", "MMR2V", "VR2V"}:
            assert new["state"] == "SUPPORTED"
            expected_limits = {
                "MI2V": ({"image": 9}, 9),
                "VR2V": ({"video": 3}, 3),
                "MMR2V": ({"image": 9, "video": 3, "audio": 3}, 15),
            }
            expected_per_kind, expected_total = expected_limits[method]
            assert new["topology"]["per_kind_max"] == expected_per_kind
            assert new["topology"]["max"] == expected_total
            assert new["topology"]["constraint_evidence"]["max"]["classification"] == (
                "DERIVED_PER_KIND_CEILING"
            )
            assert new["topology"]["constraint_evidence"]["per_kind_max"]["classification"] == (
                "PROVIDER_DOCUMENTED_COMPATIBLE"
            )
            if "method_support" in new:
                assert new["method_support"] == "SUPPORTED"
                if "method_support" not in old:
                    new.pop("method_support")
            new["topology"] = old["topology"]
            new["topology_scope"] = old.get("topology_scope")
            if new.get("topology_scope") is None:
                new.pop("topology_scope", None)
            new["state"] = old["state"]
            new["notes"] = old.get("notes")
            if new.get("notes") is None:
                new.pop("notes", None)
        if allow_documented_seedance_reference_caps and method == "AR2V":
            assert new["state"] == "UNSUPPORTED"
            assert "Provider documentation excludes audio-only input" in new.get("notes", "")
            old_conformance = before["facts"].get("inference_method_conformance")
            assert after["facts"].get("inference_method_conformance") == old_conformance
            if old_conformance is not None:
                assert old_conformance["value"]["method"] == "AR2V"
            new_methods[method] = old
            new = old
        if old.get("controls", {}).get("aspect_ratio") != new.get("controls", {}).get(
            "aspect_ratio"
        ):
            if (
                before["exact_model_id"] == "alibaba/happyhorse-1.1"
                and method in {"IR2V", "MI2V"}
                and "aspect_ratio" not in old.get("controls", {})
            ):
                assert new["controls"]["aspect_ratio"]["state"] == "SUPPORTED"
                assert set(new["controls"]["aspect_ratio"]["values"]) == set(
                    raw["supported_aspect_ratios"]
                )
                new["controls"].pop("aspect_ratio")
            else:
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
