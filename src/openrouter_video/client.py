"""Typed OpenRouter Video client behind the canonical request policy."""

from __future__ import annotations

import json
import math
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from openrouter_video.configuration import (
    CONFIGURATION_KEY,
    REQUEST_SHAPES_KEY,
    finite_domain,
    normalize_constraints,
    normalize_request_shapes,
)
from openrouter_video.errors import MalformedOpenRouterResponseError, OpenRouterHTTPError
from openrouter_video.models import (
    CapabilityEvidenceSource,
    CapabilityFact,
    CapabilityFactState,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReferenceCapabilities,
    InputReferenceKind,
    ModelCapabilities,
    PricingEvidence,
    PricingSku,
    RemoteJobSnapshot,
    UsageCost,
)
from openrouter_video.policy import Operation
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport


class DiscoveryClient(Protocol):
    """Read-only model-catalog capability."""

    async def list_video_models(self) -> tuple[ModelCapabilities, ...]: ...


class SubmitClient(Protocol):
    """Paid-submit capability supplied only to GenerateService."""

    async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot: ...


class ObservationClient(Protocol):
    """Read-only asynchronous job observation capability."""

    async def get_job(self, job_id: str) -> RemoteJobSnapshot: ...


class ContentClient(Protocol):
    """Read-only canonical content-stream capability."""

    def stream_content(self, job_id: str) -> AbstractAsyncContextManager[httpx.Response]: ...


class OpenRouterVideoClient:
    """Exact endpoint client with no destination, header, or credential escape hatches."""

    __slots__ = ("_request_policy", "_transport")

    def __init__(
        self,
        *,
        request_policy: OpenRouterRequestPolicy,
        transport: HttpxTransport,
    ) -> None:
        self._request_policy = request_policy
        self._transport = transport

    async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
        """Fetch and normalize the dedicated Video model catalog."""

        prepared = self._request_policy.prepare(Operation.DISCOVERY)
        response = await self._transport.send(prepared)
        _require_status(response, Operation.DISCOVERY, {200})
        body = _json_object(response)
        data = body.get("data")
        if not isinstance(data, list):
            raise MalformedOpenRouterResponseError("Video model catalog is malformed")
        return tuple(_parse_capability(item) for item in data if isinstance(item, Mapping))

    async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot:
        """Perform exactly one transport-level generation submit attempt."""

        prepared = self._request_policy.prepare(
            Operation.SUBMIT, json_body=request.to_openrouter_payload()
        )
        response = await self._transport.send(prepared)
        _require_status(response, Operation.SUBMIT, {200, 202})
        return _parse_job(_json_object(response))

    async def get_job(self, job_id: str) -> RemoteJobSnapshot:
        """Observe one trusted job identity through the reconstructed canonical path."""

        prepared = self._request_policy.prepare(Operation.POLL, job_id=job_id)
        response = await self._transport.send(prepared)
        _require_status(response, Operation.POLL, {200})
        snapshot = _parse_job(_json_object(response))
        if snapshot.job_id != job_id:
            raise MalformedOpenRouterResponseError("OpenRouter job identity changed")
        return snapshot

    @asynccontextmanager
    async def stream_content(self, job_id: str) -> AsyncIterator[httpx.Response]:
        """Stream index zero only from the canonical authenticated content endpoint."""

        prepared = self._request_policy.prepare(Operation.CONTENT, job_id=job_id)
        async with self._transport.stream(prepared) as response:
            _require_status(response, Operation.CONTENT, {200})
            yield response


def _require_status(response: httpx.Response, operation: Operation, allowed: set[int]) -> None:
    if response.status_code not in allowed:
        retry_after: float | None = None
        raw_retry_after = response.headers.get("Retry-After")
        if raw_retry_after is not None:
            try:
                parsed_retry_after = float(raw_retry_after)
            except ValueError:
                pass
            else:
                if 0 <= parsed_retry_after <= 60:
                    retry_after = parsed_retry_after
        raise OpenRouterHTTPError(
            response.status_code,
            operation,
            retry_after_seconds=retry_after,
        )


def _json_object(response: httpx.Response) -> Mapping[str, Any]:
    try:
        value = json.loads(response.content, parse_float=Decimal)
    except (json.JSONDecodeError, UnicodeError):
        raise MalformedOpenRouterResponseError("OpenRouter JSON response is malformed") from None
    if not isinstance(value, Mapping):
        raise MalformedOpenRouterResponseError("OpenRouter JSON response is malformed")
    return value


