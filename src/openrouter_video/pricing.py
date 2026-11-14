"""Pure evidence-scoped preflight estimates; never grants submission authority."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum

from openrouter_video.capabilities import CapabilityModeStatus, mode_enforcement_matrix
from openrouter_video.local_media import LocalMedia
from openrouter_video.models import (
    InferenceMethod,
    InputReferenceKind,
    ModelCapabilities,
    ProviderOption,
)
from openrouter_video.pricing_profile import (
    ChargeBreakdown,
    TariffCase,
    TariffProfile,
    decimal_value,
    evaluate_charge_plan,
    load_profiles,
    normalize_rate,
)

RULES_VERSION = "ACI-1.0"


class EstimateAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class EstimateState(str, Enum):
    FORMULA = "FORMULA"
    RANGE = "RANGE"
    RATE_ONLY = "RATE_ONLY"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class MediaCostMetadata:
    """One active occurrence, containing only safe scalar read-only metadata."""

    kind: InputReferenceKind
    role: str = "reference"
    duration_seconds: Decimal | None = None
    width: int | None = None
    height: int | None = None
    fps: Decimal | None = None
    status: str = "UNKNOWN"

    def __post_init__(self) -> None:
        roles = {"reference", "source_video", "first_frame", "last_frame", "audio"}
        if self.role not in roles or self.status not in {"KNOWN", "HINT", "UNKNOWN"}:
            raise ValueError("invalid_media_metadata")
        if self.role == "source_video" and self.kind is not InputReferenceKind.VIDEO:
            raise ValueError("invalid_media_role")
        if self.role in {"first_frame", "last_frame"} and self.kind is not InputReferenceKind.IMAGE:
            raise ValueError("invalid_media_role")
        if self.role == "audio" and self.kind is not InputReferenceKind.AUDIO:
            raise ValueError("invalid_media_role")
        for value in (self.duration_seconds, self.fps):
            if value is not None and not 0 < decimal_value(value) <= 1000000:
                raise ValueError("invalid_media_quantity")
        for dimension in (self.width, self.height):
            if dimension is not None and (
                type(dimension) is not int or not 0 < dimension <= 100000
            ):
                raise ValueError("invalid_media_geometry")
        if (self.width is None) != (self.height is None):
            raise ValueError("incomplete_media_geometry")
        if self.status == "UNKNOWN" and any(
            value is not None
            for value in (
                self.duration_seconds,
                self.width,
                self.height,
                self.fps,
            )
        ):
            raise ValueError("unknown_metadata_has_values")


def metadata_from_local_media(
    media: LocalMedia,
    *,
    kind: InputReferenceKind,
    role: str,
) -> MediaCostMetadata:
    """Read existing native callbacks only; never encode, open files, execute or upload."""
    duration, width, height = None, None, None
    try:
        if media.duration is not None:
            # Existing host callbacks use floats. Convert their textual metadata once;
            # monetary rates and arithmetic never enter through binary floating point.
            duration = decimal_value(str(media.duration()))
        if media.geometry is not None:
            width, height = media.geometry()
        return MediaCostMetadata(kind, role, duration, width, height, status="KNOWN")
    except (ValueError, TypeError, ArithmeticError):
        return MediaCostMetadata(kind, role)


@dataclass(frozen=True, slots=True)
class CostProviderControl:
    """A bounded neutral-control descriptor. Text content is never accepted."""

    provider: str
    key: str
    number_value: Decimal | None = None
    text_length: int | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider, str)
            or len(self.provider) > 64
            or not re.fullmatch(
                r"[a-z0-9]+(?:-[a-z0-9]+)*",
                self.provider,
            )
            or not isinstance(self.key, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.key)
        ):
            raise ValueError("invalid_cost_provider_identifier")
        if (self.number_value is None) == (self.text_length is None):
            raise ValueError("cost_provider_descriptor_requires_one_value")
        if self.number_value is not None:
            decimal_value(self.number_value)
        if self.text_length is not None and (
            type(self.text_length) is not int or not 0 <= self.text_length <= 65536
        ):
            raise ValueError("unbounded_cost_provider_text_length")


@dataclass(frozen=True, slots=True)
class CostEstimateInputs:
    """Effective cost-only configuration. No prompt, URL, path or graph identifiers."""

    model_id: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    size: str | None = None
    generate_audio: bool | None = False
    inference_method: InferenceMethod = InferenceMethod.T2V
    reference_kinds: tuple[InputReferenceKind, ...] = ()
    reference_count: int = 0
    source_video_present: bool = False
    schema_version: int = 1
    context_revision: int = 0
    media: tuple[MediaCostMetadata, ...] = ()
    upscale_factor: int | Decimal | None = None
    creativity: int | None = None
    effective_output_seconds: Decimal | None = None
    provider_policy_version: str | None = None
    provider_controls: tuple[CostProviderControl, ...] = ()


def project_cost_provider_controls(
    capabilities: ModelCapabilities,
    inputs: CostEstimateInputs,
) -> tuple[ProviderOption, ...] | None:
    """Intersect exact neutral tariff data with current Core's typed/live validation.

    A synthetic string validates only the original text's reported type/length.
    No source content is copied, serialized or permitted to affect pricing intent.
    """
    if not inputs.provider_controls:
        return ()
    if len(inputs.provider_controls) > 8 or inputs.provider_policy_version != RULES_VERSION:
        return None
    profile = next(
        (
            profile
            for profile in load_profiles()
            if profile.model_id == capabilities.model_id
            and profile.canonical_slug == capabilities.canonical_slug
        ),
        None,
    )
    if profile is None:
        return None
    from openrouter_video.configuration import project_method, project_semantic_values

    core = project_method(capabilities, inputs.inference_method.value)
    current = core.get("controls", {}).get("provider_options", {})
    seen: set[tuple[str, str]] = set()
    options: list[ProviderOption] = []
    for descriptor in inputs.provider_controls:
        identity = (descriptor.provider, descriptor.key)
        policy = next(
            (
                policy
                for policy in profile.neutral_controls
                if (policy.provider, policy.key) == identity
                and inputs.inference_method.value in policy.methods
            ),
            None,
        )
        if identity in seen:
            raise ValueError("duplicate_cost_provider_descriptor")
        if policy is None:
            return None
        seen.add(identity)
        spec = current.get("providers", {}).get(descriptor.provider, {}).get(descriptor.key)
        if (
            not isinstance(spec, dict)
            or spec.get("type") != policy.type
            or any(
                field in spec
                for field in ("container", "omits_controls", "format", "fields", "items", "values")
            )
        ):
            return None
        value: str | float
        if policy.type == "string":
            if (
                descriptor.text_length is None
                or descriptor.number_value is not None
                or "values" in spec
            ):
                raise ValueError("cost_provider_descriptor_type_mismatch")
            value = "x" * descriptor.text_length
        else:
            if descriptor.number_value is None or descriptor.text_length is not None:
                raise ValueError("cost_provider_descriptor_type_mismatch")
            value = float(decimal_value(descriptor.number_value))
        options.append(ProviderOption(descriptor.provider, descriptor.key, value))
    # Reuse the existing validator and live passthrough allowlist, not a second
    # numeric/domain implementation. The result stays inside the estimate branch.
    project_semantic_values(
        capabilities,
        inputs.inference_method.value,
        {
            "provider_options": tuple(options),
            "duration": inputs.duration,
            "resolution": inputs.resolution,
            "aspect_ratio": inputs.aspect_ratio,
            "size": inputs.size,
            "generate_audio": inputs.generate_audio,
            "geometry_authority": "EXACT" if inputs.size else "NORMALIZED",
        },
    )
    return tuple(options)


@dataclass(frozen=True, slots=True)
class EstimateResult:
    """Compatibility envelope; a numeric total exists only for complete FORMULA."""

    availability: EstimateAvailability
    observed_at: datetime
    estimated_cost_usd: Decimal | None = None
    provenance: str | None = None
    applied_skus: tuple[str, ...] = ()
    reason: str | None = None
    state: EstimateState = EstimateState.UNKNOWN
    amount_usd: Decimal | None = None
    lower_usd: Decimal | None = None
    upper_usd: Decimal | None = None
    range_kind: str | None = None
    rate_usd: Decimal | None = None
    rate_unit: str | None = None
    breakdown: tuple[ChargeBreakdown, ...] = ()
    assumptions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    snapshot_hash: str | None = None
    rates_hash: str | None = None
    rules_version: str = RULES_VERSION
    context_revision: int = 0

    def __post_init__(self) -> None:
        # Old positional constructors retain their behavior and gain the new contract.
        if self.availability is EstimateAvailability.AVAILABLE:
            if self.estimated_cost_usd is None:
                raise ValueError("available_estimate_requires_amount")
            object.__setattr__(self, "state", EstimateState.FORMULA)
            object.__setattr__(self, "amount_usd", self.estimated_cost_usd)
        elif self.estimated_cost_usd is not None or self.amount_usd is not None:
            raise ValueError("incomplete_estimate_cannot_have_total")
        if not self.reason_codes and self.reason:
            object.__setattr__(self, "reason_codes", (self.reason,))

    @classmethod
    def unavailable(
        cls,
        observed_at: datetime,
        reason: str,
        *,
        state: EstimateState = EstimateState.UNKNOWN,
        context_revision: int = 0,
    ) -> EstimateResult:
        return cls(
            EstimateAvailability.UNAVAILABLE,
            observed_at,
            reason=reason,
            state=state,
            context_revision=context_revision,
        )


class PreflightCostEstimator:
    """One exact-profile resolver and one Decimal arithmetic implementation."""

    __slots__ = ()

    def estimate(
        self,
        capabilities: ModelCapabilities,
        inputs: CostEstimateInputs,
        *,
        observed_at: datetime,
    ) -> EstimateResult:
        try:
            neutral = project_cost_provider_controls(capabilities, inputs)
        except ValueError:
            return EstimateResult.unavailable(
                observed_at,
                "provider_control_invalid",
                state=EstimateState.INVALID,
                context_revision=inputs.context_revision,
            )
        if neutral is None:
            return EstimateResult.unavailable(
                observed_at,
                "provider_configuration_pricing_unverified",
                context_revision=inputs.context_revision,
            )
        reason = _invalid_reason(capabilities, inputs)
        if reason:
            return EstimateResult.unavailable(
                observed_at,
                reason,
                state=EstimateState.INVALID,
                context_revision=inputs.context_revision,
            )
        evidence = capabilities.pricing_evidence
        if evidence is None or not evidence.skus:
            return EstimateResult.unavailable(
                observed_at,
                "pricing_evidence_unavailable",
                context_revision=inputs.context_revision,
            )
        try:
            rates = {sku.key: decimal_value(sku.rate_usd) for sku in evidence.skus}
            if len(rates) != len(evidence.skus):
                raise ValueError("duplicate_pricing_sku")
        except ValueError:
            return EstimateResult.unavailable(
                observed_at, "pricing_rate_invalid", context_revision=inputs.context_revision
            )
        profiles = load_profiles()
        profile = next((p for p in profiles if p.model_id == capabilities.model_id), None)
        units = {
            str(charge["sku"]): str(charge["unit"])
            for rule in (() if profile is None else profile.rules)
            for charge in rule.charges
        }
        identity = {
            "endpoint_family": "video",
            "model_id": capabilities.model_id,
            "canonical_slug": capabilities.canonical_slug,
            "currency": "USD",
            "rates": {
                key: {
                    "unit": units.get(key, "RAW_UNCLASSIFIED"),
                    "value": _canonical_decimal(
                        normalize_rate(value, units[key]) if key in units else value
                    ),
                }
                for key, value in sorted(rates.items())
            },
        }
        rates_hash = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        legacy_units = set(rates) == {"generate"} or all(
            key == "per-video-second" or re.fullmatch(r"per-video-second-[a-z0-9]+", key)
            for key in rates
        )
        legacy_bridge = (
            legacy_units
            and set(rates) != {"generate"}
            and profile is not None
            and capabilities.canonical_slug == profile.canonical_slug
            and inputs.inference_method is InferenceMethod.T2V
            and not inputs.reference_kinds
            and inputs.reference_count == 0
            and not inputs.source_video_present
            and not inputs.media
            and _legacy_profile_is_complete(profile, inputs)
        )
        if legacy_bridge or profile is None:
            result = self._legacy(capabilities, inputs, observed_at, rates)
        elif legacy_units:
            result = EstimateResult.unavailable(observed_at, "legacy_pricing_scope_unverified")
        elif capabilities.canonical_slug != profile.canonical_slug:
            result = EstimateResult.unavailable(observed_at, "canonical_revision_unverified")
        elif set(rates) - set(profile.known_skus):
            known = self._profile(profile, capabilities, inputs, observed_at, rates)
            result = EstimateResult(
                EstimateAvailability.UNAVAILABLE,
                observed_at,
                reason="unclassified_pricing_sku",
                state=EstimateState.PARTIAL,
                breakdown=known.breakdown,
                assumptions=known.assumptions,
                applied_skus=known.applied_skus,
            )
        else:
            result = self._profile(profile, capabilities, inputs, observed_at, rates)
        if any(control.text_length is not None for control in inputs.provider_controls):
            result = replace(
                result,
                assumptions=result.assumptions
                + (
                    "Pricing-neutral text content is redacted; "
                    "its reported length is a client hint. "
                    "Generation retains the existing full control validation.",
                ),
            )
        return replace(result, rates_hash=rates_hash, context_revision=inputs.context_revision)

    def _profile(
        self,
        profile: TariffProfile,
        capabilities: ModelCapabilities,
        inputs: CostEstimateInputs,
        observed_at: datetime,
        rates: Mapping[str, object],
    ) -> EstimateResult:
        resolution, width, height, assumptions = _geometry(profile, inputs)
        context = _profile_context(profile, inputs, resolution)
        matches = [rule for rule in profile.rules if _matches(rule, context)]
        if len(matches) != 1:
            reason = "exclusive_rule_conflict" if matches else profile.default_reason
            return EstimateResult.unavailable(observed_at, reason)
        rule = matches[0]
        if not rule.active:
            return EstimateResult.unavailable(
                observed_at,
                rule.reason or "tariff_semantics_unresolved",
                state=EstimateState.PARTIAL
                if rule.expected_state == "PARTIAL"
                else EstimateState.UNKNOWN,
            )
        if rule.require_equal_skus:
            try:
                aliases = [decimal_value(rates[key]) for key in rule.require_equal_skus]
            except (KeyError, ValueError):
                return EstimateResult.unavailable(observed_at, "alias_evidence_unavailable")
            if len(set(aliases)) != 1:
                return EstimateResult.unavailable(observed_at, "alias_rates_diverged")
        if rule.expected_state in {"UNKNOWN", "INVALID", "STALE"}:
            return EstimateResult.unavailable(
                observed_at,
                rule.reason or "tariff_semantics_unresolved",
                state=EstimateState(rule.expected_state),
            )
        values: dict[str, object] = {
            "output_seconds": inputs.duration if inputs.duration != -1 else None,
            "width": width,
            "height": height,
            "reference_images": sum(
                kind is InputReferenceKind.IMAGE for kind in inputs.reference_kinds
            ),
            "active_image_inputs": sum(
                kind is InputReferenceKind.IMAGE for kind in inputs.reference_kinds
            )
            + (
                1
                if inputs.inference_method is InferenceMethod.I2V
                else 2
                if inputs.inference_method is InferenceMethod.FLF2V
                else 0
            ),
            "effective_output_seconds": inputs.effective_output_seconds,
        }
        sources = [
            item
            for item in inputs.media
            if item.role == "source_video" and item.status in {"KNOWN", "HINT"}
        ]
        if len(sources) == 1:
            values["source_seconds"] = sources[0].duration_seconds
            if sources[0].status == "HINT":
                assumptions += (
                    "Source duration comes from an already loaded media preview; "
                    "it is an estimate hint, not authoritative delivered usage.",
                )
            if profile.metadata_policy == "UPSCALE_SOURCE_24":
                # Native output geometry/cap rounding is not established by the
                # source size or factor. Keep the applicable rate until authoritative
                # delivered geometry is available through ordinary materialization.
                values["width"], values["height"] = None, None
        plan = evaluate_charge_plan(rule.charges, values, rates=rates)
        rows = tuple(replace(row, evidence=rule.evidence) for row in plan.breakdown)
        if rule.expected_state == "FORMULA" and plan.state == "FORMULA":
            return EstimateResult(
                EstimateAvailability.AVAILABLE,
                observed_at,
                plan.amount_usd,
                "evidence-scoped catalogue tariff",
                tuple(row.sku for row in rows),
                breakdown=rows,
                assumptions=assumptions
                + ("Advisory continuous formula; provider billing may differ.",),
            )
        state = (
            EstimateState.PARTIAL
            if rule.expected_state == "PARTIAL" or plan.state == "PARTIAL"
            else EstimateState.UNKNOWN
        )
        rate, unit = None, None
        bases = [
            charge
            for index, charge in enumerate(rule.charges)
            if charge.get("relation", "base" if index == 0 else "add") == "base"
        ]
        single_rate_with_floor = (
            rule.expected_state == "RATE_ONLY"
            and len(bases) == 1
            and all(
                charge is bases[0] or charge.get("relation") == "minimum" for charge in rule.charges
            )
        )
        if len(rule.charges) == 1 or single_rate_with_floor:
            charge = bases[0]
            try:
                rate = normalize_rate(rates[str(charge["sku"])], str(charge["unit"]))
                unit = _rate_unit(str(charge["quantity"]), charge.get("rate_unit"))
            except (KeyError, ValueError):
                pass
            if (
                rate is not None
                and unit is not None
                and rule.expected_state in {"FORMULA", "RATE_ONLY"}
            ):
                state = EstimateState.RATE_ONLY
        return EstimateResult(
            EstimateAvailability.UNAVAILABLE,
            observed_at,
            reason=(
                "delivered_output_geometry_or_fps_unproven"
                if profile.metadata_policy == "UPSCALE_SOURCE_24"
                else rule.reason or plan.reason or "billing_quantity_unavailable"
            ),
            state=state,
            rate_usd=rate,
            rate_unit=unit,
            breakdown=rows,
            assumptions=assumptions,
            applied_skus=tuple(row.sku for row in rows),
        )

    def _legacy(
        self,
        capabilities: ModelCapabilities,
        inputs: CostEstimateInputs,
        observed_at: datetime,
        rates: Mapping[str, object],
    ) -> EstimateResult:
        # The original documented generic vocabulary remains compatible. Current
        # opaque catalogue keys require an exact evidence profile, never a name pattern.
        if inputs.source_video_present or InputReferenceKind.VIDEO in inputs.reference_kinds:
            return EstimateResult.unavailable(
                observed_at, "video_input_pricing_semantics_ambiguous"
            )
        if InputReferenceKind.AUDIO in inputs.reference_kinds:
            return EstimateResult.unavailable(
                observed_at, "audio_input_pricing_semantics_ambiguous"
            )
        if inputs.duration == -1:
            return EstimateResult.unavailable(observed_at, "automatic_duration_unknown")
        unit = "USD"
        if set(rates) == {"generate"}:
            key, quantity = "generate", "fixed"
        elif (
            len(rates) == 1
            and inputs.inference_method in {InferenceMethod.T2V, InferenceMethod.I2V}
            and not inputs.reference_kinds
            and (
                match := re.fullmatch(
                    r"(duration_seconds|cents_per_video_output_second)(?:_(\d+p|\d+[kK]))?",
                    next(iter(rates)),
                )
            )
            is not None
        ):
            key = next(iter(rates))
            if match.group(2) and (
                inputs.resolution is None
                or match.group(2).casefold() != inputs.resolution.casefold()
            ):
                return EstimateResult.unavailable(observed_at, "matching_pricing_sku_unavailable")
            if inputs.duration is None or inputs.duration <= 0:
                return EstimateResult.unavailable(observed_at, "duration_required_for_pricing")
            quantity = "output_seconds"
            unit = "USD" if match.group(1) == "duration_seconds" else "cents"
        elif all(
            key == "per-video-second" or re.fullmatch(r"per-video-second-[a-z0-9]+", key)
            for key in rates
        ):
            specific = f"per-video-second-{inputs.resolution.lower()}" if inputs.resolution else ""
            key = specific if specific in rates else "per-video-second"
            if key not in rates:
                return EstimateResult.unavailable(observed_at, "matching_pricing_sku_unavailable")
            if inputs.duration is None or inputs.duration <= 0:
                return EstimateResult.unavailable(observed_at, "duration_required_for_pricing")
            quantity = "output_seconds"
        else:
            # Existing explicitly structured output/image/floor units are reusable
            # contracts, unlike opaque provider SKU names. Unknown charges or two
            # competing base shapes still fail closed.
            specific = f"cents_per_second_output_{inputs.resolution}" if inputs.resolution else ""
            generic = "cents_per_second_output"
            known = {"cents_per_image_input", "minimum_cents_per_generation"}
            output_keys = {
                candidate
                for candidate in rates
                if candidate == generic
                or re.fullmatch(r"cents_per_second_output_[a-z0-9]+", candidate)
            }
            inactive = {
                candidate
                for candidate in rates
                if re.fullmatch(r"cents_per_second_video_continuation_[a-z0-9]+", candidate)
                and inputs.inference_method is InferenceMethod.T2V
            }
            if set(rates) - known - output_keys - inactive or not output_keys:
                return EstimateResult.unavailable(observed_at, "pricing_sku_semantics_ambiguous")
            if specific in output_keys and generic in output_keys:
                return EstimateResult.unavailable(observed_at, "exclusive_rule_conflict")
            key = specific if specific in output_keys else generic
            if key not in rates:
                return EstimateResult.unavailable(observed_at, "matching_pricing_sku_unavailable")
            charges: list[Mapping[str, object]] = [
                {"sku": key, "unit": "cents", "quantity": "output_seconds"},
            ]
            if "cents_per_image_input" in rates:
                charges.append(
                    {
                        "sku": "cents_per_image_input",
                        "unit": "cents",
                        "quantity": "active_image_inputs",
                        "relation": "add",
                    }
                )
            if "minimum_cents_per_generation" in rates:
                charges.append(
                    {
                        "sku": "minimum_cents_per_generation",
                        "unit": "cents",
                        "quantity": "fixed",
                        "relation": "minimum",
                    }
                )
            image_count = sum(kind is InputReferenceKind.IMAGE for kind in inputs.reference_kinds)
            image_count += (
                1
                if inputs.inference_method is InferenceMethod.I2V
                else 2
                if inputs.inference_method is InferenceMethod.FLF2V
                else 0
            )
            plan = evaluate_charge_plan(
                charges,
                {"output_seconds": inputs.duration, "active_image_inputs": image_count},
                rates=rates,
            )
            if plan.state != "FORMULA":
                return EstimateResult.unavailable(
                    observed_at, plan.reason or "billing_quantity_unavailable"
                )
            return EstimateResult(
                EstimateAvailability.AVAILABLE,
                observed_at,
                plan.amount_usd,
                "documented structured output/image/minimum units",
                tuple(row.sku for row in plan.breakdown),
                breakdown=plan.breakdown,
            )
        plan = evaluate_charge_plan(
            [{"sku": key, "unit": unit, "quantity": quantity}],
            {"output_seconds": inputs.duration},
            rates=rates,
        )
        if plan.state != "FORMULA":
            return EstimateResult.unavailable(observed_at, plan.reason or "pricing_unavailable")
        return EstimateResult(
            EstimateAvailability.AVAILABLE,
            observed_at,
            plan.amount_usd,
            f"catalogue pricing_skus.{key}",
            (key,),
            breakdown=plan.breakdown,
        )


def _profile_context(
    profile: TariffProfile,
    inputs: CostEstimateInputs,
    resolution: str | None,
) -> dict[str, object]:
    """One predicate context shared by profile resolution and legacy compatibility."""
    return {
        "method": inputs.inference_method.value,
        "resolution": resolution,
        "generated_audio": (
            profile.audio_default
            if inputs.generate_audio is None and inputs.schema_version == 2
            else inputs.generate_audio
        ),
        "has_video": inputs.source_video_present
        or InputReferenceKind.VIDEO in inputs.reference_kinds,
        "has_references": inputs.reference_count > 0,
        "duration": inputs.duration,
        "upscale_mode": None
        if inputs.creativity is None
        else ("precise" if inputs.creativity == 0 else "creative"),
    }


def _legacy_profile_is_complete(profile: TariffProfile, inputs: CostEstimateInputs) -> bool:
    """A legacy unit cannot erase a current profile's unresolved charge relations."""
    resolution, _, _, _ = _geometry(profile, inputs)
    context = _profile_context(profile, inputs, resolution)
    matches = [rule for rule in profile.rules if _matches(rule, context)]
    if len(matches) != 1:
        return False
    rule = matches[0]
    if not rule.active or rule.expected_state != "FORMULA" or rule.require_equal_skus:
        return False
    base_count = 0
    for index, charge in enumerate(rule.charges):
        relation = charge.get("relation", "base" if index == 0 else "add")
        if relation == "base":
            if charge["quantity"] != "output_seconds" or charge.get("free_allowance", 0) != 0:
                return False
            base_count += 1
        elif relation == "add" and charge["quantity"] in {
            "active_image_inputs",
            "reference_images",
        }:
            # The caller requires effective T2V and no active media/reference/source
            # occurrences. These counts are therefore exactly zero, independent of
            # rate or any nonnegative free allowance. No other addition is omitted.
            if (
                inputs.reference_count
                or inputs.reference_kinds
                or inputs.media
                or inputs.source_video_present
            ):
                return False
        else:
            return False
    return base_count == 1


