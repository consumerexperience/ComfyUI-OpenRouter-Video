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
        if set(entry) - {
            "state",
            "controls",
            "topology",
            "media_limits",
            "relations",
            "notes",
            "audit_scope",
            "evidence_class",
            "historical_findings",
            "live_exception",
            "live_shape_receipt",
            "observed_at",
            "provider_notes",
            "review_sources",
            "topology_scope",
            "wire_shape",
        }:
            raise ValueError("Unknown method contract semantics")
        for name, control in entry.get("controls", {}).items():
            if not isinstance(control, dict) or set(control) - {
                "state",
                "required",
                "values",
                "integer_range",
                "min_length",
                "max_length",
                "providers",
                "notes",
            }:
                raise ValueError("Unknown control contract semantics")
            if any(
                type(control[key]) is not int or control[key] < 0
                for key in ("min_length", "max_length")
                if key in control
            ):
                raise ValueError("Invalid documented text bound")
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
                        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key) or not isinstance(
                            spec, dict
                        ):
                            raise ValueError("Invalid reviewed provider option")
                        _validate_provider_spec(spec)
                        dependencies = spec.get("requires", {})
                        if not isinstance(dependencies, dict) or any(
                            key not in options or not isinstance(domain, list) or not domain
                            for key, domain in dependencies.items()
                        ):
                            raise ValueError("Invalid reviewed provider dependencies")
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
                    "min_duration_seconds",
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


def _provider_field_names(raw: object, fields: Mapping[str, Any]) -> list[str]:
    if (
        not isinstance(raw, list)
        or any(not isinstance(v, str) for v in raw)
        or len(raw) != len(set(raw))
        or not set(raw) <= set(fields)
    ):
        raise ValueError("Invalid reviewed provider field names")
    return raw


def _validate_provider_rules(rules: Mapping[str, Any], fields: Mapping[str, Any]) -> None:
    _provider_field_names(rules.get("required_fields", []), fields)
    groups = rules.get("one_of_required", [])
    if not isinstance(groups, list):
        raise ValueError("Invalid provider exclusive fields")
    for group in groups:
        if not _provider_field_names(group, fields):
            raise ValueError("Empty provider exclusive group")
    order = rules.get("ordered_fields")
    if order is not None and len(_provider_field_names(order, fields)) != 2:
        raise ValueError("Provider order requires two fields")


