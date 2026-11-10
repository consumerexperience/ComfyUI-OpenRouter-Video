"""Generic configuration constraints over the existing capability/evidence profile.

Independent catalogue domains remain independent. Only explicit coupling evidence
introduces a relation; missing tuple documentation never creates a global block.
"""

from __future__ import annotations

import math
import re
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
    "reference_count_image",
    "reference_count_video",
    "reference_count_audio",
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
    "upscale_factor": "upscale_factor",
    "creativity": "creativity",
    "previous_job_id": None,
    "provider_options": None,
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
            if "required" in control and type(control["required"]) is not bool:
                raise ValueError("Required control marker must be boolean")
            if name == "provider_options" and control.get("state") == "SUPPORTED":
                providers = control.get("providers")
                if not isinstance(providers, dict) or not providers:
                    raise ValueError("Provider options need a reviewed schema")
                for provider, options in providers.items():
                    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", provider) or not isinstance(
                        options, dict
                    ):
                        raise ValueError("Invalid reviewed provider schema")
                    for key, spec in options.items():
                        if (
                            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key)
                            or not isinstance(spec, dict)
                            or set(spec) - {"type", "min", "max", "values", "container", "default"}
                            or spec.get("type") not in {"string", "boolean", "integer", "number"}
                            or spec.get("container") not in {None, "parameters"}
                        ):
                            raise ValueError("Invalid reviewed provider option")
            if name not in CONTROL_FIELDS or control.get("state") not in states:
                raise ValueError("Invalid control evidence state")
            if "values" in control:
                finite_domain(control["values"], numeric=name in {"duration", "creativity"})
            if name == "seed" and control["state"] == "SUPPORTED" and "integer_range" in control:
                bounds = control["integer_range"]
                if (
                    not isinstance(bounds, dict)
                    or set(bounds) != {"min", "max"}
                    or any(type(v) is not int for v in bounds.values())
                    or not 0 <= bounds["min"] <= bounds["max"]
                ):
                    raise ValueError("Invalid declared seed integer bounds")
        topology = entry.get("topology", {})
        if entry["state"] == "SUPPORTED":
            if set(topology) - {"source_alternative"} != {
                "fixed",
                "reference_kinds",
                "kind_sets",
                "min",
                "max",
                "per_kind_max",
            }:
                raise ValueError("Incomplete supported topology")
            if "source_alternative" in topology and (
                topology["source_alternative"] != "previous_job_id"
                or "source_video" not in topology["fixed"]
            ):
                raise ValueError("Invalid source alternative")
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
        if entry.get("media_limits"):
            for role, limits in entry["media_limits"].items():
                if role not in {"source_video", "image", "video", "audio"} or not isinstance(
                    limits, dict
                ):
                    raise ValueError("Invalid media limit role")
                if set(limits) - {
                    "max_duration_seconds",
                    "max_bytes",
                    "max_total_duration_seconds",
                }:
                    raise ValueError("Unknown media limit")
                if any(
                    type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                    for value in limits.values()
                ):
                    raise ValueError("Invalid positive media limit")
        if entry.get("relations"):
            normalize_constraints({"schema_version": 1, "relations": entry["relations"]})
    return raw


def _catalogue_control(model: ModelCapabilities, key: str) -> Any:
    facts = [
        f for f in model.evidence_facts if f.key == key and f.authority == "LIVE_STRUCTURED_API"
    ]
    return (
        facts[0].value
        if len(facts) == 1 and facts[0].state is CapabilityFactState.SUPPORTED
        else None
    )


