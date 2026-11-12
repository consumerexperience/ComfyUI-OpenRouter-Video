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
                "domain_completeness",
            }:
                raise ValueError("Unknown control contract semantics")
            if control.get("domain_completeness", "COMPLETE") not in {"COMPLETE", "PARTIAL"}:
                raise ValueError("Invalid documented domain completeness")
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
            if set(topology) - {
                "source_alternative",
                "verified_configurations",
                "per_kind_min",
                "required_kinds",
                "mutually_exclusive",
                "constraint_state",
                "constraint_evidence",
                "transport_max",
                "transport_per_kind_max",
                "transport_min",
                "transport_per_kind_min",
                "transport_required_kinds",
                "transport_mutually_exclusive",
            } != {
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
            if (
                type(low) is not int
                or low < 0
                or (high is not None and (type(high) is not int or high < low))
            ):
                raise ValueError("Invalid reference bounds")
            if any(
                k not in kinds or type(v) is not int or v < 0
                for k, v in topology["per_kind_max"].items()
            ):
                raise ValueError("Invalid per-kind limit")
            for k, v in topology.get("per_kind_min", {}).items():
                if k not in kinds or type(v) is not int or v < 0:
                    raise ValueError("Invalid per-kind minimum")
            if not set(topology.get("required_kinds", [])) <= set(topology["reference_kinds"]):
                raise ValueError("Invalid required media kinds")
            if any(
                not set(group) <= kinds or len(set(group)) < 2
                for group in topology.get("mutually_exclusive", [])
            ):
                raise ValueError("Invalid mutually exclusive media kinds")
            if topology.get("constraint_state", "SUPPORTED") not in states:
                raise ValueError("Invalid input constraint state")
            for name in ("transport_min", "transport_max"):
                transport = topology.get(name)
                if transport is not None and (type(transport) is not int or transport < 0):
                    raise ValueError("Invalid transport total bound")
            if any(
                k not in kinds or type(v) is not int or v < 0
                for k, v in topology.get("transport_per_kind_max", {}).items()
            ):
                raise ValueError("Invalid transport per-kind bound")
            if any(
                k not in kinds or type(v) is not int or v < 0
                for k, v in topology.get("transport_per_kind_min", {}).items()
            ):
                raise ValueError("Invalid transport per-kind minimum")
            if not set(topology.get("transport_required_kinds", [])) <= kinds or any(
                not isinstance(group, list)
                or not all(isinstance(k, str) and k in kinds for k in group)
                or len(set(group)) < 2
                for group in topology.get("transport_mutually_exclusive", [])
            ):
                raise ValueError("Invalid transport media combination")
            declarations = topology.get("constraint_evidence", {})
            if not isinstance(declarations, dict):
                raise ValueError("Invalid input constraint provenance")
            for field, declaration in declarations.items():
                if field not in {
                    "max",
                    "per_kind_max",
                    "verified_configurations",
                    "per_kind_min",
                    "required_kinds",
                    "mutually_exclusive",
                } or not isinstance(declaration, dict):
                    raise ValueError("Invalid scoped input constraint declaration")
                if declaration.get("state") not in states or declaration.get("scope") not in {
                    None,
                    "method",
                    "total",
                    "per_kind",
                }:
                    raise ValueError("Invalid scoped input constraint status")
                if declaration.get("state") == "SUPPORTED" and not declaration.get("source"):
                    raise ValueError("Confirmed input bound needs explicit provenance")
                if any(
                    not isinstance(v, str)
                    for k, v in declaration.items()
                    if k in {"source", "reason", "classification"}
                ):
                    raise ValueError("Invalid input constraint provenance text")
            configurations = topology.get("verified_configurations", [])
            if not isinstance(configurations, list) or any(
                not isinstance(counts, dict)
                or not counts
                or not set(counts) <= set(topology["reference_kinds"])
                or any(type(n) is not int or n <= 0 for n in counts.values())
                or set(counts) not in [set(group) for group in topology["kind_sets"]]
                for counts in configurations
            ):
                raise ValueError("Invalid documented reference configurations")
            if configurations:
                proof = declarations.get("verified_configurations", {})
                if (
                    proof.get("state") != "SUPPORTED"
                    or proof.get("scope") != "method"
                    or not proof.get("source", "").startswith("https://openrouter.ai/")
                ):
                    raise ValueError("Documented configurations need scoped OpenRouter evidence")
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
                    "max_combined_duration_seconds",
                    "min_width",
                    "max_width",
                    "min_height",
                    "max_height",
                    "min_pixels",
                    "max_pixels",
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

    if not positive("reference_kinds") or not (
        positive("max_reference_count") or positive("per_kind_max")
    ):
        return None
    refs = model.input_reference_capabilities
    if refs is None or refs.reference_kinds is None:
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
            list(s)
            for n in range(2, min(len(kinds), maximum if maximum is not None else len(kinds)) + 1)
            for s in combinations(kinds, n)
        ]
    elif method in selected and selected[method] in kinds:
        kinds = [selected[method]]
        sets = [kinds]
        if method == "IR2V":
            maximum = min(1, maximum) if maximum is not None else 1
    else:
        return None
    if not sets or (maximum is not None and maximum < minimum):
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
            "per_kind_max": {},
        },
    }


