"""Capability discovery, bounded cache fallback, and paid-request validation."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import math
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from itertools import islice, product
from typing import Any, NoReturn
from urllib.parse import urlsplit

from openrouter_video.client import DiscoveryClient
from openrouter_video.configuration import (
    CONFIGURATION_KEY,
    REQUEST_SHAPES_KEY,
    configuration_status,
    input_constraint_reconciliation,
    profile_constraints,
    project_method,
    project_semantic_values,
    projected_shape_valid,
)
from openrouter_video.errors import (
    MalformedOpenRouterResponseError,
    OpenRouterHTTPError,
    ProductFailureError,
    TransportError,
)
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.image_transport import image_data_url_metadata, is_supported_image_data_url
from openrouter_video.local_media import NativeMediaError
from openrouter_video.models import (
    BillingContext,
    FrameReference,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
    ProductError,
    ProductErrorCode,
    ProviderOption,
)
from openrouter_video.persistence import JobStore

FRESH_TTL = timedelta(minutes=15)
LKG_TTL = timedelta(hours=24)
_SIZE_PATTERN = re.compile(r"^[1-9][0-9]*x[1-9][0-9]*$")
_BACKOFF_SECONDS = (5.0, 10.0, 20.0, 30.0, 60.0)

Sleep = Callable[[float], Awaitable[None]]
Now = Callable[[], datetime]
Jitter = Callable[[float], float]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jitter(value: float) -> float:
    return random.uniform(value * 0.8, value * 1.2)  # noqa: S311 - retry timing only


@dataclass(frozen=True, slots=True)
class CapabilityObservation:
    """Normalized catalog plus its authoritative successful-observation time."""

    observed_at: datetime
    models: tuple[ModelCapabilities, ...]
    source_state: str = "FRESH"
    evolution: dict[str, Any] | None = None


class CapabilityModeStatus(str, Enum):
    """Evidence-derived runtime disposition for one independent product mode."""

    READY = "READY"
    CAPABILITY_SIGNAL_GAP = "CAPABILITY_SIGNAL_GAP"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    DEFERRED = "DEFERRED"


def inference_method_matrix(
    capabilities: ModelCapabilities,
) -> dict[InferenceMethod, CapabilityModeStatus]:
    """Reviewed public shapes; raw conceptual fixtures retain the global recipes."""

    if any(
        f.key in {REQUEST_SHAPES_KEY, "per_kind_max", "per_kind_min", "__catalogue_observation__"}
        for f in capabilities.evidence_facts
    ):
        return {
            method: CapabilityModeStatus.READY
            if (state := project_method(capabilities, method.value)["state"]) == "SUPPORTED"
            else CapabilityModeStatus(state)
            for method in InferenceMethod
        }

    from openrouter_video.recipes import RECIPES, evaluate

    return {
        recipe.method: CapabilityModeStatus(evaluate(capabilities, recipe)) for recipe in RECIPES
    }


def _reference_kind_status(
    limit: int | None,
    kinds: frozenset[InputReferenceKind],
    kind: InputReferenceKind,
    minimum: int,
) -> CapabilityModeStatus:
    if kind not in kinds:
        return CapabilityModeStatus.UNSUPPORTED
    if limit is None:
        return CapabilityModeStatus.READY
    return CapabilityModeStatus.READY if limit >= minimum else CapabilityModeStatus.UNSUPPORTED


def _intent_status(
    video_status: CapabilityModeStatus,
    supported: bool | None,
    conflict: bool,
) -> CapabilityModeStatus:
    if video_status is not CapabilityModeStatus.READY:
        return video_status
    if conflict:
        return CapabilityModeStatus.CONFLICT
    if supported is None:
        return CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
    return CapabilityModeStatus.READY if supported else CapabilityModeStatus.UNSUPPORTED


def mode_enforcement_matrix(
    capabilities: ModelCapabilities,
) -> dict[InferenceMethod, CapabilityModeStatus]:
    """Compatibility name for callers migrating to the Phase-10 method registry."""

    return inference_method_matrix(capabilities)


def infer_legacy_inference_method(
    *,
    first_frame: FrameReference | None,
    last_frame: FrameReference | None,
    references: tuple[InputReference, ...],
) -> InferenceMethod:
    """Migrate legacy topology without inventing Edit or Extend intent."""

    if first_frame is not None or last_frame is not None:
        if first_frame is not None and last_frame is not None:
            return InferenceMethod.FLF2V
        if first_frame is not None:
            return InferenceMethod.I2V
        raise ValueError("A legacy last frame without a first frame has no valid Phase-10 intent.")
    if not references:
        return InferenceMethod.T2V
    kinds = {reference.kind for reference in references}
    if kinds == {InputReferenceKind.IMAGE}:
        return InferenceMethod.IR2V if len(references) == 1 else InferenceMethod.MI2V
    if kinds == {InputReferenceKind.VIDEO}:
        return InferenceMethod.VR2V
    if kinds == {InputReferenceKind.AUDIO}:
        return InferenceMethod.AR2V
    return InferenceMethod.MMR2V


class CapabilityService:
    """Serve fresh catalog data and bounded LKG only when live discovery fails."""

    __slots__ = ("_client", "_jitter", "_now", "_sleep", "_store", "_catalog_lock")

    def __init__(
        self,
        *,
        client: DiscoveryClient,
        store: JobStore,
        sleep: Sleep = asyncio.sleep,
        now: Now = _utc_now,
        jitter: Jitter = _jitter,
    ) -> None:
        self._client = client
        self._store = store
        self._sleep = sleep
        self._now = now
        self._jitter = jitter
        self._catalog_lock = asyncio.Lock()

    async def catalog(self) -> CapabilityObservation:
        async with self._catalog_lock:
            observation = await self._catalog()
            return replace(observation, evolution=self._store.load_capability_evolution())

    async def _catalog(self) -> CapabilityObservation:
        """Return fresh cached data, otherwise refresh and use LKG only on failure."""

        current = self._now()
        cached = self._store.load_capability_catalog()
        if cached is not None and current - cached[0] <= FRESH_TTL:
            return CapabilityObservation(cached[0], cached[1])

        failure: BaseException | None = None
        for attempt in range(3):
            try:
                models = await self._client.list_video_models()
            except (
                TransportError,
                OpenRouterHTTPError,
                MalformedOpenRouterResponseError,
            ) as exc:
                failure = exc
                if attempt == 2 or not _retryable_discovery(exc):
                    break
                retry_after = (
                    exc.retry_after_seconds if isinstance(exc, OpenRouterHTTPError) else None
                )
                delay = (
                    retry_after
                    if retry_after is not None
                    else self._jitter(_BACKOFF_SECONDS[attempt])
                )
                await self._sleep(delay)
            else:
                observed_at = self._now()
                self._store.replace_capability_catalog(
                    models,
                    observed_at,
                    evolution=capability_evolution(cached[1] if cached is not None else (), models),
                )
                return CapabilityObservation(observed_at, models)

        if isinstance(failure, OpenRouterHTTPError) and failure.status_code in {401, 403}:
            raise ProductFailureError(
                ProductError(
                    ProductErrorCode.API_KEY_INVALID,
                    "OpenRouter rejected the configured API key.",
                    BillingContext.NO_SUBMIT,
                )
            )
        if cached is not None and current - cached[0] <= LKG_TTL:
            return CapabilityObservation(cached[0], cached[1], "STALE_FALLBACK")
        raise ProductFailureError(
            ProductError(
                ProductErrorCode.DISCOVERY_UNAVAILABLE,
                "The OpenRouter video model catalog is temporarily unavailable.",
                BillingContext.NO_SUBMIT,
                retryable=True,
            )
        )

    async def resolve(self, model_id: str) -> ModelCapabilities:
        """Resolve exactly one model without substituting another model."""

        observation = await self.catalog()
        for model in observation.models:
            if model.model_id == model_id or model.canonical_slug == model_id:
                if self._now() - observation.observed_at <= FRESH_TTL:
                    return enrich_capabilities(model)
                return model
        raise ProductFailureError(
            ProductError(
                ProductErrorCode.MODEL_UNAVAILABLE,
                "The selected video model is not available in the current catalog.",
                BillingContext.NO_SUBMIT,
            )
        )

    async def effective_catalog(self) -> CapabilityObservation:
        """Return catalogue truth with overlays only while the observation is fresh."""

        observation = await self.catalog()
        if not self.is_fresh(observation):
            return observation
        return CapabilityObservation(
            observation.observed_at,
            tuple(enrich_capabilities(model) for model in observation.models),
            observation.source_state,
            observation.evolution,
        )

    def is_fresh(self, observation: CapabilityObservation) -> bool:
        """Return whether external truth is inside the approved freshness window."""

        return self._now() - observation.observed_at <= FRESH_TTL


def catalogue_metadata(model: ModelCapabilities) -> dict[str, Any]:
    """The existing persisted evidence is the only discovery observation store."""
    return next(
        (
            f.value
            for f in model.evidence_facts
            if f.key == "__catalogue_observation__" and isinstance(f.value, dict)
        ),
        {},
    )


def canonical_semantics(value: Any, key: str = "") -> Any:
    """Canonicalize set-like domains only; ordered media and wire paths retain order."""
    if isinstance(value, dict):
        return {
            k: canonical_semantics(v, k)
            for k, v in sorted(value.items())
            if k not in {"observed_at", "upstream_observed_at", "artifact_version"}
        }
    if isinstance(value, (list, tuple)):
        items = [canonical_semantics(v, key) for v in value]
        if key.startswith("supported_") or key in {
            "values",
            "reference_kinds",
            "kind_sets",
            "allowed_passthrough_parameters",
        }:
            return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
        if key == "models":
            return sorted(items, key=lambda v: str(v.get("model_id", v.get("id", ""))))
        if key in {"capability_evidence", "evidence"}:
            return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
        return items
    return value


def semantic_fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(canonical_semantics(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def capability_changes(
    previous: tuple[ModelCapabilities, ...], current: tuple[ModelCapabilities, ...]
) -> dict[str, Any]:
    """Deterministic successive-observation diff, including absent versus null/type changes."""
    before = {m.model_id: catalogue_metadata(m) for m in previous}
    after = {m.model_id: catalogue_metadata(m) for m in current}
    changes = []
    for mid in sorted(before.keys() | after.keys()):
        if mid not in before or mid not in after:
            changes.append(
                {
                    "model_id": mid,
                    "field": "model",
                    "change": "ADDED" if mid in after else "REMOVED",
                }
            )
        a, b = before.get(mid, {}), after.get(mid, {})
        for key in sorted(a.keys() | b.keys()):
            if key not in a or key not in b:
                event = "ADDED" if key in b else "REMOVED"
            elif semantic_fingerprint({key: a[key]}) == semantic_fingerprint({key: b[key]}):
                continue
            else:
                event = "TYPE_CHANGED" if type(a[key]) is not type(b[key]) else "VALUE_CHANGED"
            changes.append({"model_id": mid, "field": key, "change": event})
    return {
        "changes": changes,
        "previous_model_count": len(before),
        "current_model_count": len(after),
    }


def capability_completeness(model: ModelCapabilities) -> dict[str, Any]:
    """Derived forward/reverse accounting; this report grants no execution authority."""
    raw = catalogue_metadata(model)
    profiles = {method.value: project_method(model, method.value) for method in InferenceMethod}
    executable = {m.value for m in eligible_methods(model)}
    rows: list[dict[str, Any]] = []
    # A registered profile that claims support must yield a validated wire witness.
    # Keep UNKNOWN/DEFERRED as evidence gaps; they are not positive coverage.
    for method, profile in profiles.items():
        if profile.get("state") == "SUPPORTED" and method not in executable:
            rows.append(
                {
                    "path": "methods." + method,
                    "origin": "DERIVED_PROJECTION",
                    "disposition": "IMPLEMENTATION_GAP",
                    "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT",
                    "reason": (
                        "Registered SUPPORTED method has no validated serializable request witness"
                    ),
                    "value": {"projected_state": "SUPPORTED", "admitted": False},
                }
            )
    control_map = {
        "supported_durations": "duration",
        "supported_resolutions": "resolution",
        "supported_aspect_ratios": "aspect_ratio",
        "supported_sizes": "size",
        "seed": "seed",
        "generate_audio": "generate_audio",
        "upscale_factor": "upscale_factor",
        "creativity": "creativity",
    }
    for key, value in sorted(raw.items()):
        state, reason = "EVIDENCE_GAP", "Unrecognized or incomplete API contract; not serialized"
        if key in {
            "id",
            "canonical_slug",
            "hugging_face_id",
            "name",
            "created",
            "description",
            "pricing_skus",
        }:
            state, reason = (
                "DISCOVERED_CONTRACT_COMPLETE",
                "Catalogue metadata retained; not a request control",
            )
        if key in control_map:
            methods = [
                m
                for m in executable
                if profiles[m]["controls"].get(control_map[key], {}).get("state") == "SUPPORTED"
            ]
            state = "SUPPORTED_EXECUTABLE" if methods else "EVIDENCE_GAP"
            reason = (
                "Applicable validated controls: " + ", ".join(sorted(methods))
                if methods
                else "No confirmed executable method mapping"
            )
        if key in {
            "supported_frame_images",
            "reference_kinds",
            "max_reference_count",
            "mixed_reference_kinds",
            "supports_text_only",
            "source_required",
            "supports_edit",
            "supports_extend",
            REQUEST_SHAPES_KEY,
            CONFIGURATION_KEY,
        }:
            state, reason = (
                "DISCOVERED_CONTRACT_COMPLETE",
                "Represented by method-specific Core profiles; see method/control rows",
            )
            matching = [f for f in model.evidence_facts if f.key == key]
            if any(f.state.value == "CONFLICT" for f in matching):
                state, reason = "CONTRACT_CONFLICT", "Conflicting contract observations retained"
            elif not matching or any(f.state.value == "UNKNOWN" for f in matching):
                state, reason = "EVIDENCE_GAP", "Contract metadata was not fully normalized"
            elif key == REQUEST_SHAPES_KEY and any(
                f.authority == "LIVE_STRUCTURED_API" and f.value != value for f in matching
            ):
                state, reason = "EVIDENCE_GAP", "Some supplied operation contracts were rejected"
        if value is False and state != "CONTRACT_CONFLICT":
            state, reason = "VERIFIED_UNSUPPORTED", "Explicit false; distinct from absent or null"
        if value is None:
            state, reason = "EVIDENCE_GAP", "Explicit null does not establish support or denial"
        rows.append(
            {
                "path": key,
                "origin": "UPSTREAM_FIELD",
                "value": value,
                "disposition": state,
                "reason": reason,
                "source": "https://openrouter.ai/api/v1/videos/models",
            }
        )
    # Compare each normalized catalogue scalar domain with every applicable method
    # projection. This checks conditional method domains independently, without
    # constructing a Cartesian product across unrelated controls.
    scalar_domains = {
        "supported_durations": ("duration", (int, float)),
        "supported_resolutions": ("resolution", (str,)),
        "supported_aspect_ratios": ("aspect_ratio", (str,)),
        "supported_sizes": ("size", (str,)),
    }
    for field, (control_name, accepted_types) in scalar_domains.items():
        values = raw.get(field)
        if not isinstance(values, list):
            continue
        known = [
            v
            for v in values
            if type(v) in accepted_types and (field != "supported_durations" or math.isfinite(v))
        ]
        for method, profile in profiles.items():
            if profile.get("state") != "SUPPORTED":
                continue
            control = profile.get("controls", {}).get(control_name, {})
            if control.get("state") != "SUPPORTED":
                continue
            projected = control.get("values")
            if not isinstance(projected, list):
                continue
            missing = [v for v in known if v not in projected]
            if missing:
                scoped_evidence = []
                for fact in model.evidence_facts:
                    method_contract = (
                        fact.value.get("methods", {}).get(method, {})
                        if isinstance(fact.value, dict)
                        else {}
                    )
                    scoped_control = method_contract.get("controls", {}).get(control_name, {})
                    if (
                        fact.key == REQUEST_SHAPES_KEY
                        and fact.authority == "REVIEWED_AUDIT_DISPOSITION"
                        and fact.state.value == "SUPPORTED"
                        and "Exact model" in fact.scope
                        and isinstance(scoped_control, dict)
                        and scoped_control.get("state") == "SUPPORTED"
                        and scoped_control.get("values")
                        and scoped_control.get("evidence_class") != "ABSENCE_ONLY"
                        and scoped_control.get("notes")
                    ):
                        scoped_evidence.append(scoped_control)
                reviewed_values = {
                    value
                    for item in scoped_evidence
                    for value in item.get("values", [])
                    if type(value) in accepted_types
                }
                confirmed_loss = [value for value in missing if value in reviewed_values]
                review_only = [value for value in missing if value not in reviewed_values]
                if confirmed_loss:
                    rows.append(
                        {
                            "path": f"methods.{method}.{control_name}.catalogue_domain",
                            "origin": "DERIVED_PROJECTION",
                            "disposition": "IMPLEMENTATION_GAP",
                            "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT",
                            "reason": (
                                "Exact reviewed method contract allows values absent from the "
                                "projection"
                            ),
                            "value": {
                                "catalogue_values": confirmed_loss,
                                "projected_values": projected,
                                "reviewed_values": sorted(reviewed_values),
                                "scope_notes": [item.get("notes") for item in scoped_evidence],
                            },
                        }
                    )
                if review_only and scoped_evidence:
                    rows.append(
                        {
                            "path": f"methods.{method}.{control_name}.catalogue_domain.review",
                            "origin": "DERIVED_PROJECTION",
                            "disposition": "EVIDENCE_GAP",
                            "classification": "CONTRACT_REVIEW_REQUIRED",
                            "reason": (
                                "Top-level values outside the exact reviewed method domain "
                                "remain unresolved"
                            ),
                            "value": {
                                "catalogue_values": review_only,
                                "projected_values": projected,
                                "reviewed_values": sorted(reviewed_values),
                                "scope_notes": [item.get("notes") for item in scoped_evidence],
                            },
                        }
                    )
                if not scoped_evidence:
                    rows.append(
                        {
                            "path": f"methods.{method}.{control_name}.catalogue_domain",
                            "origin": "DERIVED_PROJECTION",
                            "disposition": "IMPLEMENTATION_GAP",
                            "classification": "CAPABILITY_UNDEREXPOSURE_DEFECT",
                            "reason": (
                                "Known normalized catalogue values are absent without "
                                "affirmative scoped restriction evidence"
                            ),
                            "value": {"catalogue_values": missing, "projected_values": projected},
                        }
                    )
    allowed = raw.get("allowed_passthrough_parameters", [])
    if isinstance(allowed, list):
        for name in allowed:
            if not isinstance(name, str):
                continue
            methods = [
                m
                for m in executable
                if any(
                    name in specs
                    for specs in profiles[m]["controls"]
                    .get("provider_options", {})
                    .get("providers", {})
                    .values()
                )
            ]
            rows.append(
                {
                    "path": "provider_options." + name,
                    "disposition": "SUPPORTED_EXECUTABLE" if methods else "EVIDENCE_GAP",
                    "reason": "Typed validator/serializer and generic UI: "
                    + ", ".join(sorted(methods))
                    if methods
                    else "Allowlisted name lacks a complete type/domain/route/method contract",
                }
            )
    for method, profile in profiles.items():
        for item in input_constraint_reconciliation(model, method, profile):
            rows.append(
                {
                    "path": "methods." + method + ".constraints." + item["field"],
                    "disposition": "IMPLEMENTATION_GAP"
                    if item["classification"]
                    in {"CAPABILITY_UNDEREXPOSURE_DEFECT", "IMPLEMENTATION_GAP"}
                    else "CONTRACT_CONFLICT"
                    if item["classification"] == "CONTRACT_CONFLICT"
                    else "EVIDENCE_GAP"
                    if item["classification"] in {"MISSING_UPSTREAM_CONTRACT", "STALE_EVIDENCE"}
                    else "DISCOVERED_CONTRACT_COMPLETE",
                    "reason": item.get("reason", item["classification"]),
                    "classification": item["classification"],
                    "value": item,
                }
            )
        state = profile["state"]
        rows.append(
            {
                "path": "methods." + method,
                "disposition": "SUPPORTED_EXECUTABLE"
                if method in executable
                else "CONTRACT_CONFLICT"
                if state == "CONFLICT"
                else "VERIFIED_UNSUPPORTED"
                if state == "UNSUPPORTED"
                else "EVIDENCE_GAP",
                "reason": "Validated serializable request shape"
                if method in executable
                else "No complete compatible request shape; not offered as executable",
            }
        )
        for control, spec in profile.get("controls", {}).items():
            rows.append(
                {
                    "path": "methods." + method + "." + control,
                    "disposition": "SUPPORTED_EXECUTABLE"
                    if method in executable and spec.get("state") == "SUPPORTED"
                    else "CONTRACT_CONFLICT"
                    if spec.get("state") == "CONFLICT"
                    else "VERIFIED_UNSUPPORTED"
                    if spec.get("state") == "UNSUPPORTED"
                    else "EVIDENCE_GAP",
                    "value": spec,
                    "reason": "UI, validator and serializer share this exact Core profile",
                }
            )
    supplied = raw.get(REQUEST_SHAPES_KEY)
    if isinstance(supplied, dict) and isinstance(supplied.get("methods"), dict):
        for name in supplied["methods"]:
            if name not in profiles:
                rows.append(
                    {
                        "path": "methods." + str(name),
                        "disposition": "IMPLEMENTATION_GAP",
                        "reason": "Discovered operation lacks an existing execution primitive",
                    }
                )
    observation = next(
        (f for f in model.evidence_facts if f.key == "__catalogue_observation__"), None
    )
    for row in rows:
        row["upstream_observed_at"] = observation.observed_at if observation else None
        row["upstream_source"] = observation.source_reference if observation else None
        evidence_keys = {row["path"].split(".")[0]}
        if row["path"].startswith(("methods.", "provider_options.")):
            evidence_keys = {
                REQUEST_SHAPES_KEY,
                "reference_kinds",
                "max_reference_count",
                "mixed_reference_kinds",
                "supported_frame_images",
                "supports_text_only",
                "allowed_passthrough_parameters",
            }
        row["evidence"] = [
            {
                "key": f.key,
                "state": f.state.value,
                "authority": f.authority,
                "source": f.source_reference,
                "observed_at": f.observed_at,
                "scope": f.scope,
            }
            for f in model.evidence_facts
            if f.key in evidence_keys
        ]
        row["execution_authority"] = row["disposition"] == "SUPPORTED_EXECUTABLE"
        row.setdefault("origin", "DERIVED_PROJECTION")
        row["core_projection"] = row["path"]
        row["ui_representation"] = (
            "Generic method/control projection and Settings accounting"
            if row["execution_authority"]
            else "Settings accounting only"
        )
        row["validator_serializer"] = (
            "Core profile, validated request witness, canonical serializer"
            if row["execution_authority"]
            else "NOT_EXECUTABLE"
        )
    return {
        "model_id": model.model_id,
        "rows": rows,
        "discovered_field_count": len(raw),
        "accounted_field_count": len(raw),
        "executable_methods": sorted(executable),
        "semantic_fingerprint": semantic_fingerprint(raw),
    }


def capability_completeness_report(models: tuple[ModelCapabilities, ...]) -> dict[str, Any]:
    """Account for discoveries separately from executable coverage, without granting support."""
    reports = [capability_completeness(model) for model in sorted(models, key=lambda m: m.model_id)]
    counts: dict[str, int] = {}
    projection_counts: dict[str, int] = {}
    for report in reports:
        for row in report["rows"]:
            state = row["disposition"]
            bucket = counts if row["origin"] == "UPSTREAM_FIELD" else projection_counts
            bucket[state] = bucket.get(state, 0) + 1
    return {
        "schema_version": 1,
        "models": reports,
        "dispositions": counts,
        "projection_dispositions": projection_counts,
        "discovered_model_count": len(models),
        "discovered_field_count": sum(r["discovered_field_count"] for r in reports),
        "accounted_field_count": sum(r["accounted_field_count"] for r in reports),
        "executable_method_count": sum(len(r["executable_methods"]) for r in reports),
        "accounting_is_execution_proof": False,
        "underexposure_defect_count": sum(
            row.get("classification") == "CAPABILITY_UNDEREXPOSURE_DEFECT"
            for report in reports
            for row in report["rows"]
        ),
    }


def capability_evolution(
    previous: tuple[ModelCapabilities, ...], current: tuple[ModelCapabilities, ...]
) -> dict[str, Any]:
    """Persist the same derived accounting that the UI uses alongside fresh discovery."""
    result = capability_changes(previous, current)
    before = {
        m.model_id: {v.value for v in eligible_methods(enrich_capabilities(m))} for m in previous
    }
    effective = tuple(enrich_capabilities(m) for m in current)
    after = {m.model_id: {v.value for v in eligible_methods(m)} for m in effective}
    result["method_changes"] = [
        {
            "model_id": mid,
            "method": method,
            "change": "ACTIVATED" if method in after.get(mid, set()) else "REMOVED_OR_CHANGED",
        }
        for mid in sorted(before.keys() | after.keys())
        for method in sorted(before.get(mid, set()) ^ after.get(mid, set()))
    ]

    def executable_controls(
        models: tuple[ModelCapabilities, ...],
    ) -> dict[tuple[str, str, str], Any]:
        return {
            (model.model_id, method.value, control): spec
            for model in models
            for method in eligible_methods(model)
            for control, spec in project_method(model, method.value)["controls"].items()
            if spec.get("state") == "SUPPORTED"
        }

    prior_controls = executable_controls(tuple(enrich_capabilities(m) for m in previous))
    next_controls = executable_controls(effective)
    result["control_changes"] = [
        {
            "model_id": key[0],
            "method": key[1],
            "control": key[2],
            "change": "ACTIVATED"
            if key not in prior_controls
            else "REMOVED_OR_CHANGED"
            if key not in next_controls
            else "VALUE_CHANGED",
        }
        for key in sorted(prior_controls.keys() | next_controls.keys())
        if key not in prior_controls
        or key not in next_controls
        or semantic_fingerprint(prior_controls[key]) != semantic_fingerprint(next_controls[key])
    ]
    result["completeness"] = capability_completeness_report(effective)
    return result


def _retryable_discovery(error: BaseException) -> bool:
    if isinstance(error, TransportError):
        return True
    return isinstance(error, OpenRouterHTTPError) and (
        error.status_code in {408, 429} or 500 <= error.status_code <= 599
    )


class RequestValidator:
    """Validate frozen request semantics before acquiring a paid-submit right."""

    __slots__ = ()

    def validate_shape(self, request: GenerationRequest) -> None:
        """Validate model-independent request invariants without persisting content."""

        if not request.model or request.model != request.model.strip():
            self._fail(ProductErrorCode.UNSUPPORTED_MODEL, "A valid video model is required.")
        if not isinstance(request.inference_method, InferenceMethod):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "A supported inference method is required.",
            )
        references = request.input_references.references if request.input_references else ()
        if request.prompt is not None and not isinstance(request.prompt, str):
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "Prompt must be text.")
        prompt_optional_method = request.inference_method in {
            InferenceMethod.I2V,
            InferenceMethod.FLF2V,
            InferenceMethod.V2V_UPSCALE,
            InferenceMethod.AVATAR_AUDIO,
        }
        if not prompt_optional_method and not (request.prompt and request.prompt.strip()):
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "A non-empty prompt is required.")
        if request.prompt is not None and not request.prompt.strip():
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "Prompt must not be blank.")
        if request.duration is not None and (
            isinstance(request.duration, bool) or (request.duration < 1 and request.duration != -1)
        ):
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "Duration must be positive.")
        if request.seed is not None and isinstance(request.seed, bool):
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "Seed must be an integer.")
        for value in (request.resolution, request.aspect_ratio, request.size):
            if value is not None and (not value or value != value.strip()):
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "Generation options must use canonical non-empty values.",
                )
        if request.size is not None and (
            request.resolution is not None or request.aspect_ratio is not None
        ):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Exact size cannot be combined with resolution or aspect ratio.",
            )
        if request.size is not None and not _SIZE_PATTERN.fullmatch(request.size):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Exact size must use WIDTHxHEIGHT format.",
            )
        self._validate_frame(request.first_frame, FrameType.FIRST)
        self._validate_frame(request.last_frame, FrameType.LAST)
        if request.source_video is not None:
            self._validate_reference(request.source_video)
            if request.source_video.kind is not InputReferenceKind.VIDEO:
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "Source Video must be a VIDEO reference.",
                )
        for reference in references:
            self._validate_reference(reference)
        self._validate_topology(request, references)
        self._validate_specialized_fields(request)

    def validate_capabilities(
        self, request: GenerationRequest, capabilities: ModelCapabilities
    ) -> None:
        """Reject explicit unsupported intent without silent substitution or removal."""

        if request.model not in {capabilities.model_id, capabilities.canonical_slug}:
            self._fail(ProductErrorCode.UNSUPPORTED_MODEL, "The selected model does not match.")
        scoped = None
        if any(
            f.key
            in {REQUEST_SHAPES_KEY, "per_kind_max", "per_kind_min", "__catalogue_observation__"}
            for f in capabilities.evidence_facts
        ):
            scoped = project_method(capabilities, request.inference_method.value)
            raw = {
                name: getattr(request, name)
                for name in (
                    "prompt",
                    "duration",
                    "resolution",
                    "aspect_ratio",
                    "size",
                    "seed",
                    "generate_audio",
                    "first_frame",
                    "last_frame",
                    "source_video",
                    "input_references",
                    "previous_job_id",
                    "upscale_factor",
                    "creativity",
                    "provider_options",
                )
            }
            try:
                projected = project_semantic_values(
                    capabilities, request.inference_method.value, raw
                )
            except ValueError:
                self._fail(
                    ProductErrorCode.CAPABILITY_SIGNAL_GAP, "Method is not publicly supported."
                )
            if any(
                projected.get(name, () if name == "provider_options" else None) != value
                for name, value in raw.items()
                if not (
                    name == "generate_audio"
                    and value is False
                    and capabilities.generate_audio is not True
                )
            ):
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER, "Request contains nonprojected state."
                )
            kinds = (
                tuple(r.kind.value for r in request.input_references.references)
                if request.input_references
                else ()
            )
            if not projected_shape_valid(scoped, kinds, request.source_video is not None):
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "Reference combination is not supported.",
                )
            controls = scoped["controls"]
            if request.prompt is None and controls.get("prompt", {}).get("required", True):
                self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "This method requires a prompt.")
            if request.prompt is not None:
                bounds = controls.get("prompt", {})
                if len(request.prompt) < bounds.get("min_length", 0) or len(
                    request.prompt
                ) > bounds.get("max_length", math.inf):
                    self._fail(
                        ProductErrorCode.UNSUPPORTED_PARAMETER,
                        "Prompt length exceeds the documented method bounds.",
                    )
            specialized_values = {
                "upscale_factor": request.upscale_factor,
                "creativity": request.creativity,
                "previous_job_id": request.previous_job_id,
                "provider_options": request.provider_options,
            }
            for name, value in specialized_values.items():
                control = controls.get(name, {})
                absent = not value if name == "provider_options" else value is None
                if absent and control.get("required", False):
                    self._fail(
                        ProductErrorCode.UNSUPPORTED_PARAMETER,
                        f"{name} is required by this method.",
                    )
            for name, value in (
                ("upscale_factor", request.upscale_factor),
                ("creativity", request.creativity),
                ("previous_job_id", request.previous_job_id),
                ("provider_options", request.provider_options),
            ):
                control = controls.get(name, {"state": "UNKNOWN"})
                has_value = bool(value) if name == "provider_options" else value is not None
                if has_value and control.get("state") != "SUPPORTED":
                    self._fail(
                        ProductErrorCode.UNSUPPORTED_PARAMETER,
                        f"{name} is not supported by this method.",
                    )
                if name == "upscale_factor" and value is not None:
                    bounds = control.get("number_range", {})
                    if value < bounds.get("min", float("inf")) or value > bounds.get(
                        "max", float("-inf")
                    ):
                        self._fail(
                            ProductErrorCode.UNSUPPORTED_PARAMETER,
                            f"{name} is outside the reviewed range.",
                        )
        if (
            scoped is None
            and request.prompt is None
            and request.inference_method
            in {
                InferenceMethod.I2V,
                InferenceMethod.FLF2V,
            }
        ):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER, "Unreviewed image methods require a prompt."
            )
        if scoped is None and (
            request.previous_job_id is not None
            or request.upscale_factor is not None
            or request.creativity is not None
            or request.provider_options
        ):
            self._fail(
                ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                "Specialized controls require a reviewed exact-model profile.",
            )
        self._supported(
            request.duration,
            capabilities.supported_durations,
            "duration",
        )
        self._supported(
            request.resolution,
            capabilities.supported_resolutions,
            "resolution",
        )
        self._supported(
            request.aspect_ratio,
            capabilities.supported_aspect_ratios,
            "aspect ratio",
        )
        self._supported(request.size, capabilities.supported_sizes, "size")
        if CONFIGURATION_KEY in capabilities.unmapped_capability_keys:
            self._fail(
                ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                "UNMAPPED_UPSTREAM_CAPABILITY: configuration constraints require review.",
            )
        references_for_config = (
            request.input_references.references if request.input_references else ()
        )
        config_status = configuration_status(
            tuple(scoped["configuration_relations"])
            if scoped
            else profile_constraints(capabilities),
            {
                "duration": request.duration,
                "resolution": request.resolution,
                "aspect_ratio": request.aspect_ratio,
                "size": request.size,
            },
            {
                "geometry_authority": "EXACT" if request.size is not None else "NORMALIZED",
                "inference_method": request.inference_method.value,
                "generate_audio": request.generate_audio,
                "reference_count": len(references_for_config) + (request.source_video is not None),
                "reference_kinds": tuple(r.kind.value for r in references_for_config)
                + ((request.source_video.kind.value,) if request.source_video is not None else ()),
                "source_video_present": request.source_video is not None,
            },
        )
        if config_status != "READY":
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER
                if config_status == "CONFIRMED_INCOMPATIBLE"
                else ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                f"{config_status}: configuration violates or lacks known coupling evidence.",
            )
        if request.seed is not None and capabilities.supports_seed is not True:
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Seed is not positively supported by this model.",
            )
        if request.generate_audio and capabilities.generate_audio is not True:
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Generated audio is not positively supported by this model.",
            )
        if request.first_frame is not None and (
            capabilities.supported_frame_types is None
            or FrameType.FIRST not in capabilities.supported_frame_types
        ):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "First-frame guidance is not positively supported by this model.",
            )
        if request.last_frame is not None and (
            capabilities.supported_frame_types is None
            or FrameType.LAST not in capabilities.supported_frame_types
        ):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Last-frame guidance is not positively supported by this model.",
            )
        references = request.input_references.references if request.input_references else ()
        matrix = inference_method_matrix(capabilities)
        status = matrix[request.inference_method]
        if status is not CapabilityModeStatus.READY:
            self._fail(
                ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                f"{request.inference_method.value} is blocked because runtime capability "
                f"evidence is {status.value}.",
            )
        total_reference_count = len(references) + (request.source_video is not None)
        if total_reference_count and scoped is None:
            reference_capabilities = capabilities.input_reference_capabilities
            if (
                reference_capabilities is not None
                and reference_capabilities.max_reference_count is not None
                and total_reference_count > reference_capabilities.max_reference_count
            ):
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "The input reference collection exceeds the proven model limit.",
                )
        if total_reference_count:
            direct_cap = next(
                (
                    f.value
                    for f in capabilities.evidence_facts
                    if f.key == "max_reference_count"
                    and f.authority == "LIVE_STRUCTURED_API"
                    and type(f.value) is int
                    and f.state.value == "SUPPORTED"
                ),
                None,
            )
            if direct_cap is not None and total_reference_count > direct_cap:
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "Input references exceed confirmed transport capacity.",
                )

    def prepare_native_media(
        self, request: GenerationRequest, capabilities: ModelCapabilities
    ) -> GenerationRequest:
        """Bind reviewed media limits to deferred encoders without reading media here."""
        limits = project_method(capabilities, request.inference_method.value).get(
            "media_limits", {}
        )
        if not limits:
            return request

        references = ([request.source_video] if request.source_video is not None else []) + list(
            request.input_references.references if request.input_references else ()
        )
        combined_checks: dict[InputReferenceKind, Callable[[], None]] = {}
        for kind in (InputReferenceKind.VIDEO, InputReferenceKind.AUDIO):
            rule = limits.get(kind.value, {})
            combined = rule.get("max_combined_duration_seconds")
            combined_with_output = rule.get("max_combined_input_output_duration_seconds")
            if combined_with_output is not None:
                # An omitted output duration is chosen upstream, not guessed here.
                output_duration = request.duration
                if output_duration is not None and output_duration > 0:
                    remaining = combined_with_output - output_duration
                    combined = remaining if combined is None else min(combined, remaining)
            if combined is not None:
                group = [item for item in references if item.kind is kind]
                if not group:
                    continue
                if any(item.local_media is None for item in group):
                    self._fail(
                        ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                        "Combined reference duration cannot be verified for external media.",
                    )

                def check_duration(
                    group: tuple[InputReference, ...] = tuple(group), cap: float = float(combined)
                ) -> None:
                    total = 0.0
                    for item in group:
                        source = item.local_media
                        if source is None or source.duration is None:
                            raise NativeMediaError(
                                "Combined reference duration could not be verified."
                            )
                        value = source.duration()
                        if not math.isfinite(value) or value <= 0:
                            raise NativeMediaError(
                                "Combined reference duration could not be verified."
                            )
                        total += value
                    if total > cap:
                        raise NativeMediaError(
                            "Combined reference duration exceeds the selected method's limit."
                        )

                combined_checks[kind] = check_duration

        metadata_keys = {
            "max_bytes",
            "min_width",
            "max_width",
            "min_height",
            "max_height",
            "min_pixels",
            "max_pixels",
        }

        def check_image(url: str, role: str) -> None:
            rule = {**limits.get("image", {}), **limits.get(role, {})}
            if not metadata_keys.intersection(rule):
                return
            metadata = image_data_url_metadata(url)
            if metadata is None:
                self._fail(
                    ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                    "Image metadata cannot be verified for the selected method.",
                )
            byte_size, width, height = metadata
            pixels = width * height
            if (
                ("max_bytes" in rule and byte_size > rule["max_bytes"])
                or ("min_width" in rule and width < rule["min_width"])
                or ("max_width" in rule and width > rule["max_width"])
                or ("min_height" in rule and height < rule["min_height"])
                or ("max_height" in rule and height > rule["max_height"])
                or ("min_pixels" in rule and pixels < rule["min_pixels"])
                or ("max_pixels" in rule and pixels > rule["max_pixels"])
            ):
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "Image exceeds the selected method's size or geometry limits.",
                )

        def constrained(
            reference: InputReference | None, role: str | None = None
        ) -> InputReference | None:
            if reference is None:
                return reference
            rule = {
                **limits.get(reference.kind.value, {}),
                **limits.get(role or reference.kind.value, {}),
            }
            if reference.kind is InputReferenceKind.IMAGE:
                check_image(reference.url, role or reference.kind.value)
                return reference
            if reference.local_media is None:
                if any(
                    key in rule
                    for key in (
                        "max_duration_seconds",
                        "min_duration_seconds",
                        "max_bytes",
                        "max_total_duration_seconds",
                        "max_combined_duration_seconds",
                        "max_combined_input_output_duration_seconds",
                        "min_width",
                        "max_width",
                        "min_height",
                        "max_height",
                        "min_pixels",
                        "max_pixels",
                    )
                ):
                    self._fail(
                        ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                        "Media metadata cannot be verified for the selected method.",
                    )
                return reference
            media = reference.local_media
            max_bytes = min(media.max_bytes, int(rule.get("max_bytes", media.max_bytes)))
            durations = [
                v
                for v in (media.max_duration_seconds, rule.get("max_duration_seconds"))
                if v is not None
            ]
            if "max_total_duration_seconds" in rule:
                # An omitted duration delegates to the provider. Reserve the
                # greatest confirmed output duration rather than guessing its default.
                outputs = project_method(capabilities, request.inference_method.value)["controls"][
                    "duration"
                ].get("values", [])
                output_duration = request.duration or max(outputs, default=0)
                if output_duration <= 0:
                    self._fail(
                        ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                        "Extension duration cannot be verified before submit.",
                    )
                durations.append(rule["max_total_duration_seconds"] - output_duration)
            geometry_rules = {
                key: rule[key]
                for key in (
                    "min_width",
                    "max_width",
                    "min_height",
                    "max_height",
                    "min_pixels",
                    "max_pixels",
                )
                if key in rule
            }
            return replace(
                reference,
                local_media=replace(
                    media,
                    max_bytes=max_bytes,
                    max_duration_seconds=min(durations) if durations else None,
                    min_duration_seconds=max(
                        media.min_duration_seconds or 0, rule.get("min_duration_seconds", 0)
                    )
                    or None,
                    **geometry_rules,
                    combined_duration_check=combined_checks.get(reference.kind),
                ),
            )

        if request.first_frame is not None:
            check_image(request.first_frame.url, "first_frame")
        if request.last_frame is not None:
            check_image(request.last_frame.url, "last_frame")
        refs = request.input_references
        return replace(
            request,
            first_frame=request.first_frame,
            last_frame=request.last_frame,
            source_video=constrained(request.source_video, "source_video"),
            input_references=InputReferenceCollection(
                tuple(
                    item
                    for reference in refs.references
                    if (item := constrained(reference)) is not None
                )
            )
            if refs
            else None,
        )

    @staticmethod
    def _supported(value: object | None, supported: tuple[object, ...] | None, name: str) -> None:
        if value is not None and supported is not None and value not in supported:
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                f"The selected {name} is not supported by this model.",
            )

    @staticmethod
    def _validate_frame(frame: FrameReference | None, expected: FrameType) -> None:
        if frame is None:
            return
        if frame.frame_type is not expected or not _is_image_source(frame.url):
            RequestValidator._fail(
                ProductErrorCode.INVALID_MEDIA_URL,
                "Frame images require a valid IMAGE source.",
            )

    @staticmethod
    def _validate_reference(reference: InputReference) -> None:
        if not isinstance(reference, InputReference) or not isinstance(
            reference.kind, InputReferenceKind
        ):
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Input references require a supported typed media kind.",
            )
        if reference.local_media is not None:
            expected = {
                InputReferenceKind.VIDEO: ("video/mp4", ".mp4"),
                InputReferenceKind.AUDIO: ("audio/wav", ".wav"),
            }.get(reference.kind)
            if reference.url or expected != (
                reference.local_media.content_type,
                reference.local_media.suffix,
            ):
                RequestValidator._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER, "Invalid native media reference."
                )
            return
        if reference.kind is InputReferenceKind.IMAGE and not _is_image_source(reference.url):
            RequestValidator._fail(
                ProductErrorCode.INVALID_MEDIA_URL,
                "IMAGE references require a public HTTPS URL or valid PNG data URL.",
            )
        if reference.kind is not InputReferenceKind.IMAGE and not _is_public_https_url(
            reference.url
        ):
            RequestValidator._fail(
                ProductErrorCode.INVALID_MEDIA_URL,
                "Input references require a direct public HTTPS URL.",
            )

    @staticmethod
    def _validate_specialized_fields(request: GenerationRequest) -> None:
        if request.upscale_factor is not None and (
            type(request.upscale_factor) not in (int, float)
            or not math.isfinite(request.upscale_factor)
            or request.upscale_factor <= 0
        ):
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Upscale factor must be a positive finite number.",
            )
        if request.creativity is not None and (type(request.creativity) is not int):
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER, "Creativity must be an integer."
            )
        if (
            request.previous_job_id is not None
            and re.fullmatch(r"gen-vid-\d+-[0-9A-Za-z]{20}", request.previous_job_id) is None
        ):
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER, "Previous job identifier is malformed."
            )
        if request.inference_method is InferenceMethod.V2V_UPSCALE:
            if request.source_video is None or request.input_references is not None:
                RequestValidator._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "V2V upscale requires exactly one source video.",
                )
        elif request.upscale_factor is not None or request.creativity is not None:
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Upscale controls require V2V upscale intent.",
            )

    @staticmethod
    def _validate_topology(
        request: GenerationRequest, references: tuple[InputReference, ...]
    ) -> None:
        method = request.inference_method
        has_first = request.first_frame is not None
        has_last = request.last_frame is not None
        has_source = request.source_video is not None
        kinds = tuple(reference.kind for reference in references)

        if method is InferenceMethod.T2V:
            valid = not has_first and not has_last and not has_source and not references
        elif method is InferenceMethod.I2V:
            valid = has_first and not has_last and not has_source and not references
        elif method is InferenceMethod.FLF2V:
            valid = has_first and has_last and not has_source and not references
        elif method is InferenceMethod.IR2V:
            valid = (
                not has_first
                and not has_last
                and not has_source
                and kinds == (InputReferenceKind.IMAGE,)
            )
        elif method is InferenceMethod.MI2V:
            valid = (
                not has_first
                and not has_last
                and not has_source
                and len(kinds) >= 2
                and set(kinds) == {InputReferenceKind.IMAGE}
            )
        elif method is InferenceMethod.VR2V:
            valid = (
                not has_first
                and not has_last
                and not has_source
                and len(kinds) >= 1
                and set(kinds) == {InputReferenceKind.VIDEO}
            )
        elif method is InferenceMethod.AR2V:
            valid = (
                not has_first
                and not has_last
                and not has_source
                and len(kinds) >= 1
                and set(kinds) == {InputReferenceKind.AUDIO}
            )
        elif method is InferenceMethod.MMR2V:
            valid = (
                not has_first
                and not has_last
                and not has_source
                and len(kinds) >= 2
                and len(set(kinds)) >= 2
            )
        elif method in {
            InferenceMethod.V2V_EDIT,
            InferenceMethod.V2V_EXTEND,
            InferenceMethod.V2V_UPSCALE,
        }:
            continuation = request.previous_job_id is not None
            valid = (
                not has_first
                and not has_last
                and (has_source != continuation)
                and (method is not InferenceMethod.V2V_UPSCALE or not continuation)
            )
        elif method is InferenceMethod.AVATAR_AUDIO:
            valid = (
                not has_first
                and not has_last
                and not has_source
                and kinds.count(InputReferenceKind.IMAGE) == 1
                and kinds.count(InputReferenceKind.AUDIO) == 1
                and len(kinds) == 2
            )
        else:  # pragma: no cover - exhaustive guard for future enum additions
            valid = False
        if not valid:
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                f"The connected media topology does not match {method.value}.",
            )

    @staticmethod
    def _fail(code: ProductErrorCode, message: str) -> NoReturn:
        raise ProductFailureError(ProductError(code, message, BillingContext.NO_SUBMIT))


def _is_image_source(value: str) -> bool:
    return _is_public_https_url(value) or is_supported_image_data_url(value)


def _is_public_https_url(value: str) -> bool:
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    lowered = host.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith(
        (".localhost", ".local", ".internal", ".home.arpa")
    ):
        return False
    try:
        address = ipaddress.ip_address(lowered)
    except ValueError:
        return "." in lowered
    return address.is_global


__all__ = (
    "CapabilityModeStatus",
    "CapabilityObservation",
    "CapabilityService",
    "FRESH_TTL",
    "InferenceMethod",
    "LKG_TTL",
    "RequestValidator",
    "inference_method_matrix",
    "infer_legacy_inference_method",
    "mode_enforcement_matrix",
)


def request_witness(model: ModelCapabilities, method: InferenceMethod) -> GenerationRequest | None:
    """Return one valid serializable shape, with a bounded fail-closed search."""
    profile = project_method(model, method.value)
    if profile["state"] != "SUPPORTED":
        return None
    controls, topology = profile["controls"], profile["topology"]
    prompt_control = controls.get("prompt", {})
    if prompt_control.get("state") != "SUPPORTED" and prompt_control.get("required", True):
        return None
    domains: dict[str, list[Any]] = {}
    for name in ("duration", "resolution", "aspect_ratio", "size"):
        control = controls.get(name, {})
        domains[name] = (
            control.get("values", [None]) if control.get("state") == "SUPPORTED" else [None]
        )
    references: list[tuple[str, ...]] = [
        tuple(kind for kind, count in configuration.items() for _ in range(count))
        for configuration in topology.get("verified_configurations", [])
        if sum(configuration.values()) <= 1000
    ]
    for kinds in topology["kind_sets"]:
        # Bound witness construction work, not the advertised model capacity.
        if (
            max(
                topology["min"],
                sum(max(1, topology.get("per_kind_min", {}).get(k, 0)) for k in kinds),
            )
            > 1000
        ):
            continue
        minimum_shape = [
            kind
            for kind in kinds
            for _ in range(max(1, topology.get("per_kind_min", {}).get(kind, 0)))
        ]
        while minimum_shape and len(minimum_shape) < topology["min"]:
            available = [
                k
                for k in kinds
                if minimum_shape.count(k) < topology["per_kind_max"].get(k, topology["min"])
            ]
            if not available:
                break
            minimum_shape.append(available[0])
        if projected_shape_valid(profile, tuple(minimum_shape)):
            references.append(tuple(minimum_shape))
        for count in range(topology["min"], max(topology["min"], len(kinds)) + 1):
            if not kinds and count:
                continue
            shape = tuple(kinds[i % len(kinds)] for i in range(count))
            if projected_shape_valid(profile, shape):
                references.append(shape)
    fixed = topology["fixed"]
    scalar_controls = controls
    upscale_factor = None
    if scalar_controls.get("upscale_factor", {}).get("state") == "SUPPORTED":
        upscale_factor = scalar_controls["upscale_factor"].get("number_range", {}).get("min")
    creativity = None
    if scalar_controls.get("creativity", {}).get("state") == "SUPPORTED":
        creativity = scalar_controls["creativity"].get("values", [0])[0]
    seed = None
    seed_control = scalar_controls.get("seed", {})
    if seed_control.get("state") == "SUPPORTED":
        seed = seed_control.get("integer_range", {}).get("min", 0)
    previous_job_id = None
    previous_control = scalar_controls.get("previous_job_id", {})
    if previous_control.get("state") == "SUPPORTED" and (
        previous_control.get("required") is True
        or (
            topology.get("source_alternative") == "previous_job_id"
            and (
                topology.get("transport_max") == 0
                or topology.get("transport_per_kind_max", {}).get("video") == 0
            )
        )
    ):
        previous_job_id = "gen-vid-1234567890-12345678901234567890"
    provider_options: tuple[ProviderOption, ...] = ()
    option_control = scalar_controls.get("provider_options", {})
    if option_control.get("state") == "SUPPORTED":
        schemas = option_control.get("providers", {})
        for provider, schema in schemas.items():
            if not isinstance(schema, dict):
                continue
            for key, spec in schema.items():
                if not isinstance(spec, dict):
                    continue
                if not spec.get("required") and not option_control.get("required"):
                    continue
                value = spec.get("values", [None])[0]
                if value is None:
                    value = (
                        "TEST_ONLY_REQUIRED_VALUE"
                        if spec.get("type") == "string"
                        else spec.get("min", False if spec.get("type") == "boolean" else 0)
                    )
                provider_options += (ProviderOption(provider, key, value, spec.get("container")),)
    validator = RequestValidator()
    for geometry in ("NORMALIZED", "EXACT"):
        for values in islice(product(*domains.values(), references), 4096):
            duration, resolution, aspect, size, kinds = values
            request = GenerationRequest(
                model.model_id,
                None
                if prompt_control.get("required", True) is False
                else "Local request shape validation",
                method,
                duration=duration,
                resolution=resolution if geometry == "NORMALIZED" else None,
                aspect_ratio=aspect if geometry == "NORMALIZED" else None,
                size=size if geometry == "EXACT" else None,
                generate_audio=False
                if controls.get("generate_audio", {}).get("state") == "SUPPORTED"
                else None,
                seed=seed,
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
                upscale_factor=upscale_factor,
                creativity=creativity,
                previous_job_id=previous_job_id,
                provider_options=provider_options,
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