def _provider_options(
    control: Mapping[str, Any], value: object, model: ModelCapabilities
) -> object:
    """Typed reviewed parameters intersected with the live model allowlist."""
    from openrouter_video.models import ProviderOption

    if value in (None, "", ()):
        value = tuple(
            ProviderOption(provider, key, spec["default"], spec.get("container"))
            for provider, options in control.get("providers", {}).items()
            for key, spec in options.items()
            if "default" in spec
        )
    if not isinstance(value, tuple) or not all(isinstance(v, ProviderOption) for v in value):
        raise ValueError("Provider options must be typed values")
    allowed = _catalogue_control(model, "allowed_passthrough_parameters")
    providers = control.get("providers", {})
    seen = set()
    for option in value:
        spec = providers.get(option.provider, {}).get(option.key)
        binding = (option.provider, option.container, option.key)
        if (
            not isinstance(spec, dict)
            or not isinstance(allowed, (tuple, list))
            or option.key not in allowed
            or binding in seen
            or option.container != spec.get("container")
        ):
            raise ValueError("Provider option lacks reviewed and live support")
        seen.add(binding)
        types: dict[str, Any] = {
            "string": str,
            "boolean": bool,
            "integer": int,
            "number": (int, float),
        }
        expected = types.get(str(spec.get("type")))
        if (
            expected is None
            or not isinstance(option.value, expected)
            or (spec.get("type") != "boolean" and isinstance(option.value, bool))
        ):
            raise ValueError("Provider option type does not match its contract")
        if (
            isinstance(option.value, (float, int))
            and not isinstance(option.value, bool)
            and (
                not math.isfinite(option.value)
                or ("min" in spec and option.value < spec["min"])
                or ("max" in spec and option.value > spec["max"])
            )
        ):
            raise ValueError("Provider option outside reviewed bounds")
        if "values" in spec and option.value not in spec["values"]:
            raise ValueError("Provider option outside reviewed values")
    return value


def request_shape_profile(model: ModelCapabilities) -> dict[str, Any]:
    """No reviewed profile means UNKNOWN, including newly discovered models."""
    facts = [f for f in model.evidence_facts if f.key == REQUEST_SHAPES_KEY]
    if len(facts) != 1 or facts[0].state is not CapabilityFactState.SUPPORTED:
        return {"schema_version": 1, "methods": {}}
    return normalize_request_shapes(facts[0].value)


def project_method(model: ModelCapabilities, method: str) -> dict[str, Any]:
    """Single semantic authority; intersect reviewed scopes with dynamic domains."""
    methods = request_shape_profile(model)["methods"]
    entry = methods.get(method)
    if entry is None:
        # Canonical frame_images is a documented generic wire contract. Positive
        # exact-model structured frame signals suffice; no reference/task shape
        # is inferred, and an explicit reviewed UNKNOWN/CONFLICT is never replaced.
        live = {f.key: f for f in model.evidence_facts if f.authority == "LIVE_STRUCTURED_API"}
        roles = {"T2V": [], "I2V": ["first_frame"], "FLF2V": ["first_frame", "last_frame"]}.get(
            method
        )
        frame_signal = live.get("supported_frame_images")
        text_signal = live.get("supports_text_only")
        positive = roles is not None and (
            bool(roles)
            and frame_signal is not None
            and frame_signal.state is CapabilityFactState.SUPPORTED
            and isinstance(frame_signal.value, (tuple, list))
            and set(roles) <= set(frame_signal.value)
            or method == "T2V"
            and text_signal is not None
            and text_signal.state is CapabilityFactState.SUPPORTED
            and text_signal.value is True
        )
        if positive:
            entry = {
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
                    "fixed": roles,
                    "reference_kinds": [],
                    "kind_sets": [[]],
                    "min": 0,
                    "max": 0,
                    "per_kind_max": {},
                },
            }
        else:
            entry = {"state": "UNKNOWN"}
    state = entry["state"]
    if (
        state == "UNKNOWN"
        and method == "T2V"
        and (model.supports_text_only is False or model.source_required is True)
    ):
        state = "UNSUPPORTED"
    topology = dict(entry.get("topology", {}))
    if state == "SUPPORTED" and topology.get("min") == topology.get("max") == 0:
        topology["kind_sets"] = [[]]
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
        if name in {
            "upscale_factor",
            "creativity",
            "previous_job_id",
            "provider_options",
        } and name not in entry.get("controls", {}):
            continue
        control = dict(entry.get("controls", {}).get(name, {"state": "UNKNOWN"}))
        if field is None:
            if name == "provider_options" and control.get("state") == "SUPPORTED":
                allowed = _catalogue_control(model, "allowed_passthrough_parameters")
                allowed_keys = set(allowed) if isinstance(allowed, (tuple, list)) else set()
                providers = {
                    provider: {key: spec for key, spec in options.items() if key in allowed_keys}
                    for provider, options in control.get("providers", {}).items()
                }
                control["providers"] = {key: value for key, value in providers.items() if value}
                if not control["providers"]:
                    control["state"] = "UNKNOWN"
            controls[name] = control
            continue
        domain = (
            _catalogue_control(model, field)
            if name in {"upscale_factor", "creativity"}
            else getattr(model, field)
        )
        if control["state"] == "SUPPORTED":
            if name in {"seed", "generate_audio"}:
                if domain is not True:
                    control["state"] = "UNSUPPORTED" if domain is False else "UNKNOWN"
            elif name == "upscale_factor":
                if not isinstance(domain, dict) or not {"min", "max"} <= set(domain):
                    control["state"] = "UNKNOWN"
                else:
                    control["number_range"] = dict(domain)
            elif name == "creativity":
                if not isinstance(domain, dict) or not {"min", "max"} <= set(domain):
                    control["state"] = "UNKNOWN"
                else:
                    live = domain.get(
                        "values", list(range(int(domain["min"]), int(domain["max"]) + 1))
                    )
                    control["values"] = [
                        v for v in live if "values" not in control or v in control["values"]
                    ]
                    if not control["values"]:
                        control["state"] = "UNKNOWN"
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
    if state == "SUPPORTED":
        required = {
            "prompt",
            *(name for name, control in controls.items() if control.get("required", False)),
        }
        for name in required:
            control_state = controls.get(name, {}).get("state", "UNKNOWN")
            if control_state != "SUPPORTED":
                state = "CONFLICT" if control_state == "CONFLICT" else "UNKNOWN"
                break
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
        **({"media_limits": entry["media_limits"]} if entry.get("media_limits") else {}),
    }


