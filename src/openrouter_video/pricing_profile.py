"""Typed current catalogue pricing vocabulary, never optimistic unknown charges."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from openrouter_video.models import PricingEvidence


class PricingUnit(str, Enum):
    OUTPUT_SECOND = "OUTPUT_SECOND"
    OUTPUT_TOKEN = "OUTPUT_TOKEN"  # noqa: S105 - pricing quantity, no secret
    IMAGE_INPUT = "IMAGE_INPUT"
    REFERENCE_SECOND = "REFERENCE_SECOND"
    MINIMUM = "MINIMUM"
    MEGAPIXEL_SECOND = "MEGAPIXEL_SECOND"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PricingDimension:
    key: str
    rate_usd: Decimal
    unit: PricingUnit


def normalize_pricing(evidence: PricingEvidence) -> tuple[PricingDimension, ...]:
    dimensions = []
    for sku in evidence.skus:
        key = sku.key
        rate = sku.rate_usd / 100 if key.startswith(("cents_", "minimum_cents_")) else sku.rate_usd
        if key.startswith("video_tokens"):
            unit = PricingUnit.OUTPUT_TOKEN
        elif "megapixel_second" in key:
            unit = PricingUnit.MEGAPIXEL_SECOND
        elif key.startswith("minimum_"):
            unit = PricingUnit.MINIMUM
        elif key in ("cents_per_image_input", "reference_images"):
            unit = PricingUnit.IMAGE_INPUT
        elif key.startswith("reference_duration_seconds"):
            unit = PricingUnit.REFERENCE_SECOND
        elif key.startswith(
            (
                "duration_seconds",
                "text_to_video_duration_seconds",
                "image_to_video_duration_seconds",
                "cents_per_second_output",
                "cents_per_video_output_second",
                "cents_per_second_video_continuation",
            )
        ):
            unit = PricingUnit.OUTPUT_SECOND
        else:
            unit = PricingUnit.UNKNOWN
        dimensions.append(PricingDimension(key, rate, unit))
    return tuple(dimensions)
