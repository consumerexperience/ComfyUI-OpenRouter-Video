from datetime import datetime, timezone
from decimal import Decimal

from openrouter_video.models import ModelCapabilities, PricingEvidence, PricingSku
from openrouter_video.pricing import (
    CostEstimateInputs,
    EstimateAvailability,
    PreflightCostEstimator,
)
from openrouter_video.pricing_profile import PricingUnit, normalize_pricing


def test_current_cents_dimension_includes_input_charge_and_minimum() -> None:
    from openrouter_video.models import FrameType, InferenceMethod

    model = ModelCapabilities(
        "future/priced",
        supports_text_only=True,
        supported_durations=(4,),
        supported_frame_types=frozenset({FrameType.FIRST}),
        pricing_evidence=PricingEvidence(
            (
                PricingSku("cents_per_second_output", Decimal("3")),
                PricingSku("cents_per_image_input", Decimal("1")),
                PricingSku("minimum_cents_per_generation", Decimal("20")),
            )
        ),
    )
    result = PreflightCostEstimator().estimate(
        model,
        CostEstimateInputs(model.model_id, duration=4, inference_method=InferenceMethod.I2V),
        observed_at=datetime.now(timezone.utc),
    )
    assert result.availability is EstimateAvailability.AVAILABLE
    assert result.estimated_cost_usd == Decimal("0.20")


def test_token_and_unknown_dimensions_never_invent_optimistic_bound() -> None:
    evidence = PricingEvidence((PricingSku("video_tokens_with_video_input", Decimal("0.0000021")),))
    assert normalize_pricing(evidence)[0].unit is PricingUnit.OUTPUT_TOKEN
    model = ModelCapabilities("future/token", supports_text_only=True, pricing_evidence=evidence)
    result = PreflightCostEstimator().estimate(
        model,
        CostEstimateInputs(model.model_id, duration=4),
        observed_at=datetime.now(timezone.utc),
    )
    assert result.availability is EstimateAvailability.UNAVAILABLE
    assert result.estimated_cost_usd is None


def test_continuation_rate_does_not_price_text_only_generation() -> None:
    model = ModelCapabilities(
        "future/priced",
        supports_text_only=True,
        supported_durations=(4,),
        supported_resolutions=("720p",),
        pricing_evidence=PricingEvidence(
            (
                PricingSku("cents_per_second_output_720p", Decimal("3")),
                PricingSku("cents_per_second_video_continuation_720p", Decimal("10")),
            )
        ),
    )
    result = PreflightCostEstimator().estimate(
        model,
        CostEstimateInputs(model.model_id, duration=4, resolution="720p"),
        observed_at=datetime.now(timezone.utc),
    )
    assert result.estimated_cost_usd == Decimal("0.12")
