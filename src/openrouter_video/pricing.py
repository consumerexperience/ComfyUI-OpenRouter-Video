"""Conservative, model-agnostic preflight cost estimation from catalogue evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Final

from openrouter_video.capabilities import (
    CapabilityModeStatus,
    mode_enforcement_matrix,
)
from openrouter_video.models import InferenceMethod, ModelCapabilities, PricingEvidence

_PER_SECOND: Final = "per-video-second"
_RESOLUTION_SKU = re.compile(r"^per-video-second-(?P<resolution>[a-z0-9]+)$")


class EstimateAvailability(str, Enum):
    """Whether current catalogue evidence supports a numeric estimate."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ReferenceMode(str, Enum):
    """Normalized request shape relevant to catalogue pricing."""

    NONE = "none"
    FIRST_FRAME = "first_frame"
    FIRST_PLUS_LAST = "first_plus_last"
    MULTI_IMAGE_REFERENCE = "multi_image_reference"
    VIDEO_REFERENCE = "video_reference"
    IMAGE_PLUS_VIDEO_REFERENCE = "image_plus_video_reference"


_REFERENCE_MODES: Final = {
    ReferenceMode.FIRST_FRAME: InferenceMethod.I2V,
    ReferenceMode.FIRST_PLUS_LAST: InferenceMethod.FLF2V,
    ReferenceMode.MULTI_IMAGE_REFERENCE: InferenceMethod.MI2V,
    ReferenceMode.VIDEO_REFERENCE: InferenceMethod.VR2V,
    ReferenceMode.IMAGE_PLUS_VIDEO_REFERENCE: InferenceMethod.MMR2V,
}


@dataclass(frozen=True, slots=True)
class CostEstimateInputs:
    """Non-sensitive selected configuration used by the estimator."""

    model_id: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    size: str | None = None
    generate_audio: bool = False
    reference_mode: ReferenceMode = ReferenceMode.NONE


@dataclass(frozen=True, slots=True)
class EstimateResult:
    """A prepared frontend-safe estimate result without raw pricing evidence."""

    availability: EstimateAvailability
    observed_at: datetime
    estimated_cost_usd: Decimal | None = None
    provenance: str | None = None
    applied_skus: tuple[str, ...] = ()
    reason: str | None = None

    @classmethod
    def unavailable(cls, observed_at: datetime, reason: str) -> EstimateResult:
        return cls(EstimateAvailability.UNAVAILABLE, observed_at, reason=reason)


class PreflightCostEstimator:
    """Estimate only documented, unambiguous generic SKU shapes."""

    __slots__ = ()

    def estimate(
        self,
        capabilities: ModelCapabilities,
        inputs: CostEstimateInputs,
        *,
        observed_at: datetime,
    ) -> EstimateResult:
        if inputs.model_id not in {capabilities.model_id, capabilities.canonical_slug}:
            return EstimateResult.unavailable(observed_at, "model_mismatch")
        if inputs.size is not None and (
            inputs.resolution is not None or inputs.aspect_ratio is not None
        ):
            return EstimateResult.unavailable(observed_at, "geometry_intent_conflict")
        selected_values: tuple[tuple[object | None, tuple[object, ...] | None], ...] = (
            (inputs.duration, capabilities.supported_durations),
            (inputs.resolution, capabilities.supported_resolutions),
            (inputs.aspect_ratio, capabilities.supported_aspect_ratios),
            (inputs.size, capabilities.supported_sizes),
        )
        if any(
            selected is not None and (supported is None or selected not in supported)
            for selected, supported in selected_values
        ):
            return EstimateResult.unavailable(observed_at, "configuration_not_authorized")
        if inputs.generate_audio and capabilities.generate_audio is not True:
            return EstimateResult.unavailable(observed_at, "configuration_not_authorized")
        mode = _REFERENCE_MODES.get(inputs.reference_mode, InferenceMethod.T2V)
        if mode_enforcement_matrix(capabilities)[mode] is not CapabilityModeStatus.READY:
            return EstimateResult.unavailable(observed_at, "reference_mode_not_authorized")
        evidence = capabilities.pricing_evidence
        if evidence is None or not evidence.skus:
            return EstimateResult.unavailable(observed_at, "pricing_evidence_unavailable")

        rates = {sku.key: sku.rate_usd for sku in evidence.skus}
        if len(rates) == 1 and "generate" in rates:
            return EstimateResult(
                EstimateAvailability.AVAILABLE,
                observed_at,
                estimated_cost_usd=rates["generate"],
                provenance="catalogue pricing_skus.generate",
                applied_skus=("generate",),
            )

        if inputs.duration is None or inputs.duration <= 0:
            return EstimateResult.unavailable(observed_at, "duration_required_for_pricing")
        if not _only_per_second_skus(evidence):
            return EstimateResult.unavailable(observed_at, "pricing_sku_semantics_ambiguous")

        resolution_key = f"{_PER_SECOND}-{inputs.resolution.lower()}" if inputs.resolution else None
        if resolution_key is not None and resolution_key in rates:
            selected_key = resolution_key
        elif _PER_SECOND in rates:
            selected_key = _PER_SECOND
        else:
            return EstimateResult.unavailable(observed_at, "matching_pricing_sku_unavailable")

        estimated = rates[selected_key] * Decimal(inputs.duration)
        return EstimateResult(
            EstimateAvailability.AVAILABLE,
            observed_at,
            estimated_cost_usd=estimated,
            provenance=f"catalogue pricing_skus.{selected_key} × duration",
            applied_skus=(selected_key,),
        )


def _only_per_second_skus(evidence: PricingEvidence) -> bool:
    for sku in evidence.skus:
        if sku.key == _PER_SECOND:
            continue
        if _RESOLUTION_SKU.fullmatch(sku.key) is None:
            return False
    return True


__all__ = (
    "CostEstimateInputs",
    "EstimateAvailability",
    "EstimateResult",
    "PreflightCostEstimator",
    "ReferenceMode",
)
