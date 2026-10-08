"""Sanitized capability projection for the presentation-only Comfy adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from openrouter_video.capabilities import CapabilityModeStatus, inference_method_matrix
from openrouter_video.capability_overlays import preferred_inference_method
from openrouter_video.models import InferenceMethod, ModelCapabilities

_UI_METHODS = tuple(InferenceMethod)


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
        }


def project_model(capabilities: ModelCapabilities, observed_at: datetime) -> UiModelCapabilities:
    """Project effective Core truth without pricing, credentials or request data."""

    matrix = inference_method_matrix(capabilities)
    frames = capabilities.supported_frame_types
    references = capabilities.input_reference_capabilities
    return UiModelCapabilities(
        model_id=capabilities.model_id,
        display_name=capabilities.name or capabilities.model_id,
        supported_durations=capabilities.supported_durations,
        supported_resolutions=capabilities.supported_resolutions,
        supported_aspect_ratios=capabilities.supported_aspect_ratios,
        supported_sizes=capabilities.supported_sizes,
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
            if (preferred := preferred_inference_method(capabilities.model_id)) is not None
            and matrix[preferred] is CapabilityModeStatus.READY
            else None
        ),
        observed_at=observed_at,
    )


__all__ = ("UiModelCapabilities", "project_model")