def effective_input_constraints(
    model: ModelCapabilities, method: str, entry: Mapping[str, Any]
) -> dict[str, Any]:
    """Compose independent scoped bounds; a per-kind cap never becomes a total."""
    topology = dict(entry.get("topology", {}))
    if not topology:
        return topology
    topology["per_kind_max"] = dict(topology.get("per_kind_max", {}))
    live = {
        f.key: f
        for f in model.evidence_facts
        if f.authority == "LIVE_STRUCTURED_API" and f.state is CapabilityFactState.SUPPORTED
    }
    trace: list[dict[str, Any]] = []
    invalid = False
    declarations = topology.get("constraint_evidence", {})
    unresolved = {k for k, v in declarations.items() if v.get("state") in {"UNKNOWN", "CONFLICT"}}
    original_state = topology.get("constraint_state")
    for key, declaration in declarations.items():
        if declaration.get("state") in {"UNKNOWN", "CONFLICT"}:
            if key == "max":
                topology["max"] = None
            elif key in {"per_kind_max", "per_kind_min"}:
                topology[key] = {}
            # Incomplete upper bounds do not revoke a positively documented
            # operation. Execution is separately bounded by the admitted domain.
            if key not in {"max", "per_kind_max"} or declaration["state"] == "CONFLICT":
                topology["constraint_state"] = declaration["state"]
            trace.append(
                {
                    "field": key,
                    "classification": declaration.get(
                        "classification", "MISSING_UPSTREAM_CONTRACT"
                    ),
                    "source": declaration.get("source"),
                    "reason": declaration.get("reason", "Unverified constraint"),
                }
            )
    kinds = set(topology.get("reference_kinds", []))
    source_transport = "source_video" in topology.get("fixed", [])
    for key in ("per_kind_max", "per_kind_min"):
        fact = live.get(key)
        if fact is None:
            continue
        value = fact.value
        if not isinstance(value, dict) or any(
            k not in {"image", "video", "audio"} or type(v) is not int or v < 0
            for k, v in value.items()
        ):
            topology["constraint_state"] = "UNKNOWN"
            invalid = True
            continue
        old = topology.get(key, {})
        topology[key] = {k: v for k, v in value.items() if k in kinds}
        if source_transport:
            topology["transport_" + key] = dict(value)
            topology[key] = (
                dict(old)
                if REQUEST_SHAPES_KEY in live or declarations.get(key, {}).get("scope") == "method"
                else {}
            )
        if REQUEST_SHAPES_KEY in live or (
            declarations.get(key, {}).get("scope") == "method"
            and declarations[key].get("state") == "SUPPORTED"
            and declarations[key].get("source", "").startswith("https://openrouter.ai/")
        ):
            topology[key] = {
                k: min(v, old[k])
                if key == "per_kind_max" and k in old
                else max(v, old[k])
                if key == "per_kind_min" and k in old
                else v
                for k, v in topology[key].items()
            }
        unresolved.discard(key)
        if (
            key == "per_kind_max"
            and REQUEST_SHAPES_KEY not in live
            and declarations.get("max", {}).get("scope") != "method"
            and topology.get("max") is not None
            and declarations.get("max", {}).get("state") != "SUPPORTED"
        ):
            trace.append(
                {
                    "field": "max",
                    "classification": "STALE_EVIDENCE",
                    "previous": topology["max"],
                    "effective": None,
                    "source": fact.source_reference,
                    "reason": "Historical total cannot suppress confirmed per-kind capacity",
                }
            )
            topology["max"] = None
        if method == "IR2V" and key == "per_kind_max" and "image" in topology[key]:
            topology[key]["image"] = min(1, topology[key]["image"])
        trace.append(
            {
                "field": key,
                "classification": "AUTOMATICALLY_RECONCILED",
                "previous": old,
                "effective": topology[key],
                "source": fact.source_reference,
            }
        )
    cap = live.get("max_reference_count")
    minimum = live.get("min_reference_count")
    if minimum is not None:
        if type(minimum.value) is not int or minimum.value < 0:
            invalid = True
            topology["constraint_state"] = "UNKNOWN"
        elif source_transport:
            topology["transport_min"] = minimum.value
        else:
            topology["min"] = max(topology.get("min", 0), minimum.value)
    valid_cap = cap is not None and type(cap.value) is int and cap.value >= 0
    if cap is not None and not valid_cap:
        invalid = True
        topology["constraint_state"] = "UNKNOWN"
    if valid_cap and source_transport and cap is not None:
        topology["transport_max"] = cap.value
    if valid_cap and kinds and not source_transport and cap is not None and type(cap.value) is int:
        maximum = min(1, cap.value) if method == "IR2V" else cap.value
        old = topology.get("max")
        scoped = declarations.get("max", {}).get("scope") == "method" and declarations.get(
            "max", {}
        ).get("source", "").startswith("https://openrouter.ai/")
        topology["max"] = (
            min(old, maximum)
            if old is not None and (REQUEST_SHAPES_KEY in live or scoped)
            else maximum
        )
        if (
            declarations.get("max", {}).get("scope") != "method"
            or declarations.get("max", {}).get("classification") == "STALE_EVIDENCE"
        ):
            unresolved.discard("max")
        trace.append(
            {
                "field": "max",
                "classification": "CONFIRMED_OPENROUTER_RESTRICTION",
                "previous": old,
                "effective": topology["max"],
                "source": cap.source_reference,
            }
        )
    for key, target in (
        ("required_reference_kinds", "required_kinds"),
        ("mutually_exclusive_reference_kinds", "mutually_exclusive"),
    ):
        if key in live:
            value = live[key].value
            valid = isinstance(value, list) and (
                all(isinstance(k, str) and k in {"image", "video", "audio"} for k in value)
                if target == "required_kinds"
                else all(
                    isinstance(group, list)
                    and all(isinstance(k, str) for k in group)
                    and len(set(group)) >= 2
                    and set(group) <= {"image", "video", "audio"}
                    for group in value
                )
            )
            if valid:
                topology["transport_" + target if source_transport else target] = value
                unresolved.discard(target)
            else:
                topology["constraint_state"] = "UNKNOWN"
                invalid = True
    if (
        "max" in unresolved
        and declarations["max"].get("classification") == "STALE_EVIDENCE"
        and "per_kind_max" in live
        and kinds <= set(topology["per_kind_max"])
        and (
            len(kinds) == 1
            or "mixed_reference_kinds" in live
            and live["mixed_reference_kinds"].value is True
        )
    ):
        unresolved.discard("max")
    if (
        not invalid
        and not unresolved
        and original_state is None
        and kinds
        and (valid_cap or kinds <= set(topology["per_kind_max"]))
        and declarations
        and topology.get("constraint_state") == "UNKNOWN"
    ):
        topology["constraint_state"] = "SUPPORTED"
    bounded = (
        topology.get("max") is not None
        or topology.get("transport_max") is not None
        or kinds
        <= (set(topology["per_kind_max"]) | set(topology.get("transport_per_kind_max", {})))
    )
    topology["execution_domain"] = (
        "CONFIRMED_BOUNDS"
        if bounded
        else "VERIFIED_CONFIGURATIONS"
        if topology.get("verified_configurations")
        else "UNVERIFIED"
    )
    topology["limit_completeness"] = (
        "COMPLETE"
        if bounded and not unresolved
        else "PARTIAL"
        if bounded or topology.get("verified_configurations")
        else "UNKNOWN"
    )
    if trace:
        topology["reconciliation"] = trace
    if any(
        topology.get("per_kind_min", {}).get(k, 0) > v for k, v in topology["per_kind_max"].items()
    ) or any(topology["per_kind_max"].get(k) == 0 for k in topology.get("required_kinds", [])):
        topology["constraint_state"] = "CONFLICT"
    return topology


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
    live_recipe = any(
        f.key == REQUEST_SHAPES_KEY
        and f.authority == "LIVE_STRUCTURED_API"
        and f.state is CapabilityFactState.SUPPORTED
        for f in model.evidence_facts
    )
    if (
        state == "UNKNOWN"
        and method == "T2V"
        and (model.supports_text_only is False or model.source_required is True)
    ):
        state = "UNSUPPORTED"
    topology = effective_input_constraints(model, method, entry)
    if topology.get("constraint_state") in {"UNKNOWN", "CONFLICT"}:
        state = topology["constraint_state"]
    if state == "SUPPORTED" and topology.get("min") == topology.get("max") == 0:
        topology["kind_sets"] = [[]]
    if state == "SUPPORTED":
        frames = model.supported_frame_types
        for role in topology["fixed"]:
            if role in {"first_frame", "last_frame"}:
                if frames is None and not live_recipe:
                    state = "UNKNOWN"
                elif frames is not None and role not in {frame.value for frame in frames}:
                    state = "CONFLICT"
        refs = model.input_reference_capabilities
        if topology.get("reference_kinds"):
            if (refs is None or refs.reference_kinds is None) and not live_recipe:
                state = "UNKNOWN"
            elif refs is not None and refs.conflicts and not live_recipe:
                state = "CONFLICT"
            elif refs is not None and refs.reference_kinds is not None:
                kinds = {kind.value for kind in refs.reference_kinds}
                topology["reference_kinds"] = [
                    kind for kind in topology["reference_kinds"] if kind in kinds
                ]
                topology["kind_sets"] = [s for s in topology["kind_sets"] if set(s) <= kinds]
                topology["kind_sets"] = [
                    s
                    for s in topology["kind_sets"]
                    if (topology["max"] is None or len(s) <= topology["max"])
                    and (len(s) < 2 or refs.mixed_reference_kinds is not False)
                ]
                if not topology["kind_sets"] or (
                    topology["max"] is not None and topology["max"] < topology["min"]
                ):
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
                # Exact documented values remain usable on absence, never over
                # a conflict, explicit withdrawal or malformed current value.
                facts = [f for f in model.evidence_facts if f.key == field]
                if any(f.state is CapabilityFactState.CONFLICT for f in facts):
                    control["state"] = "CONFLICT"
                elif any(f.state is CapabilityFactState.UNSUPPORTED for f in facts):
                    control["state"] = "UNSUPPORTED"
                elif any(
                    f.authority == "LIVE_STRUCTURED_API" and f.value is not None for f in facts
                ) or not control.get("values"):
                    control["state"] = "UNKNOWN"
            else:
                values = [
                    v
                    for v in domain
                    if control.get("domain_completeness") == "PARTIAL"
                    or "values" not in control
                    or v in control["values"]
                ]
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
        "method_support": entry["state"],
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
        result[role] = values.get(role) if profile["topology"].get("reference_kinds") else None
    return result


