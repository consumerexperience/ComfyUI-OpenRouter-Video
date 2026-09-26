"""Capability discovery, bounded cache fallback, and paid-request validation."""

from __future__ import annotations

import asyncio
import ipaddress
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import NoReturn
from urllib.parse import urlsplit

from openrouter_video.capability_overlays import apply_capability_overlay
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
    InputReference,
    InputReferenceKind,
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


class GenerationMode(str, Enum):
    """Product modes evaluated independently by the Phase-8 evidence gate."""

    T2V = "T2V"
    FIRST_FRAME = "FIRST_FRAME"
    FIRST_PLUS_LAST = "FIRST_PLUS_LAST"
    MULTI_IMAGE_REFERENCE = "MULTI_IMAGE_REFERENCE"
    VIDEO_REFERENCE = "VIDEO_REFERENCE"
    IMAGE_PLUS_VIDEO_REFERENCE = "IMAGE_PLUS_VIDEO_REFERENCE"
    PROMPT_OPTIONAL_REFERENCE_GENERATION = "PROMPT_OPTIONAL_REFERENCE_GENERATION"


class CapabilityModeStatus(str, Enum):
    """Evidence-derived runtime disposition for one independent product mode."""

    READY = "READY"
    CAPABILITY_SIGNAL_GAP = "CAPABILITY_SIGNAL_GAP"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    DEFERRED = "DEFERRED"


def mode_enforcement_matrix(
    capabilities: ModelCapabilities,
) -> dict[GenerationMode, CapabilityModeStatus]:
    """Evaluate only current authoritative runtime-resolvable capability evidence."""

    frames = capabilities.supported_frame_types
    references = capabilities.input_reference_capabilities
    if references is None:
        multi_image = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        video = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        mixed = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
    elif references.conflicts:
        multi_image = CapabilityModeStatus.CONFLICT
        video = CapabilityModeStatus.CONFLICT
        mixed = CapabilityModeStatus.CONFLICT
    elif references.reference_kinds is None:
        multi_image = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        video = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        mixed = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
    else:
        kinds = references.reference_kinds
        if InputReferenceKind.IMAGE not in kinds:
            multi_image = CapabilityModeStatus.UNSUPPORTED
        elif references.max_reference_count is None:
            multi_image = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        elif references.max_reference_count < 2:
            multi_image = CapabilityModeStatus.UNSUPPORTED
        else:
            multi_image = CapabilityModeStatus.READY

        video = (
            CapabilityModeStatus.READY
            if InputReferenceKind.VIDEO in kinds
            else CapabilityModeStatus.UNSUPPORTED
        )

        if not {InputReferenceKind.IMAGE, InputReferenceKind.VIDEO}.issubset(kinds):
            mixed = CapabilityModeStatus.UNSUPPORTED
        elif references.mixed_image_video_references is None:
            mixed = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        elif references.mixed_image_video_references is False:
            mixed = CapabilityModeStatus.UNSUPPORTED
        elif references.max_reference_count is None:
            mixed = CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
        elif references.max_reference_count < 2:
            mixed = CapabilityModeStatus.UNSUPPORTED
        else:
            mixed = CapabilityModeStatus.READY
    return {
        GenerationMode.T2V: CapabilityModeStatus.READY,
        GenerationMode.FIRST_FRAME: (
            CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
            if frames is None
            else (
                CapabilityModeStatus.READY
                if FrameType.FIRST in frames
                else CapabilityModeStatus.UNSUPPORTED
            )
        ),
        GenerationMode.FIRST_PLUS_LAST: (
            CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
            if frames is None
            else (
                CapabilityModeStatus.READY
                if {FrameType.FIRST, FrameType.LAST}.issubset(frames)
                else CapabilityModeStatus.UNSUPPORTED
            )
        ),
        GenerationMode.MULTI_IMAGE_REFERENCE: multi_image,
        GenerationMode.VIDEO_REFERENCE: video,
        GenerationMode.IMAGE_PLUS_VIDEO_REFERENCE: mixed,
        GenerationMode.PROMPT_OPTIONAL_REFERENCE_GENERATION: CapabilityModeStatus.DEFERRED,
    }


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
                if self._now() - observation.observed_at <= FRESH_TTL:
                    return apply_capability_overlay(model)
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
            tuple(apply_capability_overlay(model) for model in observation.models),
        )

    def is_fresh(self, observation: CapabilityObservation) -> bool:
        """Return whether external truth is inside the approved freshness window."""

        return self._now() - observation.observed_at <= FRESH_TTL


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
        references = request.input_references.references if request.input_references else ()
        if request.prompt is not None and not isinstance(request.prompt, str):
            self._fail(ProductErrorCode.UNSUPPORTED_PARAMETER, "Prompt must be text.")
        if not (request.prompt and request.prompt.strip()):
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
        if references and (request.first_frame is not None or request.last_frame is not None):
            self._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Frame guidance cannot be combined with input references.",
            )
        for reference in references:
            self._validate_reference(reference)

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
        matrix = mode_enforcement_matrix(capabilities)
        if references:
            mode = self._reference_mode(references)
            status = matrix[mode]
            if status is not CapabilityModeStatus.READY:
                self._fail(
                    ProductErrorCode.CAPABILITY_SIGNAL_GAP,
                    f"{mode.value} is blocked because runtime capability evidence "
                    f"is {status.value}.",
                )
            reference_capabilities = capabilities.input_reference_capabilities
            if (
                reference_capabilities is not None
                and reference_capabilities.max_reference_count is not None
                and len(references) > reference_capabilities.max_reference_count
            ):
                self._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "The input reference collection exceeds the proven model limit.",
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
    def _validate_reference(reference: InputReference) -> None:
        if not isinstance(reference, InputReference) or not isinstance(
            reference.kind, InputReferenceKind
        ):
            RequestValidator._fail(
                ProductErrorCode.UNSUPPORTED_PARAMETER,
                "Input references require a supported typed media kind.",
            )
        if not _is_public_https_url(reference.url):
            RequestValidator._fail(
                ProductErrorCode.INVALID_MEDIA_URL,
                "Input references require a direct public HTTPS URL.",
            )

    @staticmethod
    def _reference_mode(references: tuple[InputReference, ...]) -> GenerationMode:
        kinds = {reference.kind for reference in references}
        if kinds == {InputReferenceKind.IMAGE}:
            if len(references) < 2:
                RequestValidator._fail(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    "Multi-image reference generation requires at least two references.",
                )
            return GenerationMode.MULTI_IMAGE_REFERENCE
        if kinds == {InputReferenceKind.VIDEO}:
            return GenerationMode.VIDEO_REFERENCE
        if kinds == {InputReferenceKind.IMAGE, InputReferenceKind.VIDEO}:
            return GenerationMode.IMAGE_PLUS_VIDEO_REFERENCE
        RequestValidator._fail(
            ProductErrorCode.UNSUPPORTED_PARAMETER,
            "Input reference collection is unsupported.",
        )

    @staticmethod
    def _fail(code: ProductErrorCode, message: str) -> NoReturn:
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
    "CapabilityModeStatus",
    "CapabilityObservation",
    "CapabilityService",
    "FRESH_TTL",
    "GenerationMode",
    "LKG_TTL",
    "RequestValidator",
    "mode_enforcement_matrix",
)
