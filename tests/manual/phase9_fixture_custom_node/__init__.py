"""Test-only Core dependency injection for real Comfy browser acceptance.

This module is loaded only by the isolated compatibility harness.  It patches the
already registered product route handlers with an in-memory CapabilityService;
no production flag, endpoint, request header, or query parameter can enable it.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from openrouter_video.capabilities import CapabilityObservation, CapabilityService
from openrouter_video.comfy import routes
from openrouter_video.models import (
    FrameType,
    InputReferenceCapabilities,
    InputReferenceKind,
    ModelCapabilities,
    PricingEvidence,
    PricingSku,
)
from openrouter_video.persistence import JobStore
from openrouter_video.pricing import CostEstimateInputs, EstimateResult, PreflightCostEstimator

_OBSERVED_AT = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _model_a() -> ModelCapabilities:
    return ModelCapabilities(
        model_id="phase9/model-a",
        name="Phase 9 Model A",
        supported_durations=(4, 5, 6),
        supported_resolutions=("480p", "720p", "768p"),
        supported_aspect_ratios=("16:9", "4:3", "5:4"),
        supported_frame_types=frozenset({FrameType.FIRST, FrameType.LAST}),
        generate_audio=False,
        supports_seed=True,
        input_reference_capabilities=InputReferenceCapabilities(
            reference_kinds=frozenset({InputReferenceKind.IMAGE, InputReferenceKind.VIDEO}),
            max_reference_count=3,
            mixed_reference_kinds=True,
        ),
        pricing_evidence=PricingEvidence((PricingSku("generate", Decimal("0.14")),)),
    )


def _model_b() -> ModelCapabilities:
    return ModelCapabilities(
        model_id="phase9/model-b",
        name="Phase 9 Model B",
        supported_durations=(4, 6, 8),
        supported_resolutions=("720p", "1080p"),
        supported_aspect_ratios=("1:1", "3:2"),
        supported_sizes=("854x480",),
        supported_frame_types=frozenset({FrameType.FIRST}),
        generate_audio=True,
        supports_seed=False,
        input_reference_capabilities=InputReferenceCapabilities(
            reference_kinds=frozenset(),
            max_reference_count=0,
            mixed_reference_kinds=False,
        ),
        pricing_evidence=PricingEvidence((PricingSku("generate", Decimal("0.42")),)),
    )


def _fixture_models() -> tuple[ModelCapabilities, ...]:
    generic = tuple(
        ModelCapabilities(
            model_id=f"phase9/model-{index:02d}",
            name=f"Phase 9 Model {index:02d}",
            supported_durations=(4,),
            supported_resolutions=("480p",),
            supported_aspect_ratios=("16:9",),
            supported_frame_types=frozenset(),
            generate_audio=False,
            supports_seed=False,
            input_reference_capabilities=InputReferenceCapabilities(
                reference_kinds=frozenset(),
                max_reference_count=0,
                mixed_reference_kinds=False,
            ),
        )
        for index in range(3, 31)
    )
    return (_model_a(), _model_b(), *generic)


class _FixtureDiscovery:
    async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
        return _fixture_models()


class _AlwaysLiveFixtureStore:
    """Persist through the real store while forcing each fixture read through discovery."""

    def __init__(self, database: Path) -> None:
        self._store = JobStore(database)

    def load_capability_catalog(self) -> None:
        return None

    def replace_capability_catalog(
        self,
        models: tuple[ModelCapabilities, ...],
        observed_at: datetime,
    ) -> None:
        self._store.replace_capability_catalog(models, observed_at)


class _FixtureRuntime:
    def __init__(self) -> None:
        database = Path(tempfile.mkdtemp(prefix="orv-phase9-fixture-")) / "jobs.sqlite3"
        self._service = CapabilityService(
            client=_FixtureDiscovery(),
            store=_AlwaysLiveFixtureStore(database),  # type: ignore[arg-type]
            now=lambda: _OBSERVED_AT,
        )

    async def catalog(self) -> CapabilityObservation:
        return await self._service.catalog()

    async def effective_catalog(self) -> CapabilityObservation:
        return await self._service.effective_catalog()

    async def estimate_cost(self, inputs: CostEstimateInputs) -> EstimateResult:
        observation = await self._service.effective_catalog()
        for model in observation.models:
            if inputs.model_id in {model.model_id, model.canonical_slug}:
                return PreflightCostEstimator().estimate(
                    model,
                    inputs,
                    observed_at=observation.observed_at,
                )
        return EstimateResult.unavailable(observation.observed_at, "model_unavailable")


_RUNTIME = _FixtureRuntime()
routes.__dict__["get_runtime"] = lambda: _RUNTIME

NODE_CLASS_MAPPINGS: dict[str, object] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}