def apply_transport_input_constraints(
    topology: Mapping[str, Any], source_present: bool
) -> dict[str, Any]:
    """Transport counts include the actual source, independently of optional references."""
    result = dict(topology)
    result["per_kind_max"] = dict(topology.get("per_kind_max", {}))
    result["per_kind_min"] = dict(topology.get("per_kind_min", {}))
    if topology.get("transport_min") is not None:
        result["min"] = max(
            result.get("min", 0), max(0, topology["transport_min"] - int(source_present))
        )
    cap = topology.get("transport_max")
    if cap is not None:
        remaining = cap - int(source_present)
        if remaining < 0:
            result["constraint_state"] = "CONFLICT"
        result["max"] = (
            min(result["max"], remaining) if result.get("max") is not None else remaining
        )
    for kind, maximum in topology.get("transport_per_kind_max", {}).items():
        remaining = maximum - int(source_present and kind == "video")
        if remaining < 0:
            result["constraint_state"] = "CONFLICT"
        if kind in topology.get("reference_kinds", []):
            old = result["per_kind_max"].get(kind)
            result["per_kind_max"][kind] = min(old, remaining) if old is not None else remaining
    for kind, minimum in topology.get("transport_per_kind_min", {}).items():
        remaining = max(0, minimum - int(source_present and kind == "video"))
        result["per_kind_min"][kind] = max(result["per_kind_min"].get(kind, 0), remaining)
    result["required_kinds"] = sorted(
        set(topology.get("required_kinds", []))
        | (
            set(topology.get("transport_required_kinds", []))
            - ({"video"} if source_present else set())
        )
    )
    result["mutually_exclusive"] = list(topology.get("mutually_exclusive", []))
    for group in topology.get("transport_mutually_exclusive", []):
        if source_present and "video" in group:
            for kind in group:
                if kind != "video":
                    result["per_kind_max"][kind] = 0
        else:
            result["mutually_exclusive"].append(group)
    return result


