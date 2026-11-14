"""Bounded tariff grammar and Decimal quantities for the existing cost estimator."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from enum import Enum
from functools import lru_cache
from importlib.resources import files
from itertools import combinations
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openrouter_video.pricing_planning import PlanningPolicy

from openrouter_video.models import InferenceMethod, PricingEvidence


class PricingUnit(str, Enum):
    OUTPUT_SECOND = "OUTPUT_SECOND"
    OUTPUT_TOKEN = "OUTPUT_TOKEN"  # noqa: S105 - billing unit
    IMAGE_INPUT = "IMAGE_INPUT"
    REFERENCE_SECOND = "REFERENCE_SECOND"
    MINIMUM = "MINIMUM"
    MEGAPIXEL_SECOND = "MEGAPIXEL_SECOND"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PricingDimension:
    key: str
    rate_usd: Decimal
    unit: PricingUnit


def decimal_value(value: object) -> Decimal:
    """Accept bounded exact decimals, never binary floats or booleans."""
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("nondecimal_quantity")
    if isinstance(value, str) and (not value or len(value) > 128 or value != value.strip()):
        raise ValueError("invalid_decimal")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid_decimal") from None
    if not result.is_finite() or result < 0 or result.adjusted() > 30:
        raise ValueError("nonfinite_negative_or_unbounded_decimal")
    if len(result.as_tuple().digits) > 60 or int(result.as_tuple().exponent) < -30:
        raise ValueError("unbounded_decimal_precision")
    return result


def normalize_rate(rate: object, unit: str) -> Decimal:
    scales = {"USD": Decimal(1), "cents": Decimal(100), "USD_per_million": Decimal(1000000)}
    if unit not in scales:
        raise ValueError("unknown_rate_unit")
    with localcontext() as context:
        context.prec = 80
        return decimal_value(rate) / scales[unit]


_SCALAR_QUANTITIES = frozenset(
    {
        "output_seconds",
        "source_seconds",
        "effective_output_seconds",
        "input_seconds",
        "active_image_inputs",
        "reference_images",
        "output_count",
        "tokens",
        "billable_seconds",
        "billable_mp_seconds",
    }
)
_QUANTITIES = _SCALAR_QUANTITIES | {
    "unknown",
    "fixed",
    "video_tokens_output_24",
    "video_tokens_input_output",
    "megapixel_seconds",
    "megapixel_seconds_binary_output_24",
}
_COUNTS = {"active_image_inputs", "reference_images", "output_count"}


def calculate_quantity(kind: str, values: Mapping[str, object]) -> Decimal:
    """Evaluate one declared quantity. Missing metadata is never zero."""

    def number(key: str, *, positive: bool = True, integer: bool = False) -> Decimal:
        value = decimal_value(values.get(key))
        if (positive and value <= 0) or (integer and value != value.to_integral_value()):
            raise ValueError("invalid_quantity_domain")
        return value

    with localcontext() as context:
        context.prec = 80
        if kind == "fixed":
            return Decimal(1)
        if kind in _SCALAR_QUANTITIES:
            return number(kind, positive=kind not in _COUNTS, integer=kind in _COUNTS)
        if kind in {
            "video_tokens_output_24",
            "video_tokens_input_output",
            "megapixel_seconds",
            "megapixel_seconds_binary_output_24",
        }:
            pixels = number("width", integer=True) * number("height", integer=True)
            duration = number("output_seconds")
            if kind == "video_tokens_output_24":
                return pixels * 24 * duration / 1024
            if kind == "video_tokens_input_output":
                return pixels * number("fps") * (number("input_seconds") + duration) / 1024
            divisor = 1048576 if kind == "megapixel_seconds_binary_output_24" else 1000000
            return pixels * duration / divisor
    raise ValueError("unproven_quantity")


@dataclass(frozen=True, slots=True)
class ChargeBreakdown:
    sku: str
    unit: str
    quantity: Decimal | None
    rate_usd: Decimal
    amount_usd: Decimal | None
    relation: str = "base"
    evidence: str | None = None
    applicability: str = "APPLICABLE"


@dataclass(frozen=True, slots=True)
class ChargePlanResult:
    state: str
    amount_usd: Decimal | None = None
    breakdown: tuple[ChargeBreakdown, ...] = ()
    reason: str | None = None
    lower_usd: Decimal | None = None
    upper_usd: Decimal | None = None


def evaluate_charge_plan(
    charges: Sequence[Mapping[str, object]],
    values: Mapping[str, object],
    *,
    rates: Mapping[str, object] | None = None,
    stale: bool = False,
    invalid: bool = False,
    conflict: bool = False,
    unknown_charge: bool = False,
) -> ChargePlanResult:
    """One exclusive base, additions, then floors; literal rates support offline conformance.

    Production profiles separately forbid literal rates. Missing quantities or unknown
    charges suppress the total; known rows remain explicitly partial components.
    """
    if invalid:
        return ChargePlanResult("INVALID", reason="invalid_configuration")
    if stale:
        return ChargePlanResult("STALE", reason="pricing_evidence_stale")
    if conflict:
        return ChargePlanResult("UNKNOWN", reason="exclusive_rule_conflict")
    if unknown_charge:
        return ChargePlanResult("PARTIAL", reason="unknown_relevant_charge")
    if not charges or len(charges) > 64:
        return ChargePlanResult("UNKNOWN", reason="empty_or_unbounded_charge_plan")
    rows: list[ChargeBreakdown] = []
    subtotal = Decimal(0)
    floors: list[Decimal] = []
    missing = False
    base_count = 0
    try:
        with localcontext() as context:
            context.prec = 80
            for index, charge in enumerate(charges):
                sku = str(charge.get("sku", f"charge_{index}"))
                unit = str(charge["unit"])
                relation = str(charge.get("relation", "base" if index == 0 else "add"))
                if relation not in {"base", "add", "minimum"}:
                    raise ValueError("invalid_charge_relation")
                base_count += relation == "base"
                raw_rate = charge.get("rate") if rates is None else rates.get(sku)
                rate = normalize_rate(raw_rate, unit)
                quantity: Decimal | None
                amount: Decimal | None
                try:
                    quantity = calculate_quantity(str(charge["quantity"]), values)
                except ValueError:
                    quantity, amount, missing = None, None, True
                else:
                    free = decimal_value(charge.get("free_allowance", charge.get("free", 0)))
                    quantity = max(Decimal(0), quantity - free)
                    if "minimum_quantity" in charge:
                        quantity = max(quantity, decimal_value(charge["minimum_quantity"]))
                    if "rounding_quantum" in charge:
                        quantum = decimal_value(charge["rounding_quantum"])
                        if quantum <= 0:
                            raise ValueError("invalid_rounding_quantum")
                        quantity = (quantity / quantum).to_integral_value(
                            rounding=ROUND_CEILING
                        ) * quantum
                    tiers = charge.get("tiers")
                    amount = (
                        rate * quantity if tiers is None else _tier_amount(tiers, quantity, unit)
                    )
                    if relation == "minimum":
                        floors.append(amount)
                    else:
                        subtotal += amount
                rows.append(ChargeBreakdown(sku, unit, quantity, rate, amount, relation))
            if base_count != 1:
                raise ValueError("exclusive_base_conflict")
            if missing:
                known = any(row.amount_usd is not None for row in rows)
                return ChargePlanResult(
                    "PARTIAL" if known else "UNKNOWN",
                    breakdown=tuple(rows),
                    reason="billing_quantity_unavailable",
                )
            return ChargePlanResult("FORMULA", max([subtotal, *floors]), tuple(rows))
    except (ValueError, KeyError, InvalidOperation, TypeError):
        return ChargePlanResult("UNKNOWN", reason="invalid_charge_plan")


def _tier_amount(tiers: object, quantity: Decimal, unit: str) -> Decimal:
    if not isinstance(tiers, list) or not tiers or len(tiers) > 32:
        raise ValueError("invalid_tiers")
    last, amount = Decimal(0), Decimal(0)
    open_ended = False
    for tier in tiers:
        if not isinstance(tier, dict) or set(tier) != {"through", "rate"} or open_ended:
            raise ValueError("invalid_tier")
        through = tier["through"]
        end = quantity if through is None else decimal_value(through)
        if through is not None and end <= last:
            raise ValueError("invalid_tier_order")
        amount += max(Decimal(0), min(quantity, end) - last) * normalize_rate(tier["rate"], unit)
        last, open_ended = end, through is None
    if not open_ended and quantity > last:
        raise ValueError("incomplete_tiers")
    return amount


def calculate_range(alternatives: Sequence[ChargePlanResult]) -> ChargePlanResult:
    """Every explicitly documented alternative must have a complete cost."""
    if (
        not alternatives
        or len(alternatives) > 64
        or any(result.state != "FORMULA" or result.amount_usd is None for result in alternatives)
    ):
        return ChargePlanResult("UNKNOWN", reason="incomplete_range_alternatives")
    amounts = [result.amount_usd for result in alternatives if result.amount_usd is not None]
    return ChargePlanResult("RANGE", lower_usd=min(amounts), upper_usd=max(amounts))


@dataclass(frozen=True, slots=True)
class TariffCase:
    id: str
    when: tuple[tuple[str, tuple[object, ...]], ...]
    expected_state: str
    charges: tuple[Mapping[str, object], ...]
    reason: str | None
    evidence: str
    active: bool
    require_equal_skus: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TariffProfile:
    model_id: str
    canonical_slug: str
    known_skus: tuple[str, ...]
    rules: tuple[TariffCase, ...]
    geometry_map: Mapping[str, Mapping[str, str]]
    geometry_status: str
    default_reason: str
    source: str
    audio_default: bool | None = None
    metadata_policy: str = "NONE"
    neutral_controls: tuple[NeutralControlPolicy, ...] = ()
    normalized_geometry_map: Mapping[str, Mapping[str, str]] | None = None
    planning_policy: PlanningPolicy | None = None


@dataclass(frozen=True, slots=True)
class NeutralControlPolicy:
    provider: str
    key: str
    type: str
    methods: tuple[str, ...]
    evidence: str


_STATES = {"FORMULA", "RANGE", "RATE_ONLY", "PARTIAL", "STALE", "UNKNOWN", "INVALID"}
_PREDICATES = {
    "method",
    "resolution",
    "generated_audio",
    "has_video",
    "has_references",
    "upscale_mode",
    "duration",
}


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("invalid_profile_text")
    return value


def _string_list(value: object, *, empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 256 or (not value and not empty):
        raise ValueError("invalid_profile_list")
    result = tuple(_text(item) for item in value)
    if len(result) != len(set(result)):
        raise ValueError("duplicate_profile_item")
    return result


def _predicate_valid(key: str, item: object, methods: tuple[str, ...]) -> bool:
    if key == "method":
        return isinstance(item, str) and item in methods
    if key in {"has_video", "has_references"}:
        return type(item) is bool
    if key == "generated_audio":
        return item is None or type(item) is bool
    if key == "duration":
        return item is None or (type(item) is int and (item == -1 or 0 < item <= 1000000))
    return item is None or isinstance(item, str)


def compile_profile(raw: Mapping[str, object]) -> TariffProfile:
    """Reject unknown grammar, ambiguous exclusive cases and unbounded data."""
    required = {
        "model_id",
        "canonical_slug",
        "capture_methods",
        "known_skus",
        "rules",
        "sku_accounting",
        "gaps",
        "source",
        "activation",
        "default",
        "geometry_map",
        "geometry_status",
    }
    if not required <= set(raw) or set(raw) - required - {
        "audio_default",
        "metadata_policy",
        "neutral_controls",
        "normalized_geometry_map",
        "planning_policy",
    }:
        raise ValueError("invalid_profile_fields")
    audio_default = raw.get("audio_default")
    if audio_default is not None and type(audio_default) is not bool:
        raise ValueError("invalid_audio_default")
    metadata_policy = raw.get("metadata_policy", "NONE")
    if metadata_policy not in {"NONE", "SOURCE_DURATION", "UPSCALE_SOURCE_24"}:
        raise ValueError("invalid_metadata_policy")
    if raw["activation"] not in {
        "CANDIDATE_REQUIRES_FRESH_CAPTURE_AND_EVIDENCE_REVIEW",
        "EVIDENCE_REVIEWED",
    }:
        raise ValueError("invalid_profile_activation")
    model_id, canonical = _text(raw["model_id"]), _text(raw["canonical_slug"])
    known = _string_list(raw["known_skus"])
    methods = _string_list(raw["capture_methods"])
    if not set(methods) <= {method.value for method in InferenceMethod}:
        raise ValueError("invalid_profile_method")
    neutral_raw = raw.get("neutral_controls", [])
    if not isinstance(neutral_raw, list) or len(neutral_raw) > 8:
        raise ValueError("invalid_neutral_control_policy")
    neutral: list[NeutralControlPolicy] = []
    for control in neutral_raw:
        if not isinstance(control, dict) or set(control) != {
            "provider",
            "key",
            "type",
            "methods",
            "evidence",
        }:
            raise ValueError("invalid_neutral_control_fields")
        provider, key = _text(control["provider"]), _text(control["key"])
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", provider) or not re.fullmatch(
            r"[a-z][a-z0-9_]{0,63}", key
        ):
            raise ValueError("invalid_neutral_control_identifier")
        if control["type"] not in {"number", "string"}:
            raise ValueError("invalid_neutral_control_type")
        scoped_methods = _string_list(control["methods"])
        if not set(scoped_methods) <= set(methods):
            raise ValueError("invalid_neutral_control_scope")
        neutral.append(
            NeutralControlPolicy(
                provider, key, control["type"], scoped_methods, _text(control["evidence"])
            )
        )
    if len({(entry.provider, entry.key) for entry in neutral}) != len(neutral):
        raise ValueError("duplicate_neutral_control_policy")
    rules_raw = raw["rules"]
    if not isinstance(rules_raw, list) or not rules_raw or len(rules_raw) > 256:
        raise ValueError("invalid_profile_rules")
    rules: list[TariffCase] = []
    for case in rules_raw:
        if not isinstance(case, dict):
            raise ValueError("invalid_rule")
        fields = {"id", "when", "expected_state", "charges", "reason", "evidence"}
        optional = {"activation", "notes", "require_equal_skus", "production_active"}
        if not fields <= set(case) or set(case) - fields - optional:
            raise ValueError("invalid_rule_fields")
        if case.get("activation", "CANDIDATE") not in {
            "CANDIDATE",
            "RECHECK_1080P_SCOPE",
            "RECHECK_ALEPH_DURATION_AND_FORMAT",
            "RECHECK_DURATION_MAPPING",
            "RECHECK_EFFECTIVE_AUDIO_AND_TIER",
            "RECHECK_FIXED_FRAME_FEE",
            "RECHECK_OUTPUT_GEOMETRY_AND_ROUTE",
        }:
            raise ValueError("invalid_rule_activation")
        when = case["when"]
        if not isinstance(when, dict) or "method" not in when or set(when) - _PREDICATES:
            raise ValueError("invalid_rule_predicate")
        predicates: list[tuple[str, tuple[object, ...]]] = []
        for key, options in when.items():
            if not isinstance(options, list) or not options or len(options) > 256:
                raise ValueError("invalid_predicate_domain")
            if any(not _predicate_valid(key, item, methods) for item in options):
                raise ValueError("invalid_predicate_value")
            if len({(type(item), item) for item in options}) != len(options):
                raise ValueError("duplicate_predicate_value")
            predicates.append((key, tuple(options)))
        state = _text(case["expected_state"])
        if state not in _STATES:
            raise ValueError("invalid_rule_state")
        charge_data = case["charges"]
        if not isinstance(charge_data, list) or len(charge_data) > 64:
            raise ValueError("invalid_rule_charges")
        if state == "FORMULA" and not charge_data:
            raise ValueError("missing_formula_charges")
        charges: list[Mapping[str, object]] = []
        for index, charge in enumerate(charge_data):
            if not isinstance(charge, dict) or not {"sku", "unit", "quantity"} <= set(charge):
                raise ValueError("invalid_rule_charge")
            if set(charge) - {"sku", "unit", "quantity", "free_allowance", "relation", "rate_unit"}:
                raise ValueError("unsupported_rule_charge_field")
            if "rate_unit" in charge and charge["rate_unit"] not in {
                "s",
                "token",
                "MP.s",
                "generation",
                "image",
            }:
                raise ValueError("invalid_rate_quantity_unit")
            if charge["sku"] not in known or charge["unit"] not in {
                "USD",
                "cents",
                "USD_per_million",
            }:
                raise ValueError("invalid_charge_sku_or_unit")
            if charge["quantity"] not in _QUANTITIES:
                raise ValueError("invalid_charge_quantity")
            if "free_allowance" in charge and (
                type(charge["free_allowance"]) is not int or charge["free_allowance"] < 0
            ):
                raise ValueError("invalid_free_allowance")
            relation = charge.get("relation", "base" if index == 0 else "add")
            if relation not in {"base", "add", "minimum"}:
                raise ValueError("invalid_charge_relation")
            charges.append(MappingProxyType(dict(charge)))
        if (
            charges
            and sum(
                charge.get("relation", "base" if i == 0 else "add") == "base"
                for i, charge in enumerate(charges)
            )
            != 1
        ):
            raise ValueError("exclusive_base_conflict")
        active = case.get("production_active", False)
        if type(active) is not bool:
            raise ValueError("invalid_activation")
        reason = case["reason"]
        if reason is not None:
            reason = _text(reason)
        equal = _string_list(case.get("require_equal_skus", []), empty=True)
        if not set(equal) <= set(known):
            raise ValueError("unknown_alias_sku")
        rules.append(
            TariffCase(
                _text(case["id"]),
                tuple(predicates),
                state,
                tuple(charges),
                reason,
                _text(case["evidence"]),
                active,
                equal,
            )
        )
    if len({rule.id for rule in rules}) != len(rules):
        raise ValueError("duplicate_rule_id")
    for left, right in combinations(rules, 2):
        lpred, rpred = dict(left.when), dict(right.when)
        if not any(not set(lpred[key]) & set(rpred[key]) for key in set(lpred) & set(rpred)):
            raise ValueError("overlapping_exclusive_rules")
    geometry = raw["geometry_map"]
    if not isinstance(geometry, dict) or len(geometry) > 64:
        raise ValueError("invalid_geometry_map")
    for mapping in geometry.values():
        if not isinstance(mapping, dict) or len(mapping) > 64:
            raise ValueError("invalid_geometry_map")
        for size in mapping.values():
            if (
                not isinstance(size, str)
                or len(size.split("x")) != 2
                or not all(part.isdigit() and 0 < int(part) <= 100000 for part in size.split("x"))
            ):
                raise ValueError("invalid_geometry_size")
    normalized = raw.get("normalized_geometry_map")
    if normalized is not None:
        if not isinstance(normalized, dict) or not set(normalized) <= set(geometry):
            raise ValueError("invalid_normalized_geometry_map")
        for mapping in normalized.values():
            if not isinstance(mapping, dict) or len(mapping) > 64:
                raise ValueError("invalid_normalized_geometry_map")
            for ratio, size in mapping.items():
                if (
                    not isinstance(ratio, str)
                    or not isinstance(size, str)
                    or not re.fullmatch(r"[1-9][0-9]{0,4}x[1-9][0-9]{0,4}", size)
                ):
                    raise ValueError("invalid_normalized_geometry_size")
    default = raw["default"]
    if (
        not isinstance(default, dict)
        or set(default) != {"state", "reason"}
        or default["state"] not in _STATES
    ):
        raise ValueError("invalid_profile_default")
    for key in ("sku_accounting", "gaps"):
        metadata_rows = raw[key]
        if not isinstance(metadata_rows, list) or len(metadata_rows) > 256:
            raise ValueError("invalid_profile_accounting")
    accounting = raw["sku_accounting"]
    assert isinstance(accounting, list)  # noqa: S101 - narrowed validated schema
    accounted: set[str] = set()
    for row in accounting:
        if not isinstance(row, dict) or set(row) != {"sku", "disposition", "rule_ids"}:
            raise ValueError("invalid_sku_accounting")
        sku = _text(row["sku"])
        if (
            sku not in known
            or sku in accounted
            or row["disposition"]
            not in {
                "ALIAS_REQUIRE_EQUAL",
                "GENERIC_NOT_FALLBACK",
                "INACTIVE_METHOD",
                "RULE_REFERENCE",
                "UNRESOLVED_NOT_USED",
                "UNRESOLVED_TIER",
            }
        ):
            raise ValueError("invalid_sku_disposition")
        references = _string_list(row["rule_ids"], empty=True)
        if not set(references) <= {rule.id for rule in rules}:
            raise ValueError("unknown_accounted_rule")
        accounted.add(sku)
    if accounted != set(known):
        raise ValueError("unaccounted_sku")
    gaps = raw["gaps"]
    assert isinstance(gaps, list)  # noqa: S101 - narrowed validated schema
    for gap in gaps:
        if not isinstance(gap, dict) or set(gap) != {"code", "description"}:
            raise ValueError("invalid_gap")
        _text(gap["code"])
        _text(gap["description"])
    from openrouter_video.pricing_planning import compile_planning_policy

    planning = compile_planning_policy(raw.get("planning_policy"), known)
    return TariffProfile(
        model_id,
        canonical,
        known,
        tuple(rules),
        MappingProxyType({key: MappingProxyType(dict(value)) for key, value in geometry.items()}),
        _text(raw["geometry_status"]),
        _text(default["reason"]),
        _text(raw["source"]),
        audio_default,
        str(metadata_policy),
        tuple(neutral),
        None
        if normalized is None
        else MappingProxyType(
            {key: MappingProxyType(dict(value)) for key, value in normalized.items()}
        ),
        planning,
    )


@lru_cache(maxsize=1)
def load_profiles() -> tuple[TariffProfile, ...]:
    resource = files("openrouter_video").joinpath("data/video-tariff-rules.json")
    raw: Any = json.loads(resource.read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or set(raw) != {"version", "profiles"}
        or raw["version"] != "ACI-1.0"
    ):
        raise ValueError("invalid_profile_resource")
    if not isinstance(raw["profiles"], list) or not raw["profiles"] or len(raw["profiles"]) > 256:
        raise ValueError("invalid_profile_resource")
    profiles = tuple(compile_profile(profile) for profile in raw["profiles"])
    if len({profile.model_id for profile in profiles}) != len(profiles):
        raise ValueError("duplicate_model_profile")
    return profiles


def normalize_pricing(evidence: PricingEvidence) -> tuple[PricingDimension, ...]:
    """Diagnostic vocabulary only; never infer a production charge plan from it."""
    dimensions = []
    for sku in evidence.skus:
        key = sku.key
        rate = normalize_rate(
            sku.rate_usd, "cents" if key.startswith(("cents_", "minimum_cents_")) else "USD"
        )
        if key.startswith("video_tokens"):
            unit = PricingUnit.OUTPUT_TOKEN
        elif "megapixel_second" in key:
            unit = PricingUnit.MEGAPIXEL_SECOND
        elif key.startswith("minimum_"):
            unit = PricingUnit.MINIMUM
        elif key in ("cents_per_image_input", "reference_images"):
            unit = PricingUnit.IMAGE_INPUT
        elif key.startswith(
            (
                "duration_seconds",
                "text_to_video_duration_seconds",
                "image_to_video_duration_seconds",
                "reference_duration_seconds",
                "long_reference_duration_seconds",
                "cents_per_second_output",
                "cents_per_video_output_second",
                "cents_per_second_video_continuation",
            )
        ):
            unit = PricingUnit.OUTPUT_SECOND
        else:
            unit = PricingUnit.UNKNOWN
        dimensions.append(PricingDimension(key, rate, unit))
    return tuple(dimensions)
