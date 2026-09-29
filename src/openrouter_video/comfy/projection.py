"""Sanitized capability projection for the presentation-only Comfy adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from openrouter_video.capabilities import GenerationMode, mode_enforcement_matrix
from openrouter_video.models import ModelCapabilities

_UI_MODES = (
    GenerationMode.FIRST_FRAME,
    GenerationMode.FIRST_PLUS_LAST,
    GenerationMode.MULTI_IMAGE_REFERENCE,
    GenerationMode.VIDEO_REFERENCE,
    GenerationMode.IMAGE_PLUS_VIDEO_REFERENCE,
)


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
    mixed_image_video_references: bool | None
    normalized_reference_modes: tuple[tuple[str, str], ...]
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
            "mixed_image_video_references": self.mixed_image_video_references,
            "normalized_reference_modes": [
                {"mode": mode, "status": status} for mode, status in self.normalized_reference_modes
            ],
            "observed_at": self.observed_at.isoformat(),
        }


def project_model(capabilities: ModelCapabilities, observed_at: datetime) -> UiModelCapabilities:
    """Project effective Core truth without pricing, credentials or request data."""

    matrix = mode_enforcement_matrix(capabilities)
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
        mixed_image_video_references=(
            references.mixed_image_video_references if references is not None else None
        ),
        normalized_reference_modes=tuple((mode.value, matrix[mode].value) for mode in _UI_MODES),
        observed_at=observed_at,
    )


__all__ = ("UiModelCapabilities", "project_model")