def project_semantic_values(
    model: ModelCapabilities, method: str, values: Mapping[str, object]
) -> dict[str, Any]:
    """Omit hidden raw state before parsing, validation, pricing or encoding."""
    profile = project_method(model, method)
    if profile["state"] != "SUPPORTED":
        raise ValueError("Inference method is not supported by the current projection")
    result: dict[str, Any] = {}
    if (
        values.get("provider_options")
        and profile["controls"].get("provider_options", {}).get("state") != "SUPPORTED"
    ):
        raise ValueError(
            "Saved provider controls are no longer supported; choose an explicit replacement"
        )
    for name, control in profile["controls"].items():
        if control["state"] != "SUPPORTED":
            result[name] = () if name == "provider_options" else None
            continue
        value = values.get(name)
        if name == "provider_options":
            result[name] = _provider_options(control, value, model)
            continue
        if name == "previous_job_id":
            if value in (None, ""):
                result[name] = None
            elif isinstance(value, str) and re.fullmatch(r"gen-vid-\d+-[0-9A-Za-z]{20}", value):
                result[name] = value
            else:
                raise ValueError("Invalid completed video job ID")
            continue
        if name == "upscale_factor":
            bounds = control.get("number_range", {})
            if value in (None, 0, ""):
                result[name] = None
            elif (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and (bounds.get("min", 0) <= value <= bounds.get("max", float("inf")))
                and value > 0
            ):
                result[name] = value
            else:
                raise ValueError("Upscale factor outside live capability range")
            continue
        if name == "creativity":
            if value in (None, -1, ""):
                result[name] = None
            elif type(value) is int and value in control.get("values", []):
                result[name] = value
            else:
                raise ValueError("Creativity outside live capability values")
            continue
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
            bounds = control.get("integer_range")
            in_bounds = type(parsed) is int and (
                bounds is None or bounds["min"] <= parsed <= bounds["max"]
            )
            # -1 remains the node's no-seed sentinel, not an upstream seed value.
            result[name] = parsed if parsed != -1 and in_bounds else None
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
            key: finite_domain(
                value, numeric=key == "reference_count" or key.startswith("reference_count_")
            )
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
        if value is None and key.startswith("reference_count_"):
            kinds = context.get("reference_kinds")
            if isinstance(kinds, (tuple, list)) and all(isinstance(k, str) for k in kinds):
                value = kinds.count(key.removeprefix("reference_count_"))
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