def _safe_required_text(value: object, label: str, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise MalformedOpenRouterResponseError(f"OpenRouter {label} is malformed")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise MalformedOpenRouterResponseError(f"OpenRouter {label} is malformed")
    return normalized


def _optional_text(value: object, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    try:
        return _safe_required_text(value, "text field", maximum=maximum)
    except MalformedOpenRouterResponseError:
        return None


def _optional_string_tuple(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    result = tuple(item for item in value if isinstance(item, str) and item)
    return result if len(result) == len(value) else None


def _optional_int_tuple(value: object) -> tuple[int, ...] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            return tuple(finite_domain(value, numeric=True))
        except ValueError:
            return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    result = tuple(item for item in value if isinstance(item, int) and not isinstance(item, bool))
    return result if len(result) == len(value) else None


def bounded_catalogue_metadata(value: dict[Any, Any]) -> dict[str, Any]:
    """Retain public discovery evidence; every bound/redaction has an explicit marker."""
    remaining = [4096]
    sensitive = re.compile(
        r"api[_-]?key|(?:access|refresh)[_-]?token|authorization|password|secret|"
        r"cookies?|credentials?|headers|email|(?:user|account|session)[_-]?id",
        re.I,
    )

    def safe(raw: object, depth: int = 0) -> Any:
        remaining[0] -= 1
        if depth > 24 or remaining[0] < 0:
            return {"discovery_omitted": "STRUCTURE_BOUND"}
        if raw is None or type(raw) in (bool, int):
            return raw
        if isinstance(raw, float):
            return raw if math.isfinite(raw) else {"discovery_omitted": "NONFINITE"}
        if isinstance(raw, Decimal):
            if not raw.is_finite():
                return {"discovery_omitted": "NONFINITE"}
            number = float(raw)
            return (
                number
                if math.isfinite(number) and Decimal(str(number)) == raw
                else {"discovery_number": str(raw), "representation": "EXACT_DECIMAL"}
            )
        if isinstance(raw, str):
            if re.search(r"sk-or-|Bearer\s|PRIVATE KEY|[?&](?:key|token|signature)=", raw, re.I):
                return {"discovery_omitted": "SENSITIVE_VALUE"}
            if len(raw) > 2048 or any(ord(c) < 32 and c not in "\n\t\r" for c in raw):
                return {"discovery_omitted": "TEXT_BOUND", "length": len(raw)}
            return raw
        if isinstance(raw, list):
            result = [safe(v, depth + 1) for v in raw[:256]]
            if len(raw) > 256:
                result.append({"discovery_omitted": "ARRAY_BOUND", "count": len(raw) - 256})
            return result
        if isinstance(raw, dict):
            result_dict: dict[str, Any] = {}
            for k, v in list(raw.items())[:256]:
                if not isinstance(k, str) or len(k) > 128 or any(ord(c) < 32 for c in k):
                    result_dict["__invalid_key__"] = {"discovery_omitted": "KEY_BOUND"}
                    continue
                result_dict[k] = (
                    {"discovery_omitted": "SENSITIVE_FIELD"}
                    if sensitive.fullmatch(k)
                    else safe(v, depth + 1)
                )
            if len(raw) > 256:
                result_dict["__remaining_fields__"] = {
                    "discovery_omitted": "FIELD_BOUND",
                    "count": len(raw) - 256,
                }
            return result_dict
        return {"discovery_omitted": "NON_JSON_TYPE"}

    return dict(safe(value))


def _parse_capability(value: Mapping[Any, Any]) -> ModelCapabilities:
    pricing_evidence = _parse_pricing_evidence(value.get("pricing_skus"))
    value = bounded_catalogue_metadata(dict(value))
    model_id = _safe_required_text(value.get("id"), "model identifier")
    frame_values = _optional_string_tuple(value.get("supported_frame_images"))
    frame_types = (
        frozenset(
            FrameType(item)
            for item in frame_values
            if item in {member.value for member in FrameType}
        )
        if frame_values is not None
        else None
    )
    audio_raw = value.get("generate_audio")
    seed_raw = value.get("seed")
    text_raw = value.get("supports_text_only")
    source_raw = value.get("source_required")
    known_keys = {
        "id",
        "canonical_slug",
        "hugging_face_id",
        "name",
        "created",
        "description",
        "supported_durations",
        "supported_resolutions",
        "supported_aspect_ratios",
        "supported_sizes",
        "supported_frame_images",
        "generate_audio",
        "seed",
        "pricing_skus",
        "supports_text_only",
        "source_required",
        "reference_kinds",
        "max_reference_count",
        "min_reference_count",
        "per_kind_max",
        "per_kind_min",
        "required_reference_kinds",
        "mutually_exclusive_reference_kinds",
        "mixed_reference_kinds",
        "supports_edit",
        "supports_extend",
        CONFIGURATION_KEY,
        REQUEST_SHAPES_KEY,
    }
    raw_kinds = _optional_string_tuple(value.get("reference_kinds"))
    reference_kinds = (
        frozenset(InputReferenceKind(kind) for kind in raw_kinds)
        if raw_kinds is not None
        and all(kind in {k.value for k in InputReferenceKind} for kind in raw_kinds)
        else None
    )
    limit = value.get("max_reference_count")
    count = limit if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 0 else None
    mixed = value.get("mixed_reference_kinds")
    observed = datetime.now(timezone.utc).isoformat()
    control_keys = {"upscale_factor", "creativity", "allowed_passthrough_parameters"}
    control_values = {key: _catalogue_control(value.get(key), key) for key in control_keys}
    configuration = None
    configuration_invalid = False
    if value.get(CONFIGURATION_KEY) is not None:
        try:
            configuration = normalize_constraints(value[CONFIGURATION_KEY])
        except (TypeError, ValueError):
            configuration_invalid = True
    shapes = None
    if isinstance(value.get(REQUEST_SHAPES_KEY), dict):
        raw_shapes = value[REQUEST_SHAPES_KEY]
        if raw_shapes.get("schema_version") == 1 and isinstance(raw_shapes.get("methods"), dict):
            methods = {}
            for method, entry in raw_shapes["methods"].items():
                try:
                    checked = normalize_request_shapes(
                        {"schema_version": 1, "methods": {method: entry}}
                    )
                except (TypeError, ValueError, KeyError, AttributeError, IndexError):
                    if method in {m.value for m in InferenceMethod}:
                        methods[method] = {"state": "UNKNOWN"}
                    continue
                methods.update(checked["methods"])
            shapes = {"schema_version": 1, "methods": methods}
    safe_metadata = bounded_catalogue_metadata(dict(value))
    for key, control_value in control_values.items():
        if key in safe_metadata and value[key] is not None and control_value is None:
            safe_metadata[key] = {"discovery_omitted": "INVALID_TYPED_CONTROL"}
    facts = tuple(
        CapabilityFact(
            model_id,
            str(key),
            shapes
            if key == REQUEST_SHAPES_KEY
            else configuration
            if key == CONFIGURATION_KEY
            else control_values[key]
            if key in control_keys
            else raw
            if key in known_keys
            else safe_metadata.get(str(key)),
            CapabilityFactState.UNKNOWN
            if (
                shapes is None
                if key == REQUEST_SHAPES_KEY
                else configuration is None
                if key == CONFIGURATION_KEY
                else control_values[key] is None
                if key in control_keys
                else raw is None or key not in known_keys
            )
            else CapabilityFactState.UNSUPPORTED
            if raw is False
            else CapabilityFactState.SUPPORTED,
            "LIVE_STRUCTURED_API",
            "https://openrouter.ai/api/v1/videos/models",
            observed,
            "CAPABILITY_ONLY_CONFIRMED; wire unresolved"
            if key in control_keys
            else "exact model catalogue metadata",
            "live",
        )
        for key, raw in value.items()
        if key
        not in {
            "id",
            "canonical_slug",
            "hugging_face_id",
            "name",
            "created",
            "description",
            "pricing_skus",
        }
    ) + (
        CapabilityFact(
            model_id,
            "__catalogue_observation__",
            safe_metadata,
            CapabilityFactState.UNKNOWN,
            "LIVE_CATALOGUE_EVIDENCE",
            "https://openrouter.ai/api/v1/videos/models",
            observed,
            "Bounded discovery evidence only; never request passthrough",
            "live",
        ),
    )
    return ModelCapabilities(
        model_id=model_id,
        canonical_slug=_optional_text(value.get("canonical_slug")),
        name=_optional_text(value.get("name")),
        supported_durations=_optional_int_tuple(value.get("supported_durations")),
        supported_resolutions=_optional_string_tuple(value.get("supported_resolutions")),
        supported_aspect_ratios=_optional_string_tuple(value.get("supported_aspect_ratios")),
        supported_sizes=_optional_string_tuple(value.get("supported_sizes")),
        supported_frame_types=frame_types,
        generate_audio=audio_raw if isinstance(audio_raw, bool) else None,
        supports_seed=seed_raw if isinstance(seed_raw, bool) else None,
        pricing_evidence=pricing_evidence,
        supports_text_only=text_raw if isinstance(text_raw, bool) else None,
        source_required=source_raw if isinstance(source_raw, bool) else None,
        input_reference_capabilities=InputReferenceCapabilities(
            reference_kinds=reference_kinds,
            max_reference_count=count,
            mixed_reference_kinds=mixed if isinstance(mixed, bool) else None,
            reference_kinds_source=CapabilityEvidenceSource.LEVEL_A
            if reference_kinds is not None
            else None,
            max_reference_count_source=CapabilityEvidenceSource.LEVEL_A
            if count is not None
            else None,
            mixed_reference_kinds_source=CapabilityEvidenceSource.LEVEL_A
            if isinstance(mixed, bool)
            else None,
        )
        if any(v is not None for v in (reference_kinds, count, mixed))
        else None,
        supports_edit=value.get("supports_edit")
        if isinstance(value.get("supports_edit"), bool)
        else None,
        supports_extend=value.get("supports_extend")
        if isinstance(value.get("supports_extend"), bool)
        else None,
        evidence_facts=facts,
        unmapped_capability_keys=tuple(
            sorted(
                {str(key) for key in value if key not in known_keys}
                | ({CONFIGURATION_KEY} if configuration_invalid else set())
            )
        ),
    )


def _catalogue_control(raw: object, key: str) -> object:
    """Retain typed public control evidence without enabling body passthrough."""
    if key == "allowed_passthrough_parameters":
        if isinstance(raw, list) and all(
            isinstance(item, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", item)
            for item in raw
        ):
            return raw
        return None
    values = [raw.get("min"), raw.get("max")] if isinstance(raw, dict) else raw
    if not isinstance(values, list) or len(values) != 2:
        return None
    if not all(type(item) in (int, float) and math.isfinite(item) for item in values):
        return None
    if key == "creativity" and not all(type(item) is int for item in values):
        return None
    if values[0] > values[1] or values[0] < 0:
        return None
    normalized: dict[str, object] = {"type": "number", "min": values[0], "max": values[1]}
    if key == "creativity" and isinstance(raw, list):
        normalized["values"] = list(raw)
    return normalized


def _parse_pricing_evidence(value: object) -> PricingEvidence | None:
    if not isinstance(value, Mapping) or not value:
        return None
    parsed: list[PricingSku] = []
    for raw_key, raw_rate in value.items():
        try:
            key = _safe_required_text(raw_key, "pricing SKU", maximum=128)
        except MalformedOpenRouterResponseError:
            return None
        rate = _parse_cost(raw_rate)
        if rate is None:
            return None
        parsed.append(PricingSku(key, rate))
    return PricingEvidence(tuple(sorted(parsed, key=lambda sku: sku.key)))


def _parse_cost(value: object) -> Decimal | None:
    if (
        value is None
        or isinstance(value, bool)
        or not isinstance(value, (Decimal, int, float, str))
    ):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def _parse_job(value: Mapping[Any, Any]) -> RemoteJobSnapshot:
    job_id = _safe_required_text(value.get("id"), "job identifier")
    status = _safe_required_text(value.get("status"), "job status", maximum=128)
    usage_raw = value.get("usage")
    cost = _parse_cost(usage_raw.get("cost")) if isinstance(usage_raw, Mapping) else None
    error_raw = value.get("error")
    error_message = _optional_text(error_raw, maximum=1024)
    if error_message is None and isinstance(error_raw, Mapping):
        error_message = _optional_text(error_raw.get("message"), maximum=1024)
    return RemoteJobSnapshot(
        job_id=job_id,
        status_raw=status,
        generation_id=_optional_text(value.get("generation_id")),
        model=_optional_text(value.get("model")),
        usage=UsageCost(cost),
        error_message=error_message,
    )


__all__ = (
    "ContentClient",
    "DiscoveryClient",
    "ObservationClient",
    "OpenRouterVideoClient",
    "SubmitClient",
)
