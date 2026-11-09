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

from openrouter_video.capabilities import RequestValidator
from openrouter_video.client import OpenRouterVideoClient, _parse_capability
from openrouter_video.eligibility import eligible_methods, request_witness
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import CapabilityFactState, InferenceMethod
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


def test_every_selectable_historical_method_has_a_valid_serializer_witness() -> None:
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


@pytest.mark.parametrize("mid", ["google/gemini-omni-1.2-flash", "google/veo-3.1-lite"])
def test_reconciled_google_exact_shape_controls_and_mock_wire(mid: str) -> None:
    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-discovery-catalogue.json").read_text()
    )["data"]
    model = enrich_capabilities(_parse_capability(next(m for m in data if m["id"] == mid)))
    assert eligible_methods(model) == (
        InferenceMethod.T2V,
        InferenceMethod.I2V,
        InferenceMethod.FLF2V,
    )

    async def run() -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            return httpx.Response(202, json={"id": "TEST_ONLY_JOB", "status": "pending"})

        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            for method in eligible_methods(model):
                witness = request_witness(model, method)
                assert witness is not None
                await client.submit_video(witness)
                wire = seen[-1]
                assert (
                    wire["model"],
                    wire["duration"],
                    wire["resolution"],
                    wire["aspect_ratio"],
                ) == (mid, 8, "720p", "16:9")
                assert (
                    len(wire.get("frame_images", []))
                    == {"T2V": 0, "I2V": 1, "FLF2V": 2}[method.value]
                )
                assert not {
                    "seed",
                    "generate_audio",
                    "size",
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
        expected = raw["id"] in {"google/gemini-omni-1.2-flash", "google/veo-3.1-lite"}
        assert bool(eligible_methods(model)) == expected


def test_google_frontend_fixture_matches_real_core_projection() -> None:
    from openrouter_video.comfy.projection import project_selectable

    fixture = Path(__file__).parents[1] / "fixtures"
    raw = json.loads((fixture / "op07-discovery-catalogue.json").read_text())["data"]
    expected = json.loads((fixture / "op07-google-ui-projection.json").read_text())["models"]
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
        "google/gemini-omni-1.2-flash"
    }
    for model in before["models"]:
        if model["exact_model_id"] != "google/veo-3.1-lite":
            assert mapping[model["exact_model_id"]] == model


@pytest.mark.parametrize("mid", ["google/gemini-omni-1.2-flash", "google/veo-3.1-lite"])
def test_google_bounded_profile_does_not_enable_omission_or_unproven_combinations(mid: str) -> None:
    from openrouter_video.errors import ProductFailureError
    from openrouter_video.models import GenerationRequest

    data = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-discovery-catalogue.json").read_text()
    )["data"]
    raw = next(m for m in data if m["id"] == mid)
    model = enrich_capabilities(_parse_capability(raw))
    witness = request_witness(model, InferenceMethod.T2V)
    assert witness is not None
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(replace(witness, duration=None), model)
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            GenerationRequest(mid, "prompt", duration=10), model
        )
    raw["supported_durations"] = [5]
    assert not eligible_methods(enrich_capabilities(_parse_capability(raw)))


def test_eligibility_compatibility_exports_have_no_independent_implementation() -> None:
    from openrouter_video import capabilities, eligibility

    assert eligibility.request_witness is capabilities.request_witness
    assert eligibility.eligible_methods is capabilities.eligible_methods
    assert request_witness.__module__ == "openrouter_video.capabilities"
