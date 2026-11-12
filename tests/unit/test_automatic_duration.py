from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from openrouter_video.models import ModelCapabilities, PricingEvidence, PricingSku
from openrouter_video.pricing import (
    CostEstimateInputs,
    EstimateAvailability,
    PreflightCostEstimator,
)


def test_explicit_automatic_duration_is_not_priced_as_a_numeric_duration() -> None:
    model = ModelCapabilities(
        "vendor/model",
        supported_durations=(-1, 4, 8),
        pricing_evidence=PricingEvidence((PricingSku("per-video-second", Decimal("0.02")),)),
    )

    result = PreflightCostEstimator().estimate(
        model,
        CostEstimateInputs("vendor/model", duration=-1),
        observed_at=datetime(2026, 11, 13, tzinfo=timezone.utc),
    )

    assert result.availability is EstimateAvailability.UNAVAILABLE
    assert result.estimated_cost_usd is None
    assert result.reason == "automatic_duration_unknown"
