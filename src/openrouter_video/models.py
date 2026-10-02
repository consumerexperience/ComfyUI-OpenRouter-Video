"""Stable Headless Core domain contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from openrouter_video.local_media import LocalMedia


class FrameType(str, Enum):
    """Frame positions supported by the frozen v0.1 request surface."""

    FIRST = "first_frame"
    LAST = "last_frame"


class InputReferenceKind(str, Enum):
    """Typed media kinds accepted by the evidence-backed reference protocol."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class InferenceMethod(str, Enum):
    """Local product intent; values are never serialized to OpenRouter."""

    T2V = "T2V"
    I2V = "I2V"
    FLF2V = "FLF2V"
    IR2V = "IR2V"
    MI2V = "MI2V"
    VR2V = "VR2V"
    AR2V = "AR2V"
    MMR2V = "MMR2V"
    V2V_EDIT = "V2V_EDIT"
    V2V_EXTEND = "V2V_EXTEND"


class CapabilityEvidenceSource(str, Enum):
    """Authoritative source used for one normalized capability field."""

    LEVEL_A = "LEVEL_A"
    EVIDENCE_OVERLAY = "EVIDENCE_OVERLAY"


class InputReferenceCapabilityField(str, Enum):
    """Independently mergeable reference-capability fields."""

    REFERENCE_KINDS = "reference_kinds"
    MAX_REFERENCE_COUNT = "max_reference_count"
    MIXED_REFERENCE_KINDS = "mixed_reference_kinds"


class ModelCapabilityField(str, Enum):
    """Exact-model primitive fields whose evidence can conflict."""

    EDIT = "supports_edit"
    EXTEND = "supports_extend"


@dataclass(frozen=True, slots=True)
class PricingSku:
    """One normalized non-negative catalogue price with an opaque SKU key."""

    key: str
    rate_usd: Decimal


@dataclass(frozen=True, slots=True)
class PricingEvidence:
    """Typed catalogue pricing evidence retained inside Core only."""

    skus: tuple[PricingSku, ...]


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

    STORAGE_UPLOAD_FAILED = "STORAGE_UPLOAD_FAILED"
    NATIVE_MEDIA_INVALID = "NATIVE_MEDIA_INVALID"
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
    CAPABILITY_SIGNAL_GAP = "CAPABILITY_SIGNAL_GAP"


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
class InputReference:
    """One transient typed media reference; never persisted or logged."""

    kind: InputReferenceKind
    url: str = field(default="", repr=False)
    local_media: LocalMedia | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class InputReferenceCollection:
    """Ordered references whose occurrences are preserved exactly."""

    references: tuple[InputReference, ...] = ()


