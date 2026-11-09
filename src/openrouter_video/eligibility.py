"""Selectable methods require a feasible request through the existing serializer.

Raw discovery and job resolution are deliberately unaffected. Witnesses are local,
synthetic shape checks, never remote generation or proof of provider success.
"""

from __future__ import annotations

from itertools import islice, product
from typing import Any

from openrouter_video.capabilities import RequestValidator
from openrouter_video.configuration import project_method, projected_shape_valid
from openrouter_video.errors import ProductFailureError
from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
)


def request_witness(model: ModelCapabilities, method: InferenceMethod) -> GenerationRequest | None:
    """Return one valid serializable shape, with a bounded fail-closed search."""
    profile = project_method(model, method.value)
    if profile["state"] != "SUPPORTED":
        return None
    controls, topology = profile["controls"], profile["topology"]
    if controls.get("prompt", {}).get("state") != "SUPPORTED":
        return None
    domains: dict[str, list[Any]] = {}
    for name in ("duration", "resolution", "aspect_ratio", "size"):
        control = controls.get(name, {})
        domains[name] = (
            control.get("values", [None]) if control.get("state") == "SUPPORTED" else [None]
        )
    references: list[tuple[str, ...]] = []
    for kinds in topology["kind_sets"]:
        for count in range(topology["min"], max(topology["min"], len(kinds)) + 1):
            if not kinds and count:
                continue
            shape = tuple(kinds[i % len(kinds)] for i in range(count))
            if projected_shape_valid(profile, shape):
                references.append(shape)
    fixed = topology["fixed"]
    validator = RequestValidator()
    for geometry in ("NORMALIZED", "EXACT"):
        for values in islice(product(*domains.values(), references), 4096):
            duration, resolution, aspect, size, kinds = values
            request = GenerationRequest(
                model.model_id,
                "Local request shape validation",
                method,
                duration=duration,
                resolution=resolution if geometry == "NORMALIZED" else None,
                aspect_ratio=aspect if geometry == "NORMALIZED" else None,
                size=size if geometry == "EXACT" else None,
                generate_audio=False
                if controls.get("generate_audio", {}).get("state") == "SUPPORTED"
                else None,
                first_frame=FrameReference(FrameType.FIRST, "https://example.com/first.png")
                if "first_frame" in fixed
                else None,
                last_frame=FrameReference(FrameType.LAST, "https://example.com/last.png")
                if "last_frame" in fixed
                else None,
                source_video=InputReference(
                    InputReferenceKind.VIDEO, "https://example.com/source.mp4"
                )
                if "source_video" in fixed
                else None,
                input_references=InputReferenceCollection(
                    tuple(
                        InputReference(InputReferenceKind(k), "https://example.com/reference")
                        for k in kinds
                    )
                )
                if kinds
                else None,
            )
            try:
                validator.validate_shape(request)
                validator.validate_capabilities(request, model)
                request.to_openrouter_payload()
            except (ProductFailureError, ValueError, TypeError, KeyError):
                continue
            return request
    return None


def eligible_methods(model: ModelCapabilities) -> tuple[InferenceMethod, ...]:
    return tuple(method for method in InferenceMethod if request_witness(model, method) is not None)
