"""Declarative established-wire recipes. Requirements contain no model IDs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openrouter_video.models import CapabilityFactState, InferenceMethod, ModelCapabilities


@dataclass(frozen=True, slots=True)
class Requirement:
    field: str
    operator: str
    value: object
    optional_when_unknown: bool = False


@dataclass(frozen=True, slots=True)
class Recipe:
    method: InferenceMethod
    requirements: tuple[Requirement, ...]


def reference(kind: str, count: int = 1) -> tuple[Requirement, ...]:
    return (
        Requirement("reference_kinds", "contains", kind),
        Requirement("max_reference_count", "minimum", count, True),
    )


RECIPES = (
    Recipe(
        InferenceMethod.T2V,
        (
            Requirement("supports_text_only", "equals", True),
            Requirement("source_required", "equals", False, True),
        ),
    ),
    Recipe(InferenceMethod.I2V, (Requirement("supported_frame_types", "contains", "first_frame"),)),
    Recipe(
        InferenceMethod.FLF2V,
        (
            Requirement("supported_frame_types", "contains", "first_frame"),
            Requirement("supported_frame_types", "contains", "last_frame"),
        ),
    ),
    Recipe(InferenceMethod.IR2V, reference("image")),
    Recipe(InferenceMethod.MI2V, reference("image", 2)),
    Recipe(InferenceMethod.VR2V, reference("video")),
    Recipe(InferenceMethod.AR2V, reference("audio")),
    Recipe(
        InferenceMethod.MMR2V,
        (
            Requirement("reference_kinds", "length", 2),
            Requirement("mixed_reference_kinds", "equals", True),
            Requirement("max_reference_count", "minimum", 2, True),
        ),
    ),
    Recipe(
        InferenceMethod.V2V_EDIT,
        reference("video") + (Requirement("supports_edit", "equals", True),),
    ),
    Recipe(
        InferenceMethod.V2V_EXTEND,
        reference("video") + (Requirement("supports_extend", "equals", True),),
    ),
)


def evaluate(model: ModelCapabilities, recipe: Recipe) -> str:
    refs = model.input_reference_capabilities
    states = []
    for requirement in recipe.requirements:
        field = requirement.field
        ref_field = field in ("reference_kinds", "max_reference_count", "mixed_reference_kinds")
        if (
            (ref_field and refs and refs.conflicts)
            or any(c.value == field for c in model.capability_conflicts)
            or any(
                fact.key == field and fact.state is CapabilityFactState.CONFLICT
                for fact in model.evidence_facts
            )
        ):
            states.append("CONFLICT")
            continue
        value: Any = getattr(refs if ref_field else model, field, None)
        if value is None:
            states.append("READY" if requirement.optional_when_unknown else "CAPABILITY_SIGNAL_GAP")
            continue
        if requirement.operator == "contains":
            matches = requirement.value in [getattr(v, "value", v) for v in value]
        elif requirement.operator == "length":
            matches = isinstance(requirement.value, int) and len(value) >= requirement.value
        elif requirement.operator == "minimum":
            matches = value >= requirement.value
        else:
            matches = value == requirement.value
        states.append("READY" if matches else "UNSUPPORTED")
    for priority in ("CONFLICT", "UNSUPPORTED", "CAPABILITY_SIGNAL_GAP"):
        if priority in states:
            return priority
    return "READY"
