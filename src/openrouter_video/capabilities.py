"""Capability discovery, bounded cache fallback, and paid-request validation."""

from __future__ import annotations

import asyncio
import ipaddress
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from openrouter_video.client import DiscoveryClient
from openrouter_video.errors import (
    MalformedOpenRouterResponseError,
    OpenRouterHTTPError,
    ProductFailureError,
    TransportError,
)
from openrouter_video.models import (
    BillingContext,
    FrameReference,
    FrameType,
    GenerationRequest,
    ModelCapabilities,
    ProductError,
    ProductErrorCode,
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


class CapabilityService:
    """Serve fresh catalog data and bounded LKG only when live discovery fails."""

    __slots__ = ("_client", "_jitter", "_now", "_sleep", "_store")

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

    async def catalog(self) -> CapabilityObservation:
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
                self._store.replace_capability_catalog(models, observed_at)
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
            return CapabilityObservation(cached[0], cached[1])
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
                return model
        raise ProductFailureError(
            ProductError(
                ProductErrorCode.MODEL_UNAVAILABLE,
                "The selected video model is not available in the current catalog.",
                BillingContext.NO_SUBMIT,
            )
        )


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
        if not request.prompt.strip():
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "A non-empty prompt is required.")
        if request.duration is not None and (
            isinstance(request.duration, bool) or request.duration < 1
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

    def validate_capabilities(
        self, request: GenerationRequest, capabilities: ModelCapabilities
    ) -> None:
        """Reject explicit unsupported intent without silent substitution or removal."""

        if request.model not in {capabilities.model_id, capabilities.canonical_slug}:
            self._fail(ProductErrorCode.UNSUPPORTED_MODEL, "The selected model does not match.")
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
        if request.seed is not None and capabilities.supports_seed is False:
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "Seed is not supported.")
        if request.generate_audio and capabilities.generate_audio is not True:
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Generated audio is not positively supported by this model.",
            )
        if (
            request.first_frame is not None
            and FrameType.FIRST not in capabilities.supported_frame_types
        ):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "First-frame guidance is not positively supported by this model.",
            )
        if (
            request.last_frame is not None
            and FrameType.LAST not in capabilities.supported_frame_types
        ):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Last-frame guidance is not positively supported by this model.",
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
        if frame.frame_type is not expected or not _is_public_https_url(frame.url):
            RequestValidator._fail(
                ProductErrorCode.INVALID_MEDIA_URL,
                "Frame images require a direct public HTTPS URL.",
            )

    @staticmethod
    def _fail(code: ProductErrorCode, message: str) -> None:
        raise ProductFailureError(ProductError(code, message, BillingContext.NO_SUBMIT))


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
    "CapabilityObservation",
    "CapabilityService",
    "FRESH_TTL",
    "LKG_TTL",
    "RequestValidator",
)
