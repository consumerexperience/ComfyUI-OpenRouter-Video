# mypy: disable-error-code="attr-defined,arg-type"
import asyncio
import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from openrouter_video.capabilities import CapabilityObservation, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy import nodes, runtime
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import (
    GenerationRequest,
    GenerationResult,
    InferenceMethod,
    InputReferenceKind,
    LocalLifecycleState,
    PricingEvidence,
    PricingSku,
    VideoArtifact,
)
from openrouter_video.pricing import (
    CostEstimateInputs,
    EstimateAvailability,
    PreflightCostEstimator,
)

ROOT = Path(__file__).parents[2]
CATALOGUE = json.loads(
    (ROOT / "tests/fixtures/capability-audit-catalogue.json").read_text(encoding="utf-8")
)


def model(slug: str) -> Any:
    return enrich_capabilities(
        _parse_capability(next(raw for raw in CATALOGUE["models"] if raw["id"] == slug))
    )


def test_known_model_legacy_bridge_never_omits_active_image_charges() -> None:
    capability = replace(
        model("x-ai/grok-imagine-video"),
        pricing_evidence=PricingEvidence((PricingSku("per-video-second-720p", Decimal("0.03")),)),
    )
    assert request_witness(capability, InferenceMethod.IR2V) is not None
    result = PreflightCostEstimator().estimate(
        capability,
        CostEstimateInputs(
            capability.model_id,
            duration=1,
            resolution="720p",
            aspect_ratio="16:9",
            inference_method=InferenceMethod.IR2V,
            reference_kinds=(InputReferenceKind.IMAGE,),
            reference_count=1,
        ),
        observed_at=datetime.now(timezone.utc),
    )
    assert result.state.value == "UNKNOWN"
    assert result.estimated_cost_usd is result.amount_usd is None
    assert result.reason == "legacy_pricing_scope_unverified"


def test_known_model_legacy_bridge_preserves_unresolved_long_duration_relations() -> None:
    # This retained discovery capture has the actual 5..30 second domain; the
    # older general UI-audit fixture above predates the long-duration capability.
    captured = json.loads(
        (ROOT / "tests/fixtures/op07-topology-catalogue-b628912.json").read_text(encoding="utf8")
    )
    capability = enrich_capabilities(
        _parse_capability(
            next(raw for raw in captured["data"] if raw["id"] == "heygen/heygen-video-1")
        )
    )
    assert 20 in capability.supported_durations
    inputs = CostEstimateInputs(
        capability.model_id,
        duration=20,
        resolution="480p",
        aspect_ratio="16:9",
    )
    estimator = PreflightCostEstimator()
    observed = datetime.now(timezone.utc)
    current = estimator.estimate(capability, inputs, observed_at=observed)
    assert current.state.value == "PARTIAL" and current.estimated_cost_usd is None
    legacy = replace(
        capability,
        pricing_evidence=PricingEvidence((PricingSku("per-video-second-480p", Decimal("0.03")),)),
    )
    result = estimator.estimate(legacy, inputs, observed_at=observed)
    assert result.state.value == "UNKNOWN"
    assert result.estimated_cost_usd is result.amount_usd is None
    assert result.reason == "legacy_pricing_scope_unverified"