def projected_shape_valid(
    profile: Mapping[str, Any], kinds: tuple[str, ...], source_present: bool = False
) -> bool:
    """Validate complete ordered shape, without deriving a Cartesian modality set."""
    topology = apply_transport_input_constraints(profile["topology"], source_present)
    if topology.get("constraint_state", "SUPPORTED") != "SUPPORTED":
        return False
    if topology.get("execution_domain") == "UNVERIFIED" and kinds:
        return False
    if topology.get("execution_domain") == "VERIFIED_CONFIGURATIONS" and not any(
        {k: kinds.count(k) for k in set(kinds)} == counts
        for counts in topology.get("verified_configurations", [])
    ):
        return False
    if len(kinds) < topology["min"] or (
        topology["max"] is not None and len(kinds) > topology["max"]
    ):
        return False
    if set(kinds) not in [set(s) for s in topology["kind_sets"]]:
        return False
    return (
        all(kinds.count(k) <= v for k, v in topology["per_kind_max"].items())
        and all(kinds.count(k) >= v for k, v in topology.get("per_kind_min", {}).items())
        and set(topology.get("required_kinds", [])) <= set(kinds)
        and not any(
            len(set(group) & set(kinds)) > 1 for group in topology.get("mutually_exclusive", [])
        )
    )


