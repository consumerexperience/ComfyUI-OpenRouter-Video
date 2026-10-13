"""Synthetic shape proof for adapter/transport tests, never live model claims."""

from datetime import datetime, timezone
from typing import Any

from openrouter_video.capabilities import CapabilityObservation
from openrouter_video.configuration import REQUEST_SHAPES_KEY
from openrouter_video.models import (
    CapabilityFact,
    CapabilityFactState,
    FrameType,
    InferenceMethod,
    InputReferenceCapabilities,
    InputReferenceKind,
    ModelCapabilities,
)


def synthetic_projected_model(model_id: str = "vendor/model") -> ModelCapabilities:
    methods: dict[str, Any] = {}
    for method in InferenceMethod:
        fixed = {
            "I2V": ["first_frame"],
            "FLF2V": ["first_frame", "last_frame"],
            "V2V_EDIT": ["source_video"],
            "V2V_EXTEND": ["source_video"],
        }.get(method.value, [])
        reference = method.value not in {"T2V", "I2V", "FLF2V"}
        kinds = [kind.value for kind in InputReferenceKind] if reference else []
        sets = (
            [
                [],
                ["image"],
                ["video"],
                ["audio"],
                ["image", "video"],
                ["image", "audio"],
                ["video", "audio"],
                kinds,
            ]
            if reference
            else [[]]
        )
        methods[method.value] = {
            "state": "SUPPORTED",
            "controls": {
                name: {"state": "SUPPORTED"}
                for name in (
                    "prompt",
                    "duration",
                    "resolution",
                    "aspect_ratio",
                    "size",
                    "seed",
                    "generate_audio",
                )
            },
            "topology": {
                "fixed": fixed,
                "reference_kinds": kinds,
                "kind_sets": sets,
                "min": 0,
                "max": 50 if reference else 0,
                "per_kind_max": {kind: 50 for kind in kinds},
            },
        }
        methods[method.value]["controls"]["seed"]["integer_range"] = {"min": 0, "max": 999}
    fact = CapabilityFact(
        model_id,
        REQUEST_SHAPES_KEY,
        {"schema_version": 1, "methods": methods},
        CapabilityFactState.SUPPORTED,
        "TEST_ONLY",
        "https://openrouter.ai/docs",
        "2026-10-13T00:00:00+00:00",
        "Synthetic fixture only",
        "TEST_ONLY",
    )
    return ModelCapabilities(
        model_id,
        supports_text_only=True,
        supports_seed=True,
        generate_audio=True,
        supported_durations=tuple(range(1, 31)),
        supported_resolutions=("480p", "720p", "1080p"),
        supported_aspect_ratios=("1:1", "16:9", "9:16"),
        supported_sizes=("480x480", "640x480", "1280x720"),
        supported_frame_types=frozenset(FrameType),
        input_reference_capabilities=InputReferenceCapabilities(
            reference_kinds=frozenset(InputReferenceKind),
            max_reference_count=50,
            mixed_reference_kinds=True,
        ),
        evidence_facts=(fact,),
    )


class ProjectionCatalogRuntime:
    async def effective_catalog(self) -> Any:
        return CapabilityObservation(datetime.now(timezone.utc), (synthetic_projected_model(),))
