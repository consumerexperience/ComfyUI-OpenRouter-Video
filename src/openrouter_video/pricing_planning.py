"""Declarative planning quantities for the existing pricing engine.
No price constants, network, model ID branches or spend authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from types import MappingProxyType
from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from openrouter_video.pricing import CostEstimateInputs, MediaCostMetadata
    from openrouter_video.pricing_profile import TariffProfile

from openrouter_video.pricing_profile import decimal_value, evaluate_charge_plan

KINDS = {
    "TOKEN_GEOMETRY",
    "AUDIO_OUTPUT_COMPARISON",
    "INPUT_OUTPUT_SECONDS",
    "CAPPED_REFERENCE_ALIAS",
    "REFERENCE_INPUT_COMPARISON",
    "AUDIO_DURATION",
    "NOMINAL_UPSCALE",
}


class PlanningPolicy(TypedDict, total=False):
    kind: str
    note: str
    floor_evidence: str
    tier_skus: Mapping[str, str]
    long_tier_skus: Mapping[str, str]
    image_sku: str


class PlanningCharge(TypedDict):
    sku: str
    unit: str
    quantity_unit: str
    quantity: str | None
    rate_usd: str
    amount_usd: str | None
    relation: str


class PlanningScenario(TypedDict):
    label: str
    scope: str
    sku: str
    quantity: str
    quantity_unit: str
    amount_usd: str
    assumption: str
    charges: list[PlanningCharge]


class PlanningProjection(TypedDict):
    version: str
    display: str
    notice: str
    scenarios: list[PlanningScenario]
    missing: list[str]
    modelled_usd: str | None
    scenario_min_usd: str | None
    scenario_max_usd: str | None


def compile_planning_policy(raw: object, known: Sequence[str]) -> PlanningPolicy | None:
    if raw is None:
        return None
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("kind"), str)
        or raw.get("kind") not in KINDS
    ):
        raise ValueError("invalid_planning_policy")
    kind = raw["kind"]
    optional = {
        "TOKEN_GEOMETRY": {"floor_evidence"},
        "AUDIO_OUTPUT_COMPARISON": {"tier_skus"},
        "CAPPED_REFERENCE_ALIAS": {"tier_skus"},
        "REFERENCE_INPUT_COMPARISON": {"tier_skus", "long_tier_skus", "image_sku"},
    }.get(kind, set())
    if (
        set(raw) != {"kind", "note"} | optional
        or not isinstance(raw["note"], str)
        or not 0 < len(raw["note"]) <= 1024
    ):
        raise ValueError("invalid_planning_fields")
    out = dict(raw)
    for key in ("tier_skus", "long_tier_skus"):
        if key in raw:
            m = raw[key]
            if (
                not isinstance(m, dict)
                or not m
                or len(m) > 16
                or any(
                    k not in {"360p", "480p", "720p", "768p", "1080p", "2K", "4K"}
                    or not isinstance(v, str)
                    or v not in known
                    for k, v in m.items()
                )
            ):
                raise ValueError("invalid_planning_tier_sku")
            out[key] = MappingProxyType(dict(m))
    if "image_sku" in raw and (
        not isinstance(raw["image_sku"], str) or raw["image_sku"] not in known
    ):
        raise ValueError("invalid_planning_image_sku")
    if "floor_evidence" in raw and (
        not isinstance(raw["floor_evidence"], str)
        or raw["floor_evidence"] not in {"OBSERVED_OTHER_ROUTE", "EXTRAPOLATED_OTHER_REVISION"}
    ):
        raise ValueError("invalid_planning_evidence")
    return cast(PlanningPolicy, MappingProxyType(out))


def plan_scenarios(
    profile: TariffProfile,
    inputs: CostEstimateInputs,
    rates: Mapping[str, object],
) -> PlanningProjection:
    from openrouter_video.pricing import (
        _geometry,
        _matches,
        _profile_context,
        canonicalize_cost_metadata,
        media_inventory_status,
    )

    inputs = canonicalize_cost_metadata(inputs)
    policy = profile.planning_policy
    scenarios: list[PlanningScenario] = []
    missing: list[str] = []

    def finish() -> PlanningProjection:
        # Only total-conditional scenarios in the same semantic scope form a scenario range.
        totals = [x for x in scenarios if x["scope"] == "CONDITIONAL_TOTAL"]
        amounts = [Decimal(x["amount_usd"]) for x in totals]
        display = "DETAIL_ONLY"
        if len(totals) == len(scenarios) and totals:
            display = "SCENARIO_RANGE" if min(amounts) != max(amounts) else "MODELLED"
        return {
            "version": "ACI-PLANNING-1",
            "display": display,
            "notice": "Limited billing transparency: actual charge may differ; not a spending cap.",
            "scenarios": scenarios,
            "missing": list(dict.fromkeys(missing)),
            "modelled_usd": format(amounts[0], "f") if display == "MODELLED" else None,
            "scenario_min_usd": format(min(amounts), "f") if display == "SCENARIO_RANGE" else None,
            "scenario_max_usd": format(max(amounts), "f") if display == "SCENARIO_RANGE" else None,
        }

    if policy is None:
        return finish()
    inventory_reason = media_inventory_status(inputs)
    if inventory_reason:
        missing.append(inventory_reason)
        return finish()

    def positive(value: object) -> Decimal:
        v = decimal_value(value)
        if v <= 0:
            raise ValueError("positive_quantity_required")
        return v

    def add(
        label: str,
        scope: str,
        sku: str | None,
        q: Decimal,
        unit: str = "USD",
        extra: Sequence[Mapping[str, object]] = (),
        values: Mapping[str, object] | None = None,
        note: str = "",
    ) -> None:
        if sku is None or sku not in rates:
            return
        qkind, qunit = {
            "TOKEN_GEOMETRY": ("tokens", "token"),
            "NOMINAL_UPSCALE": ("billable_mp_seconds", "MP.s"),
        }.get(policy["kind"], ("billable_seconds", "s"))
        result = evaluate_charge_plan(
            [{"sku": sku, "unit": unit, "quantity": qkind}, *extra],
            {qkind: q, **(values or {})},
            rates=rates,
        )
        if result.state != "FORMULA" or result.amount_usd is None:
            return
        scenarios.append(
            {
                "label": label,
                "scope": scope,
                "sku": sku,
                "quantity": format(q, "f"),
                "quantity_unit": qunit,
                "amount_usd": format(result.amount_usd, "f"),
                "assumption": policy["note"] + " " + note,
                "charges": [
                    {
                        "sku": r.sku,
                        "unit": r.unit,
                        "quantity_unit": qunit if r.sku == sku else "image",
                        "quantity": format(r.quantity, "f") if r.quantity is not None else None,
                        "rate_usd": format(r.rate_usd, "f"),
                        "amount_usd": format(r.amount_usd, "f")
                        if r.amount_usd is not None
                        else None,
                        "relation": r.relation,
                    }
                    for r in result.breakdown
                ],
            }
        )

    # Exact ordered active occurrence inventory. No parked data, no source double count.
    refs = [x for x in inputs.media if x.role == "reference"]
    sources = [x for x in inputs.media if x.role == "source_video"]
    method = inputs.inference_method.value
    if (
        tuple(x.kind for x in refs) != inputs.reference_kinds
        or len(sources) != int(inputs.source_video_present)
        or any(
            x.role not in {"reference", "source_video", "first_frame", "last_frame"}
            for x in inputs.media
        )
    ):
        missing.append("active_occurrence_metadata")
        return finish()
    if sum(x.role == "first_frame" for x in inputs.media) != int(method in {"I2V", "FLF2V"}) or sum(
        x.role == "last_frame" for x in inputs.media
    ) != int(method == "FLF2V"):
        missing.append("active_frame_metadata")
        return finish()

    def duration_of(x: MediaCostMetadata) -> Decimal | None:
        return (
            positive(x.duration_seconds)
            if x.status in {"KNOWN", "HINT"} and x.duration_seconds is not None
            else None
        )

    d = Decimal(inputs.duration) if inputs.duration is not None and inputs.duration > 0 else None
    videos = [x for x in (*refs, *sources) if x.kind.value == "video"]
    video_durations = [duration_of(x) for x in videos]
    known_video_durations = [value for value in video_durations if value is not None]
    din = (
        sum(known_video_durations, Decimal(0))
        if len(known_video_durations) == len(video_durations)
        else None
    )
    src = sources[0] if sources else None
    ds = duration_of(src) if src else None
    res, _, _, _ = _geometry(profile, inputs)
    ctx = _profile_context(profile, inputs, res)
    matches = [r for r in profile.rules if _matches(r, ctx)]
    rule = matches[0] if len(matches) == 1 else None
    # Never rescue an actual predicate conflict or an alias conflict.
    if len(matches) > 1 or (
        rule
        and rule.require_equal_skus
        and (
            any(k not in rates for k in rule.require_equal_skus)
            or len({decimal_value(rates[k]) for k in rule.require_equal_skus}) != 1
        )
    ):
        missing.append("exclusive_rule_or_alias_conflict")
        return finish()
    sku = str(rule.charges[0]["sku"]) if rule and rule.charges else None
    kind = policy["kind"]
    with localcontext() as lc:
        lc.prec = 60
        if kind == "TOKEN_GEOMETRY":
            sizes = []
            if inputs.size:
                sizes = [("explicit requested geometry", inputs.size)]
            else:
                old = profile.geometry_map.get(inputs.resolution or "", {}).get(
                    inputs.aspect_ratio or ""
                )
                native = profile.normalized_geometry_map
                new = (
                    native.get(inputs.resolution or "", {}).get(inputs.aspect_ratio or "")
                    if native
                    else old
                )
                if new:
                    sizes.append(("native normalized geometry", new))
                if old and old != new:
                    sizes.append(("catalogue geometry alternative", old))
            if not sizes:
                missing.append("geometry")
            if d is None:
                missing.append("output_duration")
            if din is None:
                missing.append("all_active_video_durations")
            if sku and d is not None and din is not None:
                for label, size in sizes:
                    w, h = map(int, size.split("x"))
                    t = d
                    if videos:
                        t = max(d + din, (d * 5 / 3).to_integral_value(rounding=ROUND_CEILING))
                    scope = (
                        "COMPARISON"
                        if method in {"V2V_EDIT", "V2V_EXTEND"}
                        else "CONDITIONAL_TOTAL"
                    )
                    add(
                        label + " / continuous",
                        scope,
                        sku,
                        Decimal(w * h) * 24 * t / 1024,
                        note=(
                            f"{size}; input seconds {din}; requested output {d}; "
                            "assumes no other fees. "
                        )
                        + str(policy.get("floor_evidence", "")),
                    )
                    if videos:
                        add(
                            label + " / extra frame",
                            scope,
                            sku,
                            (Decimal(w * h) * (24 * t + 1) / 1024).to_integral_value(
                                rounding=ROUND_FLOOR
                            ),
                            note="Hypothetical extra-frame variant; not a universal rounding rule.",
                        )
        elif kind == "AUDIO_OUTPUT_COMPARISON":
            sku = policy["tier_skus"].get(res or "")
            if method == "V2V_EDIT":
                if ds is None:
                    missing.append("source_duration")
                else:
                    add("with-audio output component / source length", "COMPARISON", sku, ds)
            elif method == "V2V_EXTEND":
                if d is not None:
                    add("with-audio / if requested length is extension", "COMPARISON", sku, d)
                else:
                    missing.append("output_duration")
                if ds is not None and d is not None:
                    add(
                        "with-audio / if billed full result",
                        "COMPARISON",
                        sku,
                        min(ds, Decimal(30)) + d,
                        note="Native 30s source cap is a conditional scenario, not OR capability.",
                    )
                elif ds is None:
                    missing.append("source_duration")
            elif d is not None:
                add("with-audio output component (comparison)", "COMPARISON", sku, d)
            else:
                missing.append("output_duration")
        elif kind == "INPUT_OUTPUT_SECONDS":
            if din is None:
                missing.append("all_active_video_durations")
            if d is None:
                missing.append("output_duration")
            if d is not None and din is not None:
                add(
                    "native input + output seconds",
                    "CONDITIONAL_TOTAL"
                    if all(x.kind.value != "audio" for x in refs)
                    else "COMPARISON",
                    sku,
                    d + din,
                    note="Assumes no additional reference fees.",
                )
        elif kind == "CAPPED_REFERENCE_ALIAS":
            if tuple(x.kind.value for x in refs) == ("video",) and not sources:
                if din is None:
                    missing.append("active_video_duration")
                if d is None:
                    missing.append("output_duration")
                if din is not None and d is not None:
                    add(
                        "if reference tariff equals image-to-video rate",
                        "CONDITIONAL_TOTAL",
                        policy["tier_skus"].get(res or ""),
                        d + min(din, Decimal(5)),
                    )
            else:
                missing.append("single_video_reference_policy_not_applicable")
        elif kind == "REFERENCE_INPUT_COMPARISON":
            if din is None:
                missing.append("all_active_video_durations")
            if d is None:
                missing.append("output_duration")
            if d is not None and refs:
                sku = policy["long_tier_skus" if d > 15 else "tier_skus"].get(res or "")
                extra = [
                    {
                        "sku": policy["image_sku"],
                        "unit": "USD",
                        "quantity": "reference_images",
                        "free_allowance": 2,
                    }
                ]
                values = {"reference_images": sum(x.kind.value == "image" for x in refs)}
                add("output and image components", "COMPONENT", sku, d, extra=extra, values=values)
                if din is not None:
                    add(
                        "if same rate applies to input seconds",
                        "COMPARISON",
                        sku,
                        d + din,
                        extra=extra,
                        values=values,
                    )
        elif kind == "AUDIO_DURATION":
            audio = [x for x in refs if x.kind.value == "audio"]
            audio_duration = duration_of(audio[0]) if len(audio) == 1 else None
            if method == "AVATAR_AUDIO" and audio_duration is not None:
                add(
                    "if delivered duration equals audio",
                    "CONDITIONAL_TOTAL",
                    sku,
                    audio_duration,
                )
            else:
                missing.append("audio_duration_or_explicit_planning_duration")
        elif kind == "NOMINAL_UPSCALE":
            if (
                src
                and ds is not None
                and src.width
                and src.height
                and inputs.upscale_factor
                and ctx["upscale_mode"]
            ):
                output_width = Decimal(src.width) * positive(inputs.upscale_factor)
                output_height = Decimal(src.height) * positive(inputs.upscale_factor)
                if (
                    output_width == output_width.to_integral_value()
                    and output_height == output_height.to_integral_value()
                    and output_width * output_height <= Decimal(14000000)
                ):
                    add(
                        "nominal integer output geometry",
                        "CONDITIONAL_TOTAL",
                        sku,
                        output_width * output_height * ds / 1048576,
                        "cents",
                        note=(
                            f"{int(output_width)}x{int(output_height)}; "
                            "nominal guard only, not capability."
                        ),
                    )
                else:
                    missing.append("delivered_output_geometry")
            else:
                missing.append("source_geometry_duration_factor_mode")
    return finish()