def _matches(rule: TariffCase, context: Mapping[str, object]) -> bool:
    # None is a genuine unknown, not false. An explicit null predicate can describe it.
    return all(
        any(
            type(context.get(key)) is type(value) and context.get(key) == value for value in options
        )
        for key, options in rule.when
    )


def _canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return (text.rstrip("0").rstrip(".") or "0") if "." in text else text


def _geometry(
    profile: TariffProfile, inputs: CostEstimateInputs
) -> tuple[str | None, int | None, int | None, tuple[str, ...]]:
    resolution, size = inputs.resolution, inputs.size
    assumptions: tuple[str, ...] = ()
    if size:
        tiers = {tier for tier, ratios in profile.geometry_map.items() if size in ratios.values()}
        if len(tiers) == 1:
            resolution = next(iter(tiers))
    elif inputs.resolution and inputs.aspect_ratio:
        size = profile.geometry_map.get(inputs.resolution, {}).get(inputs.aspect_ratio)
        if size and profile.geometry_status == "EXPLICIT_CAPTURE_MAP_ESTIMATE_ASSUMPTION":
            assumptions = (
                "Geometry uses the explicit catalogue size mapping; "
                "actual provider geometry may differ.",
            )
    if size and re.fullmatch(r"[1-9][0-9]{0,5}x[1-9][0-9]{0,5}", size):
        width, height = (int(part) for part in size.split("x"))
        return resolution, width, height, assumptions
    return resolution, None, None, assumptions


