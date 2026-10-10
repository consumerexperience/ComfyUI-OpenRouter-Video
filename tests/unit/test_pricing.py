from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from openrouter_video.models import (
    InferenceMethod,
    InputReferenceCapabilities,
    InputReferenceKind,
    ModelCapabilities,
    PricingEvidence,
    PricingSku,
)
from openrouter_video.pricing import (
    CostEstimateInputs,
    EstimateAvailability,
    PreflightCostEstimator,
)

OBSERVED = datetime(2026, 9, 26, 19, 54, 44, tzinfo=timezone.utc)


def test_estimator_uses_only_matching_generic_resolution_sku() -> None:
    model = ModelCapabilities(
        "vendor/model",
        supports_text_only=True,
        supported_durations=(4,),
        supported_resolutions=("480p",),
        pricing_evidence=PricingEvidence(
            (
                PricingSku("per-video-second", Decimal("0.02")),
                PricingSku("per-video-second-480p", Decimal("0.035")),
            )
        ),
    )

    result = PreflightCostEstimator().estimate(
        model,
        CostEstimateInputs("vendor/model", duration=4, resolution="480p"),
        observed_at=OBSERVED,
    )

    assert result.availability is EstimateAvailability.AVAILABLE
    assert result.estimated_cost_usd == Decimal("0.140")
    assert result.applied_skus == ("per-video-second-480p",)


def test_estimator_refuses_ambiguous_or_unmatched_shapes() -> None:
    ambiguous = ModelCapabilities(
        "vendor/model",
        supports_text_only=True,
        supported_durations=(4,),
        supported_resolutions=("480p",),
        pricing_evidence=PricingEvidence(
            (
                PricingSku("per-video-second", Decimal("0.02")),
                PricingSku("per-image-reference", Decimal("0.10")),
            )
        ),
    )
    unmatched = ModelCapabilities(
        "vendor/model",
        supports_text_only=True,
        supported_durations=(4,),
        supported_resolutions=("480p",),
        pricing_evidence=PricingEvidence((PricingSku("per-video-second-720p", Decimal("0.03")),)),
    )
    estimator = PreflightCostEstimator()

    ambiguous_result = estimator.estimate(
        ambiguous,
        CostEstimateInputs("vendor/model", duration=4, resolution="480p"),
        observed_at=OBSERVED,
    )
    unmatched_result = estimator.estimate(
        unmatched,
        CostEstimateInputs("vendor/model", duration=4, resolution="480p"),
        observed_at=OBSERVED,
    )

    assert ambiguous_result.availability is EstimateAvailability.UNAVAILABLE
    assert ambiguous_result.reason == "pricing_sku_semantics_ambiguous"
    assert unmatched_result.availability is EstimateAvailability.UNAVAILABLE
    assert unmatched_result.reason == "matching_pricing_sku_unavailable"


def test_estimator_accepts_only_unambiguous_fixed_generate_shape() -> None:
    model = ModelCapabilities(
        "vendor/model",
        supports_text_only=True,
        pricing_evidence=PricingEvidence((PricingSku("generate", Decimal("0.42")),)),
    )

    result = PreflightCostEstimator().estimate(
        model,
        CostEstimateInputs("vendor/model"),
        observed_at=OBSERVED,
    )

    assert result.availability is EstimateAvailability.AVAILABLE
    assert result.estimated_cost_usd == Decimal("0.42")
    assert result.applied_skus == ("generate",)


def test_estimator_never_prices_unsupported_or_conflicting_configuration() -> None:
    model = ModelCapabilities(
        "vendor/model",
        supported_durations=(4,),
        supported_resolutions=("480p",),
        supported_aspect_ratios=("16:9",),
        supported_sizes=("854x480",),
        pricing_evidence=PricingEvidence((PricingSku("generate", Decimal("0.42")),)),
    )
    estimator = PreflightCostEstimator()

    unsupported = estimator.estimate(
        model,
        CostEstimateInputs("vendor/model", duration=8),
        observed_at=OBSERVED,
    )
    conflicting = estimator.estimate(
        model,
        CostEstimateInputs(
            "vendor/model",
            resolution="480p",
            aspect_ratio="16:9",
            size="854x480",
        ),
        observed_at=OBSERVED,
    )

    assert unsupported.availability is EstimateAvailability.UNAVAILABLE
    assert unsupported.reason == "configuration_not_authorized"
    assert conflicting.availability is EstimateAvailability.UNAVAILABLE
    assert conflicting.reason == "geometry_intent_conflict"


def test_estimator_refuses_video_and_audio_reference_pricing_by_analogy() -> None:
    model = ModelCapabilities(
        "vendor/model",
        input_reference_capabilities=InputReferenceCapabilities(
            reference_kinds=frozenset(
                {InputReferenceKind.IMAGE, InputReferenceKind.VIDEO, InputReferenceKind.AUDIO}
            ),
            max_reference_count=50,
            mixed_reference_kinds=True,
        ),
        pricing_evidence=PricingEvidence((PricingSku("generate", Decimal("0.42")),)),
    )
    estimator = PreflightCostEstimator()

    video = estimator.estimate(
        model,
        CostEstimateInputs(
            "vendor/model",
            inference_method=InferenceMethod.VR2V,
            reference_kinds=(InputReferenceKind.VIDEO,),
            reference_count=1,
        ),
        observed_at=OBSERVED,
    )
    audio = estimator.estimate(
        model,
        CostEstimateInputs(
            "vendor/model",
            inference_method=InferenceMethod.AR2V,
            reference_kinds=(InputReferenceKind.AUDIO,),
            reference_count=1,
        ),
        observed_at=OBSERVED,
    )

    assert video.reason == "video_input_pricing_semantics_ambiguous"
    assert audio.reason == "audio_input_pricing_semantics_ambiguous"
