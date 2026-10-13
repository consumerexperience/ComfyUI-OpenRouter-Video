"""Generic configuration constraints over the existing capability/evidence profile.

Independent catalogue domains remain independent. Only explicit coupling evidence
introduces a relation; missing tuple documentation never creates a global block.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import product
from typing import Any

from openrouter_video.models import CapabilityFactState, InferenceMethod, ModelCapabilities

CONFIGURATION_KEY = "configuration_constraints"
AXES = ("resolution", "aspect_ratio", "duration", "size")
CONTEXT = (
    "geometry_authority",
    "inference_method",
    "mode",
    "generate_audio",
    "reference_count",
    "reference_kinds",
    "source_video_present",
)
MAX_VALUES = 1000
REQUEST_SHAPES_KEY = "request_shape_profiles"
CONTROL_FIELDS = {
    "prompt": None,
    "duration": "supported_durations",
    "resolution": "supported_resolutions",
    "aspect_ratio": "supported_aspect_ratios",
    "size": "supported_sizes",
    "seed": "supports_seed",
    "generate_audio": "generate_audio",
}


def normalize_request_shapes(raw: object) -> dict[str, Any]:
    """Method-scoped facts inside the existing reviewed capability profile."""
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "methods"}:
        raise ValueError("Invalid request-shape vocabulary")
    if raw["schema_version"] != 1 or not isinstance(raw["methods"], dict):
        raise ValueError("Invalid request-shape schema")
    states = {s.value for s in CapabilityFactState}
    for method, entry in raw["methods"].items():
        InferenceMethod(method)
        if not isinstance(entry, dict) or entry.get("state") not in states:
            raise ValueError("Invalid method evidence state")
        for name, control in entry.get("controls", {}).items():
            if name not in CONTROL_FIELDS or control.get("state") not in states:
                raise ValueError("Invalid control evidence state")
            if "values" in control:
                finite_domain(control["values"], numeric=name == "duration")
            if name == "seed" and control["state"] == "SUPPORTED":
                bounds = control.get("integer_range", {})
                if (
                    set(bounds) != {"min", "max"}
                    or any(type(v) is not int for v in bounds.values())
                    or not 0 <= bounds["min"] <= bounds["max"]
                ):
                    raise ValueError("Supported seed needs a confirmed integer domain")
        topology = entry.get("topology", {})
        if entry["state"] == "SUPPORTED":
            if set(topology) != {
                "fixed",
                "reference_kinds",
                "kind_sets",
                "min",
                "max",
                "per_kind_max",
            }:
                raise ValueError("Incomplete supported topology")
            if any(
                r not in {"first_frame", "last_frame", "source_video"} for r in topology["fixed"]
            ):
                raise ValueError("Invalid fixed media role")
            kinds = {"image", "video", "audio"}
            if not set(topology["reference_kinds"]) <= kinds:
                raise ValueError("Invalid reference kinds")
            if any(not set(s) <= set(topology["reference_kinds"]) for s in topology["kind_sets"]):
                raise ValueError("Invalid reference combination")
            low, high = topology["min"], topology["max"]
            if type(low) is not int or type(high) is not int or not 0 <= low <= high <= 100:
                raise ValueError("Invalid reference bounds")
            if any(
                k not in kinds or type(v) is not int or v < 1
                for k, v in topology["per_kind_max"].items()
            ):
                raise ValueError("Invalid per-kind limit")
        if entry.get("relations"):
            normalize_constraints({"schema_version": 1, "relations": entry["relations"]})
    return raw


def request_shape_profile(model: ModelCapabilities) -> dict[str, Any]:
    """No reviewed profile means UNKNOWN, including newly discovered models."""
    facts = [f for f in model.evidence_facts if f.key == REQUEST_SHAPES_KEY]
    if len(facts) != 1 or facts[0].state is not CapabilityFactState.SUPPORTED:
        return {"schema_version": 1, "methods": {}}
    return normalize_request_shapes(facts[0].value)


def project_method(model: ModelCapabilities, method: str) -> dict[str, Any]:
    """Single semantic authority; intersect reviewed scopes with dynamic domains."""
    entry = request_shape_profile(model)["methods"].get(method, {"state": "UNKNOWN"})
    state = entry["state"]
    if (
        state == "UNKNOWN"
        and method == "T2V"
        and (model.supports_text_only is False or model.source_required is True)
    ):
        state = "UNSUPPORTED"
    topology = dict(entry.get("topology", {}))
    if state == "SUPPORTED":
        frames = model.supported_frame_types
        for role in topology["fixed"]:
            if role in {"first_frame", "last_frame"}:
                if frames is None:
                    state = "UNKNOWN"
                elif role not in {frame.value for frame in frames}:
                    state = "CONFLICT"
        refs = model.input_reference_capabilities
        if topology["max"]:
            if refs is None or refs.reference_kinds is None:
                state = "UNKNOWN"
            elif refs.conflicts:
                state = "CONFLICT"
            else:
                kinds = {kind.value for kind in refs.reference_kinds}
                topology["reference_kinds"] = [
                    kind for kind in topology["reference_kinds"] if kind in kinds
                ]
                topology["kind_sets"] = [s for s in topology["kind_sets"] if set(s) <= kinds]
                if refs.max_reference_count is not None:
                    topology["max"] = min(topology["max"], refs.max_reference_count)
                topology["kind_sets"] = [
                    s
                    for s in topology["kind_sets"]
                    if len(s) <= topology["max"]
                    and (len(s) < 2 or refs.mixed_reference_kinds is not False)
                ]
                if not topology["kind_sets"] or topology["max"] < topology["min"]:
                    state = "CONFLICT"
        if method == "T2V" and (model.supports_text_only is False or model.source_required is True):
            state = "CONFLICT"
    controls = {}
    for name, field in CONTROL_FIELDS.items():
        control = dict(entry.get("controls", {}).get(name, {"state": "UNKNOWN"}))
        if field is None:
            controls[name] = control
            continue
        domain = getattr(model, field)
        if control["state"] == "SUPPORTED":
            if name in {"seed", "generate_audio"}:
                if domain is not True:
                    control["state"] = "UNSUPPORTED" if domain is False else "UNKNOWN"
            elif domain is None:
                control["state"] = "UNKNOWN"
            else:
                values = [v for v in domain if "values" not in control or v in control["values"]]
                control["values"] = values
                if not values:
                    control["state"] = "UNKNOWN"
        if control["state"] != "SUPPORTED":
            control.pop("values", None)
        controls[name] = control
    relations = list(profile_constraints(model))
    if entry.get("relations"):
        relations.extend(
            normalize_constraints({"schema_version": 1, "relations": entry["relations"]})[
                "relations"
            ]
        )
    return {
        "state": state,
        "controls": controls,
        "topology": topology,
        "configuration_relations": relations,
    }


def project_semantic_values(
    model: ModelCapabilities, method: str, values: Mapping[str, object]
) -> dict[str, Any]:
    """Omit hidden raw state before parsing, validation, pricing or encoding."""
    profile = project_method(model, method)
    if profile["state"] != "SUPPORTED":
        raise ValueError("Inference method is not supported by the current projection")
    result: dict[str, Any] = {}
    for name, control in profile["controls"].items():
        if control["state"] != "SUPPORTED":
            result[name] = None
            continue
        value = values.get(name)
        if name == "prompt":
            result[name] = value if isinstance(value, str) and value.strip() else None
            continue
        if isinstance(value, str):
            value = value.strip() or None
        supported = True
        if name == "seed":
            try:
                parsed = int(value) if isinstance(value, str) else value
            except ValueError:
                parsed = None
            bounds = control["integer_range"]
            result[name] = (
                parsed if type(parsed) is int and bounds["min"] <= parsed <= bounds["max"] else None
            )
        elif name == "generate_audio":
            result[name] = value if supported and type(value) is bool else None
        else:
            typed = name != "duration" or type(value) is int
            result[name] = value if supported and typed and value in control["values"] else None
    authority = values.get("geometry_authority")
    if authority == "EXACT" and result["size"] is not None:
        result["resolution"] = result["aspect_ratio"] = None
    elif authority == "NORMALIZED":
        result["size"] = None
    for role in ("first_frame", "last_frame", "source_video"):
        result[role] = values.get(role) if role in profile["topology"]["fixed"] else None
    for role in ("direct_references", "input_references"):
        result[role] = values.get(role) if profile["topology"]["max"] else None
    return result


def projected_shape_valid(profile: Mapping[str, Any], kinds: tuple[str, ...]) -> bool:
    """Validate complete ordered shape, without deriving a Cartesian modality set."""
    topology = profile["topology"]
    if not topology["min"] <= len(kinds) <= topology["max"]:
        return False
    if set(kinds) not in [set(s) for s in topology["kind_sets"]]:
        return False
    return all(kinds.count(k) <= v for k, v in topology["per_kind_max"].items())


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