def test_hidden_raw_seed_and_media_are_omitted_before_any_encoder_or_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = model("x-ai/grok-imagine-video-1.5-lite")
    captured: list[GenerationRequest] = []

    class Runtime:
        async def effective_catalog(self) -> CapabilityObservation:
            return CapabilityObservation(datetime.now(timezone.utc), (capability,))

        async def generate(self, request: GenerationRequest, node_id: object) -> GenerationResult:
            captured.append(request)
            return GenerationResult(
                LocalLifecycleState.DONE,
                "TEST_ONLY_JOB",
                artifact=VideoArtifact(Path("test-only.mp4"), "video/mp4", 1),
            )

    def forbidden(*_: object) -> None:
        pytest.fail("Hidden media must never reach an encoder or bridge")

    def seed_parser(raw: object) -> None:
        assert raw is None  # malformed hidden input never reaches parsing

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "native_reference", forbidden)
    monkeypatch.setattr(nodes, "to_image_data_url", forbidden)
    monkeypatch.setattr(nodes, "_seed", seed_parser)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "TEST_ONLY_NATIVE_VIDEO")
    asyncio.run(
        nodes.OpenRouterVideoGenerate.execute(
            capability.model_id,
            "test",
            inference_method="T2V",
            duration=1,
            resolution="480p",
            aspect_ratio="16:9",
            seed="private-malformed-canary",
            generate_audio=True,
            size="stale-value",
            first_frame=object(),
            last_frame=object(),
            source_video=object(),
            direct_references={"reference_0": object()},
            input_references=object(),
        )
    )
    request = captured[0]
    assert all(
        getattr(request, name) is None
        for name in (
            "seed",
            "generate_audio",
            "size",
            "first_frame",
            "last_frame",
            "source_video",
            "input_references",
        )
    )
    assert not {"generate_audio", "seed", "size", "frame_images", "input_references"}.intersection(
        request.to_openrouter_payload()
    )


@pytest.mark.parametrize("method", ["AR2V", "INVALID"])
def test_nonprojected_explicit_method_cannot_activate_media_or_reach_generate(
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = model("bytedance/seedance-2.0-mini")

    class Runtime:
        async def effective_catalog(self) -> CapabilityObservation:
            return CapabilityObservation(datetime.now(timezone.utc), (capability,))

        async def generate(self, *_: object) -> None:
            pytest.fail("Blocked method must not acquire generation authority")

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "native_reference", lambda *_: pytest.fail("Must not encode"))
    with pytest.raises(nodes.AdapterExecutionError):
        asyncio.run(
            nodes.OpenRouterVideoGenerate.execute(
                capability.model_id,
                "test",
                inference_method=method,
                direct_references={"reference_0": object()},
            )
        )


def test_estimator_consumes_same_omitted_semantics_and_never_contacts_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capability = replace(
        model("x-ai/grok-imagine-video"),
        pricing_evidence=PricingEvidence((PricingSku("per-video-second-480p", Decimal("0.03")),)),
    )
    observed = datetime.now(timezone.utc)

    class Capabilities:
        async def effective_catalog(self) -> CapabilityObservation:
            return CapabilityObservation(observed, (capability,))

        def is_fresh(self, _: object) -> bool:
            return True

    def forbidden(_: httpx.Request) -> httpx.Response:
        pytest.fail("Projection/estimate must not issue HTTP")

    monkeypatch.setattr(
        runtime.HttpxTransport,
        "create",
        classmethod(lambda cls: cls.for_test(httpx.MockTransport(forbidden))),
    )
    monkeypatch.setattr(runtime.compat, "host_interrupted", lambda: False)

    async def scenario() -> None:
        process = runtime.ProcessRuntime(tmp_path / "jobs.sqlite3", tmp_path / "output")
        try:
            process._resources = replace(process._require_resources(), capabilities=Capabilities())
            ordinary = CostEstimateInputs(
                capability.model_id, duration=1, resolution="480p", aspect_ratio="16:9"
            )
            hidden = replace(
                ordinary,
                generate_audio=True,
                reference_kinds=(InputReferenceKind.AUDIO,),
                reference_count=1,
                source_video_present=True,
            )
            first = await process.estimate_cost(ordinary)
            second = await process.estimate_cost(hidden)
            assert first.availability is second.availability is EstimateAvailability.AVAILABLE
            assert first.estimated_cost_usd == second.estimated_cost_usd == Decimal("0.03")
            assert first.applied_skus == second.applied_skus
            # Exact sizes are now positively reconciled for this T2V
            # method, so simultaneous normalized/exact intent is a real
            # conflict rather than hidden state to ignore.
            conflicted = await process.estimate_cost(replace(ordinary, size="480x480"))
            assert conflicted.availability is EstimateAvailability.UNAVAILABLE
            assert conflicted.reason == "geometry_intent_conflict"
            blocked = await process.estimate_cost(
                replace(ordinary, inference_method=InferenceMethod.AR2V)
            )
            assert blocked.availability is EstimateAvailability.UNAVAILABLE
        finally:
            await process.aclose(timeout=2)

    asyncio.run(scenario())