def _rate_unit(quantity: str, declared_unit: object) -> str | None:
    units = {
        "fixed": "generation",
        "output_seconds": "s",
        "source_seconds": "s",
        "effective_output_seconds": "s",
        "video_tokens_output_24": "token",
        "megapixel_seconds_binary_output_24": "MP.s",
        "megapixel_seconds": "MP.s",
    }
    # Unknown quantity has an explicit unit only for exact declared SKU references;
    # this lookup is unit presentation, never charge selection or activation.
    if quantity == "unknown":
        return declared_unit if isinstance(declared_unit, str) else None
    return units.get(quantity)


def _invalid_reason(capabilities: ModelCapabilities, inputs: CostEstimateInputs) -> str | None:
    if type(inputs.schema_version) is not int or inputs.schema_version not in {1, 2}:
        return "cost_schema_invalid"
    if inputs.model_id not in {capabilities.model_id, capabilities.canonical_slug}:
        return "model_mismatch"
    if (
        type(inputs.reference_count) is not int
        or not 0 <= inputs.reference_count <= 64
        or inputs.reference_count != len(inputs.reference_kinds)
    ):
        return "reference_topology_invalid"
    if (
        type(inputs.context_revision) is not int
        or not 0 <= inputs.context_revision <= 9007199254740991
    ):
        return "context_revision_invalid"
    if inputs.generate_audio is not None and type(inputs.generate_audio) is not bool:
        return "audio_intent_invalid"
    if inputs.size is not None and (
        inputs.resolution is not None or inputs.aspect_ratio is not None
    ):
        return "geometry_intent_conflict"
    if inputs.duration is not None and (
        type(inputs.duration) is not int or inputs.duration == 0 or inputs.duration < -1
    ):
        return "duration_invalid"
    selected_values: tuple[tuple[object | None, tuple[object, ...] | None], ...] = (
        (inputs.duration, capabilities.supported_durations),
        (inputs.resolution, capabilities.supported_resolutions),
        (inputs.aspect_ratio, capabilities.supported_aspect_ratios),
        (inputs.size, capabilities.supported_sizes),
    )
    if any(
        selected is not None and (supported is None or selected not in supported)
        for selected, supported in selected_values
    ):
        return "configuration_not_authorized"
    if inputs.generate_audio is True and capabilities.generate_audio is not True:
        return "configuration_not_authorized"
    if (
        mode_enforcement_matrix(capabilities)[inputs.inference_method]
        is not CapabilityModeStatus.READY
    ):
        return "inference_method_not_authorized"
    references = tuple(item.kind for item in inputs.media if item.role == "reference")
    if references and references != inputs.reference_kinds:
        return "metadata_reference_topology_invalid"
    if sum(item.role == "source_video" for item in inputs.media) > int(inputs.source_video_present):
        return "metadata_source_topology_invalid"
    for role, method in (
        ("first_frame", (InferenceMethod.I2V, InferenceMethod.FLF2V)),
        ("last_frame", (InferenceMethod.FLF2V,)),
    ):
        count = sum(item.role == role for item in inputs.media)
        if count > 1 or (count and inputs.inference_method not in method):
            return "metadata_frame_topology_invalid"
    if len(inputs.media) > 64:
        return "media_metadata_unbounded"
    if inputs.schema_version == 2:
        for role, methods in (
            ("first_frame", {InferenceMethod.I2V, InferenceMethod.FLF2V}),
            ("last_frame", {InferenceMethod.FLF2V}),
        ):
            if inputs.inference_method in methods and not any(
                item.role == role for item in inputs.media
            ):
                return "required_frame_not_connected"
    return None


__all__ = (
    "CostEstimateInputs",
    "CostProviderControl",
    "EstimateAvailability",
    "EstimateResult",
    "EstimateState",
    "MediaCostMetadata",
    "PreflightCostEstimator",
    "metadata_from_local_media",
    "project_cost_provider_controls",
)
