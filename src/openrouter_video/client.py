"""Typed OpenRouter Video client behind the canonical request policy."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from openrouter_video.errors import MalformedOpenRouterResponseError, OpenRouterHTTPError
from openrouter_video.models import (
    FrameType,
    GenerationRequest,
    ModelCapabilities,
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
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    result = tuple(item for item in value if isinstance(item, int) and not isinstance(item, bool))
    return result if len(result) == len(value) else None


def _parse_capability(value: Mapping[Any, Any]) -> ModelCapabilities:
    model_id = _safe_required_text(value.get("id"), "model identifier")
    frame_values = _optional_string_tuple(value.get("supported_frame_images")) or ()
    frame_types = frozenset(
        FrameType(item) for item in frame_values if item in {member.value for member in FrameType}
    )
    audio_raw = value.get("generate_audio")
    seed_raw = value.get("seed")
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
    )


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