def test_required_provider_configuration_yields_unavailable_estimate_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = json.loads((ROOT / "tests/fixtures/op07-full-catalogue.json").read_text(encoding="utf8"))[
        "data"
    ]
    capability = enrich_capabilities(
        _parse_capability(next(row for row in raw if row["id"] == "heygen/avatar-iv"))
    )
    observed = datetime.now(timezone.utc)

    class Capabilities:
        async def effective_catalog(self) -> CapabilityObservation:
            return CapabilityObservation(observed, (capability,))

        def is_fresh(self, _: object) -> bool:
            return True

    def forbidden(_: httpx.Request) -> httpx.Response:
        pytest.fail("Estimate must not issue HTTP")

    monkeypatch.setattr(
        runtime.HttpxTransport,
        "create",
        classmethod(lambda cls: cls.for_test(httpx.MockTransport(forbidden))),
    )
    monkeypatch.setattr(runtime.compat, "host_interrupted", lambda: False)

    async def scenario() -> None:
        process = runtime.ProcessRuntime(tmp_path / "jobs.sqlite3", tmp_path / "output")
        try:
            process._resources = replace(process._require_resources(), capabilities=Capabilities())
            result = await process.estimate_cost(
                CostEstimateInputs(capability.model_id, inference_method=InferenceMethod.IR2V)
            )
            assert result.availability is EstimateAvailability.UNAVAILABLE
            assert result.reason == "provider_configuration_pricing_unverified"
        finally:
            await process.aclose(timeout=2)

    asyncio.run(scenario())


def test_estimate_preserves_references_with_nullable_total_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capability = _parse_capability(
        {
            "id": "synthetic/nullable-total-estimate",
            "reference_kinds": ["image", "video"],
            "mixed_reference_kinds": True,
            "request_shape_profiles": {
                "schema_version": 1,
                "methods": {
                    "MMR2V": {
                        "state": "SUPPORTED",
                        "controls": {"prompt": {"state": "SUPPORTED"}},
                        "topology": {
                            "fixed": [],
                            "reference_kinds": ["image", "video"],
                            "kind_sets": [["image", "video"]],
                            "min": 2,
                            "max": None,
                            "per_kind_max": {"image": 9, "video": 3},
                        },
                    }
                },
            },
        }
    )
    observed = datetime.now(timezone.utc)
    captured: list[CostEstimateInputs] = []

    class Capabilities:
        async def effective_catalog(self) -> CapabilityObservation:
            return CapabilityObservation(observed, (capability,))

        def is_fresh(self, _: object) -> bool:
            return True

    class Estimator:
        def estimate(self, _: object, inputs: CostEstimateInputs, **kwargs: object) -> object:
            captured.append(inputs)
            return runtime.EstimateResult.unavailable(observed, "synthetic_no_pricing")

    def forbidden(_: httpx.Request) -> httpx.Response:
        pytest.fail("Offline estimate must not issue HTTP")

    monkeypatch.setattr(
        runtime.HttpxTransport,
        "create",
        classmethod(lambda cls: cls.for_test(httpx.MockTransport(forbidden))),
    )
    monkeypatch.setattr(runtime, "PreflightCostEstimator", Estimator)
    monkeypatch.setattr(runtime.compat, "host_interrupted", lambda: False)

    async def scenario() -> None:
        process = runtime.ProcessRuntime(tmp_path / "jobs.sqlite3", tmp_path / "output")
        try:
            process._resources = replace(process._require_resources(), capabilities=Capabilities())
            await process.estimate_cost(
                CostEstimateInputs(
                    capability.model_id,
                    inference_method=InferenceMethod.MMR2V,
                    reference_kinds=(InputReferenceKind.IMAGE, InputReferenceKind.VIDEO),
                    reference_count=2,
                )
            )
            assert len(captured) == 1
            assert captured[0].reference_count == 2
            assert captured[0].reference_kinds == (
                InputReferenceKind.IMAGE,
                InputReferenceKind.VIDEO,
            )
        finally:
            await process.aclose(timeout=2)

    asyncio.run(scenario())