@dataclass(frozen=True, slots=True)
class InputReferenceCapabilities:
    """Transient effective reference capabilities with field-level provenance."""

    reference_kinds: frozenset[InputReferenceKind] | None = None
    max_reference_count: int | None = None
    mixed_reference_kinds: bool | None = None
    reference_kinds_source: CapabilityEvidenceSource | None = None
    max_reference_count_source: CapabilityEvidenceSource | None = None
    mixed_reference_kinds_source: CapabilityEvidenceSource | None = None
    conflicts: frozenset[InputReferenceCapabilityField] = frozenset()


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Bounded generation request surface; sensitive and transient."""

    model: str
    prompt: str | None
    inference_method: InferenceMethod = InferenceMethod.T2V
    duration: int | None = None
    resolution: str | None = None
    aspect_ratio: str | None = None
    size: str | None = None
    seed: int | None = None
    generate_audio: bool = False
    first_frame: FrameReference | None = None
    last_frame: FrameReference | None = None
    source_video: InputReference | None = None
    input_references: InputReferenceCollection | None = None

    def to_openrouter_payload(self) -> dict[str, object]:
        references = self.input_references.references if self.input_references else ()
        if any(item.local_media is not None for item in references) or (
            self.source_video is not None and self.source_video.local_media is not None
        ):
            raise ValueError("Native media must be staged before serialization.")
        """Return only the frozen OpenRouter request fields with no passthrough escape hatch."""

        payload: dict[str, object] = {"model": self.model, "generate_audio": self.generate_audio}
        if self.prompt is not None:
            payload["prompt"] = self.prompt
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
            {
                "type": "image_url",
                "image_url": {"url": frame.url},
                "frame_type": frame.frame_type.value,
            }
            for frame in (self.first_frame, self.last_frame)
            if frame is not None
        ]
        if frames:
            payload["frame_images"] = frames
        references = self.input_references.references if self.input_references is not None else ()
        if self.source_video is not None:
            references = (self.source_video, *references)
        if references:
            payload["input_references"] = [
                {
                    "type": f"{reference.kind.value}_url",
                    f"{reference.kind.value}_url": {"url": reference.url},
                }
                for reference in references
            ]
        return payload


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Normalized catalog metadata plus transient effective capability fields."""

    model_id: str
    canonical_slug: str | None = None
    name: str | None = None
    supported_durations: tuple[int, ...] | None = None
    supported_resolutions: tuple[str, ...] | None = None
    supported_aspect_ratios: tuple[str, ...] | None = None
    supported_sizes: tuple[str, ...] | None = None
    supported_frame_types: frozenset[FrameType] | None = None
    generate_audio: bool | None = None
    supports_seed: bool | None = None
    input_reference_capabilities: InputReferenceCapabilities | None = None
    supports_edit: bool | None = None
    supports_extend: bool | None = None
    edit_support_source: CapabilityEvidenceSource | None = None
    extend_support_source: CapabilityEvidenceSource | None = None
    capability_conflicts: frozenset[ModelCapabilityField] = frozenset()
    pricing_evidence: PricingEvidence | None = None


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
    model: str | None
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
    model: str | None = None
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


def request_fingerprint_v2(request: GenerationRequest) -> str:
    """Return the Phase-8 structural checksum without sensitive request values."""

    references = request.input_references.references if request.input_references is not None else ()
    payload: dict[str, Any] = {
        "schema": 2,
        "model": request.model,
        "duration": request.duration,
        "resolution": request.resolution,
        "aspect_ratio": request.aspect_ratio,
        "size": request.size,
        "seed": request.seed,
        "generate_audio": request.generate_audio,
        "prompt_present": bool(request.prompt and request.prompt.strip()),
        "first_frame_present": request.first_frame is not None,
        "last_frame_present": request.last_frame is not None,
        "input_reference_present": bool(references),
        "input_references": {
            "schema": 1,
            "count": len(references),
            "kinds": [reference.kind.value for reference in references],
        },
    }
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"v2:{hashlib.sha256(canonical_bytes).hexdigest()}"


def request_fingerprint_v3(request: GenerationRequest) -> str:
    """Return the Phase-10 structural intent checksum without sensitive values."""

    references = request.input_references.references if request.input_references is not None else ()
    payload: dict[str, Any] = {
        "schema": 3,
        "model": request.model,
        "inference_method": request.inference_method.value,
        "duration": request.duration,
        "resolution": request.resolution,
        "aspect_ratio": request.aspect_ratio,
        "size": request.size,
        "seed": request.seed,
        "generate_audio": request.generate_audio,
        "prompt_present": bool(request.prompt and request.prompt.strip()),
        "first_frame_present": request.first_frame is not None,
        "last_frame_present": request.last_frame is not None,
        "source_video_present": request.source_video is not None,
        "input_reference_count": len(references),
        "input_reference_kinds": [reference.kind.value for reference in references],
    }
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"v3:{hashlib.sha256(canonical_bytes).hexdigest()}"


__all__ = (
    "BillingContext",
    "CapabilityEvidenceSource",
    "FrameReference",
    "FrameType",
    "GenerationRequest",
    "GenerationResult",
    "JobRecord",
    "InputReference",
    "InputReferenceCapabilities",
    "InputReferenceCapabilityField",
    "InputReferenceCollection",
    "InputReferenceKind",
    "InferenceMethod",
    "LocalLifecycleState",
    "ModelCapabilities",
    "ModelCapabilityField",
    "ProductError",
    "ProductErrorCode",
    "PricingEvidence",
    "PricingSku",
    "RemoteJobSnapshot",
    "UsageCost",
    "VideoArtifact",
    "request_fingerprint_v1",
    "request_fingerprint_v2",
    "request_fingerprint_v3",
)
