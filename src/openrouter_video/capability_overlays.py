"""Reviewed exact-ID capability data for gaps in machine-readable metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from types import MappingProxyType
from typing import Final, TypeVar

from openrouter_video.models import (
    CapabilityEvidenceSource,
    InputReferenceCapabilities,
    InputReferenceCapabilityField,
    InputReferenceKind,
    ModelCapabilities,
)

_Value = TypeVar("_Value")


@dataclass(frozen=True, slots=True)
class EvidenceBackedCapabilityOverlay:
    """Reviewed model-specific capability data, never executable provider logic."""

    model_id: str
    capabilities: InputReferenceCapabilities
    evidence_level: str
    first_party_source: str
    evidence_checked_at: date
    notes: tuple[str, ...]


SEEDANCE_2_5_OVERLAY: Final = EvidenceBackedCapabilityOverlay(
    model_id="bytedance/seedance-2.5",
    capabilities=InputReferenceCapabilities(
        reference_kinds=frozenset({InputReferenceKind.IMAGE, InputReferenceKind.VIDEO}),
        max_reference_count=50,
        mixed_image_video_references=True,
    ),
    evidence_level="B2",
    first_party_source="https://openrouter.ai/blog/insights/seedance-2-5-review/",
    evidence_checked_at=date(2026, 9, 26),
    notes=(
        "OpenRouter documents image, video, and audio references; the product exposes only image "
        "and video references.",
        "The reported limit of 50 references is model-page evidence, not a videos/models field.",
        "A first-party request example combines video_url and image_url references.",
        "Video references remain Generate inputs; Edit and Extend are not product operations.",
    ),
)

APPROVED_CAPABILITY_OVERLAYS: Final = MappingProxyType(
    {SEEDANCE_2_5_OVERLAY.model_id: SEEDANCE_2_5_OVERLAY}
)


def apply_capability_overlay(model: ModelCapabilities) -> ModelCapabilities:
    """Fill absent signals from one exact-ID overlay without overriding Level A."""

    matching_ids = {
        candidate
        for candidate in (model.model_id, model.canonical_slug)
        if candidate is not None and candidate in APPROVED_CAPABILITY_OVERLAYS
    }
    if len(matching_ids) != 1:
        return model
    overlay = APPROVED_CAPABILITY_OVERLAYS[next(iter(matching_ids))]
    current = model.input_reference_capabilities or InputReferenceCapabilities()
    effective = _merge_reference_capabilities(current, overlay.capabilities)
    return replace(model, input_reference_capabilities=effective)


def _merge_reference_capabilities(
    level_a: InputReferenceCapabilities,
    overlay: InputReferenceCapabilities,
) -> InputReferenceCapabilities:
    kinds, kinds_source, kinds_conflict = _merge_field(
        level_a.reference_kinds,
        level_a.reference_kinds_source,
        overlay.reference_kinds,
    )
    count, count_source, count_conflict = _merge_field(
        level_a.max_reference_count,
        level_a.max_reference_count_source,
        overlay.max_reference_count,
    )
    mixed, mixed_source, mixed_conflict = _merge_field(
        level_a.mixed_image_video_references,
        level_a.mixed_image_video_references_source,
        overlay.mixed_image_video_references,
    )
    conflicts = set(level_a.conflicts)
    if kinds_conflict:
        conflicts.add(InputReferenceCapabilityField.REFERENCE_KINDS)
    if count_conflict:
        conflicts.add(InputReferenceCapabilityField.MAX_REFERENCE_COUNT)
    if mixed_conflict:
        conflicts.add(InputReferenceCapabilityField.MIXED_IMAGE_VIDEO_REFERENCES)
    return InputReferenceCapabilities(
        reference_kinds=kinds,
        max_reference_count=count,
        mixed_image_video_references=mixed,
        reference_kinds_source=kinds_source,
        max_reference_count_source=count_source,
        mixed_image_video_references_source=mixed_source,
        conflicts=frozenset(conflicts),
    )


def _merge_field(
    level_a: _Value | None,
    source: CapabilityEvidenceSource | None,
    overlay: _Value | None,
) -> tuple[_Value | None, CapabilityEvidenceSource | None, bool]:
    if source is CapabilityEvidenceSource.EVIDENCE_OVERLAY:
        return level_a, source, False
    if level_a is not None:
        return level_a, CapabilityEvidenceSource.LEVEL_A, overlay is not None and level_a != overlay
    if overlay is not None:
        return overlay, CapabilityEvidenceSource.EVIDENCE_OVERLAY, False
    return None, None, False


__all__ = (
    "APPROVED_CAPABILITY_OVERLAYS",
    "EvidenceBackedCapabilityOverlay",
    "SEEDANCE_2_5_OVERLAY",
    "apply_capability_overlay",
)
