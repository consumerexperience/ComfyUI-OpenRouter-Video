"""Generic configuration constraints over the existing capability/evidence profile.

Independent catalogue domains remain independent. Only explicit coupling evidence
introduces a relation; missing tuple documentation never creates a global block.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Any

from openrouter_video.models import CapabilityFactState, ModelCapabilities

CONFIGURATION_KEY = "configuration_constraints"
AXES = ("resolution", "aspect_ratio", "duration", "size")
CONTEXT = (
    "inference_method",
    "mode",
    "generate_audio",
    "reference_count",
    "reference_kinds",
    "source_video_present",
)
MAX_VALUES = 1000


def finite_domain(raw: object, *, numeric: bool = False) -> list[Any]:
    """Validate discrete values or a bounded, exact integral range."""
    if numeric and isinstance(raw, dict):
        if set(raw) != {"min", "max", "step"}:
            raise ValueError("Unmapped finite-range vocabulary")
        low, high, step = raw["min"], raw["max"], raw["step"]
        if any(type(v) is not int for v in (low, high, step)):
            raise ValueError("Range requires integer values")
        if low < 0 or high < low or step < 1 or (high - low) % step:
            raise ValueError("Range is not finite/exact")
        if (high - low) // step + 1 > MAX_VALUES:
            raise ValueError("Range exceeds configuration bound")
        raw = list(range(low, high + 1, step))
    values = raw if isinstance(raw, list) else [raw]
    if not values or len(values) > MAX_VALUES:
        raise ValueError("Configuration domain is empty or oversized")
    for value in values:
        if numeric:
            if type(value) is not int or value < 0:
                raise ValueError("Configuration domain requires nonnegative integers")
        elif not isinstance(value, (str, bool)) or (
            isinstance(value, str)
            and (not value or len(value) > 128 or any(ord(c) < 32 for c in value))
        ):
            raise ValueError("Configuration domain value invalid")
    return list(dict.fromkeys(values))


def normalize_constraints(raw: object) -> dict[str, Any]:
    """Reviewed ontology, not a claim that the live API publishes this field."""
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "relations"}:
        raise ValueError("Unmapped configuration vocabulary")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("Unmapped configuration schema")
    relations = raw["relations"]
    if not isinstance(relations, list) or not relations or len(relations) > 256:
        raise ValueError("Configuration relations invalid")
    normalized = []
    for relation in relations:
        if not isinstance(relation, dict) or set(relation) - {
            "axes",
            "when",
            "allowed",
            "forbidden",
            "complete",
        }:
            raise ValueError("Unmapped configuration relation")
        axes = relation.get("axes")
        if not isinstance(axes, list) or not axes or any(type(a) is not str for a in axes):
            raise ValueError("Configuration axes invalid")
        if len(set(axes)) != len(axes):
            raise ValueError("Configuration axes repeated")
        if any(axis not in AXES for axis in axes):
            raise ValueError("Unmapped configuration axis")
        complete = relation.get("complete", False)
        if type(complete) is not bool:
            raise ValueError("Configuration coverage invalid")
        when = relation.get("when", {})
        if not isinstance(when, dict) or set(when) - set(CONTEXT):
            raise ValueError("Unmapped configuration context")
        scope = {
            key: finite_domain(value, numeric=key == "reference_count")
            for key, value in when.items()
        }
        for key in ("generate_audio", "source_video_present"):
            if key in scope and any(type(v) is not bool for v in scope[key]):
                raise ValueError("Configuration boolean context invalid")
        result: dict[str, Any] = {"axes": axes, "when": scope, "complete": complete}
        for kind in ("allowed", "forbidden"):
            rows = relation.get(kind, [])
            if not isinstance(rows, list) or len(rows) > 4096:
                raise ValueError("Configuration rows invalid")
            result[kind] = []
            for row in rows:
                if not isinstance(row, dict) or set(row) != set(axes):
                    raise ValueError("Configuration row must declare every coupled axis")
                domains = {
                    axis: finite_domain(value, numeric=axis == "duration")
                    for axis, value in row.items()
                }
                for axis, values in domains.items():
                    if axis == "duration" and any(v < 1 for v in values):
                        raise ValueError("Duration must be positive")
                    if axis != "duration" and any(type(v) is not str for v in values):
                        raise ValueError("Geometry requires wire strings")
                result[kind].append(domains)
        if not result["allowed"] and not result["forbidden"]:
            raise ValueError("Coupling requires an explicit constraint")
        if complete and not result["allowed"]:
            raise ValueError("Complete relation requires allowed configurations")
        normalized.append(result)
    return {"schema_version": 1, "relations": normalized}


def profile_constraints(model: ModelCapabilities) -> tuple[dict[str, Any], ...]:
    """Persist constraints through the existing provenance-aware evidence cache."""
    result = []
    for fact in model.evidence_facts:
        if fact.key != CONFIGURATION_KEY or fact.value is None:
            continue
        value = normalize_constraints(fact.value)
        for relation in value["relations"]:
            result.append(
                {
                    **relation,
                    "conflict": fact.state is CapabilityFactState.CONFLICT,
                    "provenance": {
                        "authority": fact.authority,
                        "source_reference": fact.source_reference,
                        "observed_at": fact.observed_at,
                        "artifact_version": fact.artifact_version,
                    },
                }
            )
    return tuple(result)


def _scope(relation: Mapping[str, Any], context: Mapping[str, object]) -> bool | None:
    unknown = False
    for key, domain in relation["when"].items():
        value = context.get(key)
        if value is None:
            unknown = True
        elif key == "reference_kinds":
            if not isinstance(value, (tuple, list)) or any(v not in domain for v in value):
                return False
        elif value not in domain:
            return False
    return None if unknown else True


def configuration_status(
    relations: tuple[dict[str, Any], ...],
    selections: Mapping[str, object],
    context: Mapping[str, object],
) -> str:
    """READY, CONFIRMED_INCOMPATIBLE or UNKNOWN_COMBINATION for known coupling only."""
    unknown = False
    for relation in relations:
        applicable = _scope(relation, context)
        if applicable is False:
            continue
        if applicable is None or relation.get("conflict"):
            unknown = True
            continue
        axes = relation["axes"]
        # Omission is not a fabricated provider default. A known coupling needs
        # explicit coupled values unless the relation itself proves an omission.
        if any(selections.get(axis) is None for axis in axes):
            unknown = True
            continue

        def matches(row: Mapping[str, list[object]], bound_axes: list[str] = axes) -> bool:
            return all(selections[axis] in row[axis] for axis in bound_axes)

        if any(matches(row) for row in relation["forbidden"]):
            return "CONFIRMED_INCOMPATIBLE"
        if any(matches(row) for row in relation["allowed"]):
            continue
        if relation["complete"]:
            return "CONFIRMED_INCOMPATIBLE"
        if relation["allowed"]:
            unknown = True
        # An explicit forbidden-only constraint confirms its complement.
    return "UNKNOWN_COMBINATION" if unknown else "READY"


def project_configuration(
    model: ModelCapabilities,
    selections: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, object]:
    """Exclude each control's own selection to permit deliberate repair."""
    domains = {
        axis: getattr(
            model,
            "supported_"
            + {
                "resolution": "resolutions",
                "aspect_ratio": "aspect_ratios",
                "duration": "durations",
                "size": "sizes",
            }[axis],
        )
        for axis in AXES
    }
    relations = profile_constraints(model)
    for axis, domain in domains.items():
        if domain is None:
            confirmed = list(
                dict.fromkeys(
                    value
                    for relation in relations
                    if _scope(relation, context) is not False
                    for row in relation["allowed"]
                    for value in row.get(axis, [])
                )
            )
            if confirmed:
                domains[axis] = tuple(confirmed)
    options: dict[str, object] = {}
    for axis, domain in domains.items():
        if domain is None:
            options[axis] = None
            continue
        candidates = []
        for candidate in domain:
            selected = dict(selections, **{axis: candidate})
            applicable = [r for r in relations if _scope(r, context) is not False]
            involved = sorted({a for r in applicable for a in r["axes"]})
            missing = [a for a in involved if selected.get(a) is None]
            choices = [domains[a] or () for a in missing]
            # Empty unknown axis does not establish any supported tuple.
            count = 1
            for values in choices:
                count *= len(values)
            if count > 100_000:
                continue
            if any(
                configuration_status(
                    relations, dict(selected, **dict(zip(missing, combo, strict=True))), context
                )
                == "READY"
                for combo in product(*choices)
            ):
                candidates.append(candidate)
        options[axis] = candidates
    return {
        "options": options,
        "status": configuration_status(relations, selections, context),
        "relations": relations,
    }