def input_constraint_reconciliation(
    model: ModelCapabilities, method: str, profile: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Machine-check current structured evidence against the actual projected bounds."""
    topology = profile.get("topology", {})
    result = list(topology.get("reconciliation", []))
    direct = {
        f.key: f
        for f in model.evidence_facts
        if f.authority == "LIVE_STRUCTURED_API" and f.state is CapabilityFactState.SUPPORTED
    }
    registered = request_shape_profile(model).get("methods", {}).get(method, {})
    if registered.get("state") == "SUPPORTED":
        excluded = profile.get("state") != "SUPPORTED"
        actual_removal = profile.get("state") in {"UNSUPPORTED", "CONFLICT"}
        result.append(
            {
                "field": "method_support",
                "classification": "CONFIRMED_OPENROUTER_RESTRICTION"
                if actual_removal
                else "CAPABILITY_UNDEREXPOSURE_DEFECT"
                if excluded
                else "AUTOMATICALLY_RECONCILED",
                "source": registered.get("review_sources", []),
                "reason": "Registered positive operation evidence compared with projection; "
                "method support is independent of complete parameter limits",
                "method_support": registered["state"],
                "execution_domain": topology.get("execution_domain"),
                "limit_completeness": topology.get("limit_completeness"),
            }
        )
        if topology.get("execution_domain") in {"UNVERIFIED", "VERIFIED_CONFIGURATIONS"}:
            result.append(
                {
                    "field": "verified_configurations",
                    "classification": "MISSING_UPSTREAM_CONTRACT",
                    "source": registered.get("review_sources", []),
                    "reason": "Operation documented; only explicitly admitted configurations "
                    "may execute while full cardinality domain is unresolved",
                    "verified_configurations": topology.get("verified_configurations", []),
                }
            )
    recipe = direct.get(REQUEST_SHAPES_KEY)
    expected_topology = (
        recipe.value.get("methods", {}).get(method, {}).get("topology", {})
        if recipe and isinstance(recipe.value, dict)
        else {}
    )
    if expected_topology:
        expected_max, actual_max = expected_topology.get("max"), topology.get("max")
        smaller = actual_max is not None and (expected_max is None or actual_max < expected_max)
        if smaller and "max_reference_count" not in direct:
            result.append(
                {
                    "field": "max",
                    "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT",
                    "expected": expected_max,
                    "effective": actual_max,
                    "reason": "Effective total restricts the current contract without proven cap",
                }
            )
        if {tuple(sorted(s)) for s in expected_topology.get("kind_sets", [])} - {
            tuple(sorted(s)) for s in topology.get("kind_sets", [])
        }:
            result.append(
                {
                    "field": "kind_sets",
                    "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT",
                    "reason": "Confirmed combinations disappeared from projection",
                }
            )
        if (
            profile.get("state") == "UNKNOWN"
            and topology.get("constraint_state", "SUPPORTED") == "SUPPORTED"
            and all(
                v.get("state") == "SUPPORTED"
                for v in profile.get("controls", {}).values()
                if v.get("required", False)
            )
        ):
            result.append(
                {
                    "field": "state",
                    "classification": "IMPLEMENTATION_GAP",
                    "reason": "Recipe unavailable: inspect non-topology contract gaps",
                }
            )
    maxima = direct.get("per_kind_max")
    proven_method_cap = bool(expected_topology and expected_topology.get("max") is not None) or (
        topology.get("constraint_evidence", {}).get("max", {}).get("state") == "SUPPORTED"
    )
    if (
        maxima is not None
        and isinstance(maxima.value, dict)
        and "max_reference_count" not in direct
        and not proven_method_cap
    ):
        potential = max(
            (
                sum(maxima.value.get(k, 0) for k in group)
                for group in topology.get("kind_sets", [])
                if all(type(maxima.value.get(k)) is int for k in group)
            ),
            default=0,
        )
        actual = topology.get("max")
        if method != "IR2V" and actual is not None and actual < potential:
            result.append(
                {
                    "field": "max",
                    "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT",
                    "expected": None,
                    "effective": actual,
                    "reason": "Unproven total ceiling truncates confirmed per-kind capacities",
                }
            )
    for fact in model.evidence_facts:
        if "STALE_EVIDENCE" in fact.scope:
            result.append(
                {
                    "field": fact.key,
                    "classification": "STALE_EVIDENCE",
                    "source": fact.source_reference,
                    "reason": fact.scope,
                }
            )
        if (
            fact.authority != "LIVE_STRUCTURED_API"
            or fact.state is not CapabilityFactState.SUPPORTED
        ):
            continue
        if fact.key == "per_kind_max" and isinstance(fact.value, dict):
            for kind, expected in fact.value.items():
                if kind not in topology.get("reference_kinds", []) or method == "IR2V":
                    continue
                actual = topology.get("per_kind_max", {}).get(kind)
                scoped = topology.get("constraint_evidence", {}).get("per_kind_max", {})
                proven = expected_topology.get("per_kind_max", {}).get(kind) is not None or (
                    scoped.get("state") == "SUPPORTED" and scoped.get("scope") == "method"
                )
                defect = (
                    not proven and type(expected) is int and (actual is None or actual < expected)
                )
                result.append(
                    {
                        "field": "per_kind_max." + kind,
                        "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT"
                        if defect
                        else "CONFIRMED_OPENROUTER_RESTRICTION"
                        if proven and actual is not None and actual < expected
                        else "AUTOMATICALLY_RECONCILED",
                        "expected": expected,
                        "effective": actual,
                        "source": fact.source_reference,
                        "reason": "Current per-kind capacity versus effective UI profile",
                    }
                )
    if topology.get("reference_kinds") and not topology.get("reconciliation"):
        result.append(
            {
                "field": "max",
                "classification": "MISSING_UPSTREAM_CONTRACT",
                "effective": topology.get("max"),
                "reason": "Historical bound lacks current structured method-limit confirmation",
            }
        )
    return result


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
