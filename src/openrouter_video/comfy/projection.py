"""Sanitized capability projection for the presentation-only Comfy adapter."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TypeVar

from openrouter_video.capabilities import CapabilityModeStatus, inference_method_matrix
from openrouter_video.configuration import profile_constraints
from openrouter_video.evidence_registry import preferred_method
from openrouter_video.models import InferenceMethod, ModelCapabilities

_UI_METHODS = tuple(InferenceMethod)
_Option = TypeVar("_Option", int, str)


def _option_order(axis: str, value: int | str) -> tuple[int, float, float, int, int, str]:
    """Nominal display hierarchy only; never a preset-to-pixel mapping."""
    text = str(value)
    if text == "AUTO / MODEL DEFAULT" or (axis == "duration" and value == 0):
        return (-1, 0, 0, 0, 0, text)
    if axis == "resolution":
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(p|k)", text, re.IGNORECASE)
        if match:
            nominal = float(match[1]) * (1000 if match[2].lower() == "k" else 1)
            if math.isfinite(nominal) and nominal > 0:
                return (0, nominal, 0, 0, 0, text)
    elif axis in {"aspect_ratio", "size"}:
        separator = ":" if axis == "aspect_ratio" else "[x×]"
        match = re.fullmatch(r"([0-9]+)" + separator + r"([0-9]+)", text)
        if match:
            width, height = int(match[1]), int(match[2])
            if width > 0 and height > 0:
                try:
                    ratio = width / height
                    area = float(width) * float(height) if axis == "size" else ratio
                except OverflowError:
                    return (1, 0, 0, 0, 0, text)
                if math.isfinite(area) and math.isfinite(ratio):
                    return (0, area, ratio, width, height, text)
    elif axis == "duration":
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
            seconds = float(text)
            if math.isfinite(seconds) and seconds > 0:
                return (0, seconds, 0, 0, 0, text)
    return (1, 0, 0, 0, 0, text)


def canonical_options(axis: str, values: tuple[_Option, ...] | None) -> tuple[_Option, ...] | None:
    """Order a copy of UI values without changing evidence, membership or wire types."""
    return None if values is None else tuple(sorted(values, key=lambda v: _option_order(axis, v)))


def _evidence_json(value: object) -> object:
    """Keep conflicting typed evidence serializable at the HTTP boundary."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset)):
        return sorted((_evidence_json(item) for item in value), key=str)
    if isinstance(value, (tuple, list)):
        return [_evidence_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _evidence_json(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class UiModelCapabilities:
    """Non-sensitive selected-model metadata exposed to the local frontend."""

    model_id: str
    display_name: str
    supported_durations: tuple[int, ...] | None
    supported_resolutions: tuple[str, ...] | None
    supported_aspect_ratios: tuple[str, ...] | None
    supported_sizes: tuple[str, ...] | None
    supported_frame_types: tuple[str, ...] | None
    supports_seed: bool | None
    generate_audio: bool | None
    supported_reference_kinds: tuple[str, ...] | None
    max_reference_count: int | None
    mixed_reference_kinds: bool | None
    supports_edit: bool | None
    supports_extend: bool | None
    supported_inference_methods: tuple[str, ...]
    inference_method_statuses: tuple[tuple[str, str], ...]
    preferred_inference_method: str | None
    observed_at: datetime
    capability_evidence: tuple[dict[str, object], ...] = ()
    unmapped_capabilities: tuple[str, ...] = ()
    configuration_relations: tuple[dict[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "supported_durations": self.supported_durations,
            "supported_resolutions": self.supported_resolutions,
            "supported_aspect_ratios": self.supported_aspect_ratios,
            "supported_sizes": self.supported_sizes,
            "supported_frame_types": self.supported_frame_types,
            "supports_seed": self.supports_seed,
            "generate_audio": self.generate_audio,
            "supported_reference_kinds": self.supported_reference_kinds,
            "max_reference_count": self.max_reference_count,
            "mixed_reference_kinds": self.mixed_reference_kinds,
            "supports_edit": self.supports_edit,
            "supports_extend": self.supports_extend,
            "supported_inference_methods": self.supported_inference_methods,
            "inference_method_statuses": [
                {"method": method, "status": status}
                for method, status in self.inference_method_statuses
            ],
            "preferred_inference_method": self.preferred_inference_method,
            "observed_at": self.observed_at.isoformat(),
            "capability_evidence": self.capability_evidence,
            "unmapped_upstream_capabilities": self.unmapped_capabilities,
            "configuration_relations": self.configuration_relations,
        }


def project_model(capabilities: ModelCapabilities, observed_at: datetime) -> UiModelCapabilities:
    """Project effective Core truth without pricing, credentials or request data."""

    matrix = inference_method_matrix(capabilities)
    frames = capabilities.supported_frame_types
    references = capabilities.input_reference_capabilities
    return UiModelCapabilities(
        model_id=capabilities.model_id,
        display_name=capabilities.name or capabilities.model_id,
        supported_durations=canonical_options("duration", capabilities.supported_durations),
        supported_resolutions=canonical_options("resolution", capabilities.supported_resolutions),
        supported_aspect_ratios=canonical_options(
            "aspect_ratio", capabilities.supported_aspect_ratios
        ),
        supported_sizes=canonical_options("size", capabilities.supported_sizes),
        supported_frame_types=(
            tuple(sorted(frame.value for frame in frames)) if frames is not None else None
        ),
        supports_seed=capabilities.supports_seed,
        generate_audio=capabilities.generate_audio,
        supported_reference_kinds=(
            tuple(sorted(kind.value for kind in references.reference_kinds))
            if references is not None and references.reference_kinds is not None
            else None
        ),
        max_reference_count=(references.max_reference_count if references is not None else None),
        mixed_reference_kinds=(
            references.mixed_reference_kinds if references is not None else None
        ),
        supports_edit=capabilities.supports_edit,
        supports_extend=capabilities.supports_extend,
        supported_inference_methods=tuple(
            method.value for method in _UI_METHODS if matrix[method] is CapabilityModeStatus.READY
        ),
        inference_method_statuses=tuple(
            (method.value, matrix[method].value) for method in _UI_METHODS
        ),
        preferred_inference_method=(
            preferred.value
            if (preferred := preferred_method(capabilities.model_id)) is not None
            and matrix[preferred] is CapabilityModeStatus.READY
            else None
        ),
        observed_at=observed_at,
        capability_evidence=tuple(
            {
                "key": fact.key,
                "value": _evidence_json(fact.value),
                "state": fact.state.value,
                "authority": fact.authority,
                "source_reference": fact.source_reference,
                "observed_at": fact.observed_at,
                "scope": fact.scope,
                "artifact_version": fact.artifact_version,
                "conflicting_evidence": _evidence_json(fact.conflicting_evidence),
            }
            for fact in capabilities.evidence_facts
        ),
        unmapped_capabilities=capabilities.unmapped_capability_keys,
        configuration_relations=profile_constraints(capabilities),
    )


__all__ = ("UiModelCapabilities", "project_model")
