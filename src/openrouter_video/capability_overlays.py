"""Reviewed exact-ID capability data for gaps in machine-readable metadata."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from types import MappingProxyType
from typing import Final, TypeVar

from openrouter_video.models import (
    CapabilityEvidenceSource,
    InferenceMethod,
    InputReferenceCapabilities,
    InputReferenceCapabilityField,
    InputReferenceKind,
    ModelCapabilities,
    ModelCapabilityField,
)

_Value = TypeVar("_Value")


@dataclass(frozen=True, slots=True)
class EvidenceBackedCapabilityOverlay:
    """Reviewed model-specific capability data, never executable provider logic."""

    model_id: str
    capabilities: InputReferenceCapabilities
    supports_edit: bool | None
    supports_extend: bool | None
    evidence_level: str
    first_party_source: str
    evidence_checked_at: date
    notes: tuple[str, ...]


SEEDANCE_2_5_OVERLAY: Final = EvidenceBackedCapabilityOverlay(
    model_id="bytedance/seedance-2.5",
    capabilities=InputReferenceCapabilities(
        reference_kinds=frozenset(
            {InputReferenceKind.IMAGE, InputReferenceKind.VIDEO, InputReferenceKind.AUDIO}
        ),
        max_reference_count=50,
        mixed_reference_kinds=True,
    ),
    supports_edit=True,
    supports_extend=True,
    evidence_level="B2",
    first_party_source="https://openrouter.ai/blog/insights/seedance-2-5-review/",
    evidence_checked_at=date(2026, 9, 30),
    notes=(
        "OpenRouter documents image, video, and audio references for this exact model.",
        "The reported limit of 50 references is model-page evidence, not a videos/models field.",
        "A first-party request example combines video_url and image_url references.",
        "Edit and Extend are separate local intents over the ordinary ordered reference wire form.",
    ),
)

APPROVED_CAPABILITY_OVERLAYS: Final = MappingProxyType(
    {SEEDANCE_2_5_OVERLAY.model_id: SEEDANCE_2_5_OVERLAY}
)

PREFERRED_INFERENCE_METHODS: Final = MappingProxyType(
    {SEEDANCE_2_5_OVERLAY.model_id: InferenceMethod.MI2V}
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
    edit, edit_source, edit_conflict = _merge_field(
        model.supports_edit,
        model.edit_support_source,
        overlay.supports_edit,
    )
    extend, extend_source, extend_conflict = _merge_field(
        model.supports_extend,
        model.extend_support_source,
        overlay.supports_extend,
    )
    model_conflicts = set(model.capability_conflicts)
    if edit_conflict:
        model_conflicts.add(ModelCapabilityField.EDIT)
    if extend_conflict:
        model_conflicts.add(ModelCapabilityField.EXTEND)
    return replace(
        model,
        input_reference_capabilities=effective,
        supports_edit=edit,
        supports_extend=extend,
        edit_support_source=edit_source,
        extend_support_source=extend_source,
        capability_conflicts=frozenset(model_conflicts),
    )


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
        level_a.mixed_reference_kinds,
        level_a.mixed_reference_kinds_source,
        overlay.mixed_reference_kinds,
    )
    conflicts = set(level_a.conflicts)
    if kinds_conflict:
        conflicts.add(InputReferenceCapabilityField.REFERENCE_KINDS)
    if count_conflict:
        conflicts.add(InputReferenceCapabilityField.MAX_REFERENCE_COUNT)
    if mixed_conflict:
        conflicts.add(InputReferenceCapabilityField.MIXED_REFERENCE_KINDS)
    return InputReferenceCapabilities(
        reference_kinds=kinds,
        max_reference_count=count,
        mixed_reference_kinds=mixed,
        reference_kinds_source=kinds_source,
        max_reference_count_source=count_source,
        mixed_reference_kinds_source=mixed_source,
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


def preferred_inference_method(model_id: str) -> InferenceMethod | None:
    """Return exact-ID UX policy without provider, family, or slug inference."""

    return PREFERRED_INFERENCE_METHODS.get(model_id)


__all__ = (
    "APPROVED_CAPABILITY_OVERLAYS",
    "EvidenceBackedCapabilityOverlay",
    "PREFERRED_INFERENCE_METHODS",
    "SEEDANCE_2_5_OVERLAY",
    "apply_capability_overlay",
    "preferred_inference_method",
)
