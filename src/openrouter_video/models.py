"""Stable Headless Core domain contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


class FrameType(str, Enum):
    """Frame positions supported by the frozen v0.1 request surface."""

    FIRST = "first_frame"
    LAST = "last_frame"


class LocalLifecycleState(str, Enum):
    """Durable local lifecycle states, including ADR-029 rejection state."""

    NOT_SUBMITTED = "NOT_SUBMITTED"
    VALIDATING = "VALIDATING"
    SUBMITTING = "SUBMITTING"
    ACCEPTED = "ACCEPTED"
    POLLING = "POLLING"
    COMPLETED = "COMPLETED"
    DOWNLOADING = "DOWNLOADING"
    DONE = "DONE"
    SUBMIT_REJECTED = "SUBMIT_REJECTED"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    OBSERVATION_INTERRUPTED = "OBSERVATION_INTERRUPTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN_REMOTE_STATE = "UNKNOWN_REMOTE_STATE"


class ProductErrorCode(str, Enum):
    """Specification-defined product-facing error codes."""

    API_KEY_MISSING = "API_KEY_MISSING"
    API_KEY_INVALID = "API_KEY_INVALID"
    DISCOVERY_UNAVAILABLE = "DISCOVERY_UNAVAILABLE"
    INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    UNSUPPORTED_PARAMETER = "UNSUPPORTED_PARAMETER"
    INVALID_MEDIA_URL = "INVALID_MEDIA_URL"
    RATE_LIMITED_SUBMIT = "RATE_LIMITED_SUBMIT"
    RATE_LIMITED_POLL = "RATE_LIMITED_POLL"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    STATUS_CHECK_FAILED = "STATUS_CHECK_FAILED"
    GENERATION_FAILED = "GENERATION_FAILED"
    JOB_CANCELLED = "JOB_CANCELLED"
    JOB_EXPIRED = "JOB_EXPIRED"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    UNKNOWN_REMOTE_STATE = "UNKNOWN_REMOTE_STATE"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    INVALID_VIDEO_RESPONSE = "INVALID_VIDEO_RESPONSE"
    DISK_ERROR = "DISK_ERROR"
    LOCAL_STATE_CORRUPT = "LOCAL_STATE_CORRUPT"
    ATTRIBUTION_CONFIG_INVALID = "ATTRIBUTION_CONFIG_INVALID"


class BillingContext(str, Enum):
    """Whether a failure is before, ambiguous around, or after known submission."""

    NO_SUBMIT = "NO_SUBMIT"
    MAY_HAVE_SUBMITTED = "MAY_HAVE_SUBMITTED"
    KNOWN_JOB_EXISTS = "KNOWN_JOB_EXISTS"


@dataclass(frozen=True, slots=True)
class FrameReference:
    """Transient HTTPS media reference; never persisted or logged."""

    frame_type: FrameType
    url: str


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Frozen v0.1 generation request surface; sensitive and transient."""

    model: str
    prompt: str
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    size: str | None = None
    seed: int | None = None
    generate_audio: bool = False
    first_frame: FrameReference | None = None
    last_frame: FrameReference | None = None

    def to_openrouter_payload(self) -> dict[str, object]:
        """Return only the frozen OpenRouter request fields with no passthrough escape hatch."""

        payload: dict[str, object] = {
            "model": self.model,
            "prompt": self.prompt,
            "generate_audio": self.generate_audio,
        }
        optional: tuple[tuple[str, object | None], ...] = (
            ("duration", self.duration),
            ("resolution", self.resolution),
            ("aspect_ratio", self.aspect_ratio),
            ("size", self.size),
            ("seed", self.seed),
        )
        for name, value in optional:
            if value is not None:
                payload[name] = value
        frames = [
            {"frame_type": frame.frame_type.value, "url": frame.url}
            for frame in (self.first_frame, self.last_frame)
            if frame is not None
        ]
        if frames:
            payload["frame_images"] = frames
        return payload


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Normalized, persistable model capability metadata."""

    model_id: str
    canonical_slug: str | None = None
    name: str | None = None
    supported_durations: tuple[int, ...] | None = None
    supported_resolutions: tuple[str, ...] | None = None
    supported_aspect_ratios: tuple[str, ...] | None = None
    supported_sizes: tuple[str, ...] | None = None
    supported_frame_types: frozenset[FrameType] = frozenset()
    generate_audio: bool | None = None
    supports_seed: bool | None = None


@dataclass(frozen=True, slots=True)
class UsageCost:
    """Authoritative cost returned by OpenRouter, or absence of cost truth."""

    actual_cost_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class VideoArtifact:
    """Validated durable local video artifact."""

    path: Path
    media_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ProductError:
    """Sanitized product-facing failure with explicit billing context."""

    code: ProductErrorCode
    message: str
    billing_context: BillingContext
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class RemoteJobSnapshot:
    """Tolerant normalized view of an OpenRouter asynchronous job response."""

    job_id: str
    status_raw: str
    generation_id: str | None = None
    model: str | None = None
    usage: UsageCost = UsageCost(None)
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class JobRecord:
    """Approved non-sensitive SQLite recovery state."""

    schema_version: int
    operation_id: str
    request_fingerprint: str
    model: str
    local_state: LocalLifecycleState
    created_at: datetime
    node_instance_id: str | None = None
    job_id: str | None = None
    remote_status_raw: str | None = None
    submission_started_at: datetime | None = None
    accepted_at: datetime | None = None
    last_observed_at: datetime | None = None
    completed_at: datetime | None = None
    actual_cost_usd: Decimal | None = None
    output_relpath: str | None = None
    product_error_code: ProductErrorCode | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Headless application result consumed by a future ComfyUI adapter."""

    state: LocalLifecycleState
    job_id: str | None
    actual_cost_usd: Decimal | None = None
    artifact: VideoArtifact | None = None
    error: ProductError | None = None


def request_fingerprint_v1(request: GenerationRequest) -> str:
    """Return the exact versioned advisory checksum defined by ADR-028."""

    payload: dict[str, Any] = {
        "schema": 1,
        "model": request.model,
        "duration": request.duration,
        "resolution": request.resolution,
        "aspect_ratio": request.aspect_ratio,
        "size": request.size,
        "seed": request.seed,
        "generate_audio": request.generate_audio,
        "first_frame_present": request.first_frame is not None,
        "last_frame_present": request.last_frame is not None,
    }
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"v1:{hashlib.sha256(canonical_bytes).hexdigest()}"


__all__ = (
    "BillingContext",
    "FrameReference",
    "FrameType",
    "GenerationRequest",
    "GenerationResult",
    "JobRecord",
    "LocalLifecycleState",
    "ModelCapabilities",
    "ProductError",
    "ProductErrorCode",
    "RemoteJobSnapshot",
    "UsageCost",
    "VideoArtifact",
    "request_fingerprint_v1",
)