def _validate_provider_spec(spec: Mapping[str, Any], depth: int = 0) -> None:
    allowed = {
        "type",
        "min",
        "max",
        "values",
        "container",
        "default",
        "fields",
        "omitted_default",
        "required",
        "required_fields",
        "variants",
        "one_of_required",
        "items",
        "min_items",
        "max_items",
        "uniform_fields",
        "ordered_fields",
        "min_length",
        "max_length",
        "exclusive_min",
        "format",
        "requires",
        "time_range",
        "omits_controls",
        "omit_when",
    }
    if depth > 4 or set(spec) - allowed or spec.get("container") not in {None, "parameters"}:
        raise ValueError("Invalid reviewed provider option schema")
    if "required" in spec and type(spec["required"]) is not bool:
        raise ValueError("Invalid required provider marker")
    if "omits_controls" in spec:
        _provider_field_names(
            spec["omits_controls"], {key: None for key in ("resolution", "aspect_ratio", "size")}
        )
    if "omit_when" in spec and (
        "omits_controls" not in spec
        or not isinstance(spec["omit_when"], list)
        or not spec["omit_when"]
    ):
        raise ValueError("Invalid conditional geometry omission")
    kind = spec.get("type")
    if kind == "array":
        low, high, items = spec.get("min_items"), spec.get("max_items"), spec.get("items")
        if (
            type(low) is not int
            or type(high) is not int
            or not 1 <= low <= high <= 64
            or not isinstance(items, dict)
            or items.get("container")
            or set(spec) - {"type", "items", "min_items", "max_items", "uniform_fields", "required"}
        ):
            raise ValueError("Provider array needs bounded reviewed items")
        _validate_provider_spec(items, depth + 1)
        if "uniform_fields" in spec:
            _provider_field_names(spec["uniform_fields"], items.get("fields", {}))
        return
    if kind == "object":
        fields = spec.get("fields")
        if (
            not isinstance(fields, dict)
            or not 1 <= len(fields) <= 64
            or set(spec)
            - {
                "type",
                "fields",
                "required_fields",
                "variants",
                "one_of_required",
                "ordered_fields",
                "required",
                "container",
                "time_range",
            }
        ):
            raise ValueError("Provider object needs reviewed fields")
        for key, child in fields.items():
            if (
                not isinstance(key, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", key)
                or not isinstance(child, dict)
                or child.get("container")
            ):
                raise ValueError("Invalid nested provider field")
            _validate_provider_spec(child, depth + 1)
        _validate_provider_rules(spec, fields)
        if "time_range" in spec:
            rule = spec["time_range"]
            if not isinstance(rule, dict) or set(rule) != {
                "absolute_field",
                "range_field",
                "start",
                "end",
            }:
                raise ValueError("Invalid reviewed temporal relation")
            if (
                rule["absolute_field"] not in fields
                or rule["range_field"] not in fields
                or not {rule["start"], rule["end"]}
                <= set(fields[rule["range_field"]].get("fields", {}))
            ):
                raise ValueError("Temporal relation lacks reviewed fields")
        variants = spec.get("variants")
        if variants is not None:
            if (
                not isinstance(variants, dict)
                or set(variants) != {"discriminator_field", "cases"}
                or variants.get("discriminator_field") not in fields
                or not isinstance(variants.get("cases"), dict)
            ):
                raise ValueError("Invalid provider object variants")
            discriminator = variants["discriminator_field"]
            if fields[discriminator].get("type") != "string" or set(variants["cases"]) != set(
                fields[discriminator].get("values", [])
            ):
                raise ValueError("Provider variant discriminator lacks complete values")
            for rules in variants["cases"].values():
                if not isinstance(rules, dict) or set(rules) - {
                    "allowed_fields",
                    "required_fields",
                    "one_of_required",
                    "field_values",
                }:
                    raise ValueError("Invalid provider variant case")
                names = _provider_field_names(rules.get("allowed_fields"), fields)
                if discriminator not in names:
                    raise ValueError("Provider variant must retain its discriminator")
                selected = {key: fields[key] for key in names}
                _validate_provider_rules(rules, selected)
                field_values = rules.get("field_values", {})
                if not isinstance(field_values, dict) or not set(field_values) <= set(selected):
                    raise ValueError("Invalid provider variant fields")
                for key, values in field_values.items():
                    if (
                        fields[key].get("type") != "string"
                        or not isinstance(values, list)
                        or not values
                        or any(not isinstance(v, str) for v in values)
                        or len(values) != len(set(values))
                        or not set(values) <= set(fields[key].get("values", values))
                    ):
                        raise ValueError("Invalid provider variant values")
        return
    if kind not in {"string", "boolean", "integer", "number"} or set(spec) & {
        "fields",
        "required_fields",
        "variants",
        "items",
        "min_items",
        "max_items",
        "uniform_fields",
        "one_of_required",
        "ordered_fields",
    }:
        raise ValueError("Invalid reviewed provider leaf")
    if "values" in spec and (not isinstance(spec["values"], list) or not spec["values"]):
        raise ValueError("Invalid reviewed provider enum")
    expected: dict[str, Any] = {
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
    }
    for label in ("default", "omitted_default"):
        if label not in spec:
            continue
        value = spec[label]
        if not isinstance(value, expected[kind]) or (kind != "boolean" and isinstance(value, bool)):
            raise ValueError("Provider default type differs from its reviewed leaf")
        if "values" in spec and value not in spec["values"]:
            raise ValueError("Provider default outside reviewed enum")
        if kind in {"number", "integer"} and (
            not math.isfinite(value)
            or value < spec.get("min", -math.inf)
            or value > spec.get("max", math.inf)
        ):
            raise ValueError("Provider default outside reviewed bounds")
    if "format" in spec and spec["format"] not in {"https_url", "runway_image_uri", "hex_color"}:
        raise ValueError("Unknown reviewed provider format")


def _provider_value_present(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _validate_provider_object(spec: Mapping[str, Any], value: Any) -> None:
    """Validate composites assembled only from reviewed scalar leaves."""
    if spec["type"] == "array":
        if not isinstance(value, list) or not spec["min_items"] <= len(value) <= spec["max_items"]:
            raise ValueError("Provider array outside reviewed item count")
        for child in value:
            _validate_provider_object(spec["items"], child)
        for name in spec.get("uniform_fields", []):
            if len({name in item for item in value}) > 1:
                raise ValueError("Provider array requires uniform optional fields")
        return
    if spec["type"] != "object":
        return
    fields = spec["fields"]
    if not isinstance(value, dict) or not set(value) <= set(fields):
        raise ValueError("Provider object contains an unreviewed field")
    required = set(spec.get("required_fields", []))
    exclusive = list(spec.get("one_of_required", []))
    variants = spec.get("variants")
    if variants:
        discriminator = variants["discriminator_field"]
        case = variants["cases"].get(value.get(discriminator))
        if case is None:
            raise ValueError("Provider object is missing a supported discriminator")
        if not set(value) <= set(case["allowed_fields"]):
            raise ValueError("Provider object contains fields for another variant")
        required.update(case.get("required_fields", []))
        exclusive.extend(case.get("one_of_required", []))
        for name, values in case.get("field_values", {}).items():
            if name in value and value[name] not in values:
                raise ValueError("Provider object field is outside variant values")
    if any(not _provider_value_present(value.get(name)) for name in required):
        raise ValueError("Provider object is missing required fields")
    for names in exclusive:
        if sum(_provider_value_present(value.get(name)) for name in names) != 1:
            raise ValueError("Provider object must supply exactly one alternative")
    if "ordered_fields" in spec:
        first, last = spec["ordered_fields"]
        if first in value and last in value and value[first] >= value[last]:
            raise ValueError("Provider range end must exceed its start")
    if "time_range" in spec:
        rule = spec["time_range"]
        if rule["absolute_field"] in value and rule["range_field"] in value:
            interval = value[rule["range_field"]]
            if (
                rule["start"] in interval
                and rule["end"] in interval
                and not interval[rule["start"]]
                <= value[rule["absolute_field"]]
                < interval[rule["end"]]
            ):
                raise ValueError("Provider keyframe must lie within its exclusive range")
    for name, child_value in value.items():
        if fields[name].get("type") in {"object", "array"}:
            _validate_provider_object(fields[name], child_value)


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
    from openrouter_video.models import ProviderOption, _check_provider_tree, _insert_provider_leaf

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
    supplied: dict[tuple[str, str | None, str], Any] = {}
    for option in value:
        spec = providers.get(option.provider, {}).get(option.key)
        binding = (option.provider, option.container, option.key, option.path)
        if (
            not isinstance(spec, dict)
            or not isinstance(allowed, (tuple, list))
            or option.key not in allowed
            or binding in seen
            or option.container != spec.get("container")
        ):
            raise ValueError("Provider option lacks reviewed and live support")
        seen.add(binding)
        group_key = (option.provider, option.container, option.key)
        holder = {"value": supplied[group_key]} if group_key in supplied else {}
        _insert_provider_leaf(holder, ("value", *option.path), option.value)
        supplied[group_key] = holder["value"]
        for component in option.path:
            if (
                spec.get("type") == "array"
                and type(component) is int
                and 0 <= component < spec["max_items"]
            ):
                spec = spec["items"]
            elif (
                spec.get("type") == "object"
                and isinstance(component, str)
                and component in spec["fields"]
            ):
                spec = spec["fields"][component]
            else:
                raise ValueError("Provider object field lacks reviewed support")
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
        if "exclusive_min" in spec and option.value <= spec["exclusive_min"]:
            raise ValueError("Provider option outside reviewed exclusive bound")
        if isinstance(option.value, str):
            if (
                not spec.get("min_length", 0)
                <= len(option.value)
                <= spec.get("max_length", float("inf"))
            ):
                raise ValueError("Provider text outside reviewed length bounds")
            if (
                spec.get("format") == "hex_color"
                and re.fullmatch(r"#[0-9A-Fa-f]{6}", option.value) is None
            ):
                raise ValueError("Provider background color requires a hex color")
            if spec.get("format") == "https_url" and not option.value.startswith("https://"):
                raise ValueError("Provider media requires a public HTTPS URL")
            if spec.get("format") == "runway_image_uri":
                limit = (
                    5242880
                    if option.value.startswith("data:image/")
                    else 5000
                    if option.value.startswith("runway://")
                    else 2048
                    if option.value.startswith("https://")
                    else 0
                )
                if not 13 <= len(option.value) <= limit:
                    raise ValueError("Provider image URI outside reviewed forms or length")
    _check_provider_tree(supplied)
    for (provider, _container, key), grouped in supplied.items():
        spec = providers[provider][key]
        if spec.get("type") in {"object", "array"}:
            _validate_provider_object(spec, grouped)
    for provider, options in providers.items():
        for key, spec in options.items():
            if spec.get("required") is True and not _provider_value_present(
                supplied.get((provider, spec.get("container"), key))
            ):
                raise ValueError("Required provider option is missing")
            selected = supplied.get((provider, spec.get("container"), key))
            if selected is not None:
                for dependency, domain in spec.get("requires", {}).items():
                    effective = supplied.get(
                        (provider, options[dependency].get("container"), dependency),
                        options[dependency].get("omitted_default"),
                    )
                    if effective not in domain:
                        raise ValueError("Provider option requires a compatible dependent setting")
    return value


def request_shape_profile(model: ModelCapabilities) -> dict[str, Any]:
    """A current structured API recipe supersedes historical recipe observations."""
    facts = [f for f in model.evidence_facts if f.key == REQUEST_SHAPES_KEY]
    live = [f for f in facts if f.authority == "LIVE_STRUCTURED_API"]
    if live:
        facts = live
    if len(facts) != 1 or facts[0].state is not CapabilityFactState.SUPPORTED:
        return {"schema_version": 1, "methods": {}}
    return normalize_request_shapes(facts[0].value)


def derive_catalogue_method(model: ModelCapabilities, method: str) -> dict[str, Any] | None:
    """Interpret explicit Level-A reference primitives through established wire recipes."""
    from itertools import combinations

    live = {f.key: f for f in model.evidence_facts if f.authority == "LIVE_STRUCTURED_API"}

    def positive(key: str) -> bool:
        return key in live and live[key].state is CapabilityFactState.SUPPORTED

    if not (positive("reference_kinds") and positive("max_reference_count")):
        return None
    refs = model.input_reference_capabilities
    if refs is None or refs.reference_kinds is None or refs.max_reference_count is None:
        return None
    kinds = sorted(k.value for k in refs.reference_kinds)
    maximum = refs.max_reference_count
    selected = {"IR2V": "image", "MI2V": "image", "VR2V": "video", "AR2V": "audio"}
    minimum = 2 if method in {"MI2V", "MMR2V"} else 1
    fixed: list[str] = []
    if method == "MMR2V":
        if not positive("mixed_reference_kinds") or refs.mixed_reference_kinds is not True:
            return None
        sets = [
            list(s) for n in range(2, min(len(kinds), maximum) + 1) for s in combinations(kinds, n)
        ]
    elif method in selected and selected[method] in kinds:
        kinds = [selected[method]]
        sets = [kinds]
        if method == "IR2V":
            maximum = min(1, maximum)
    else:
        return None
    if not sets or maximum < minimum:
        return None
    return {
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
            "min": minimum,
            "max": maximum,
            "per_kind_max": {k: maximum for k in kinds},
        },
    }


def project_method(model: ModelCapabilities, method: str) -> dict[str, Any]:
    """Single semantic authority; intersect reviewed scopes with dynamic domains."""
    methods = request_shape_profile(model)["methods"]
    entry = methods.get(method)
    if entry is None and any(
        f.key == REQUEST_SHAPES_KEY
        and (f.authority == "LIVE_STRUCTURED_API" or f.state is not CapabilityFactState.SUPPORTED)
        for f in model.evidence_facts
    ):
        entry = {"state": "UNKNOWN"}
    if entry is None:
        entry = derive_catalogue_method(model, method)
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
            name for name, control in controls.items() if control.get("required", name == "prompt")
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
    option_schema = profile["controls"].get("provider_options", {}).get("providers", {})
    for option in result.get("provider_options", ()):
        spec = option_schema[option.provider][option.key]
        if "omits_controls" in spec and (
            "omit_when" not in spec or option.value in spec["omit_when"]
        ):
            for name in spec["omits_controls"]:
                result[name] = None
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
