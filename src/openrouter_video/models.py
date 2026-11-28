"""Stable Headless Core domain contracts."""

from __future__ import annotations

import hashlib
import json
import math
import re
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
    V2V_UPSCALE = "V2V_UPSCALE"
    AVATAR_AUDIO = "AVATAR_AUDIO"


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
class ProviderOption:
    """One bounded scalar passthrough value for a validated provider slug."""

    provider: str
    key: str
    value: str | bool | int | float = field(repr=False)
    container: str | None = None
    path: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provider, str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", self.provider
        ):
            raise ValueError("Provider must be a valid lowercase provider slug.")
        if not isinstance(self.key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", self.key):
            raise ValueError("Provider option key must be a non-empty scalar key.")
        if self.container not in (None, "parameters"):
            raise ValueError("Provider option container must be absent or 'parameters'.")
        if (
            not isinstance(self.path, (tuple, list))
            or len(self.path) > 4
            or any(
                not (
                    isinstance(part, str)
                    and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", part)
                    or type(part) is int
                    and 0 <= part < 64
                )
                for part in self.path
            )
        ):
            raise ValueError(
                "Provider option path must contain field names or bounded array indices."
            )
        object.__setattr__(self, "path", tuple(self.path))
        if type(self.value) not in (str, bool, int, float):
            raise ValueError("Provider option values must be strings, booleans, or numbers.")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("Provider option numbers must be finite.")


def _insert_provider_leaf(
    target: dict[str, Any] | list[Any], path: tuple[str | int, ...], value: object
) -> None:
    key = path[0]
    if isinstance(target, list):
        if type(key) is not int:
            raise ValueError("Provider array requires integer indices.")
        while len(target) <= key:
            target.append(None)
        child = target[key]
    else:
        if not isinstance(key, str):
            raise ValueError("Provider object requires field names.")
        child = target.get(key)
    if len(path) == 1:
        target[key] = value  # type: ignore[index]  # container/key pairing checked above
        return
    expected = list if type(path[1]) is int else dict
    if child is None:
        child = expected()
        target[key] = child  # type: ignore[index]  # container/key pairing checked above
    elif not isinstance(child, expected):
        raise ValueError("Provider option container collides with another value.")
    _insert_provider_leaf(child, path[1:], value)


def _check_provider_tree(value: object) -> None:
    if value is None:
        raise ValueError("Provider arrays must be contiguous, without omitted items.")
    if isinstance(value, dict):
        for child in value.values():
            _check_provider_tree(child)
    elif isinstance(value, list):
        for child in value:
            _check_provider_tree(child)


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
    generate_audio: bool | None = False
    first_frame: FrameReference | None = None
    last_frame: FrameReference | None = None
    source_video: InputReference | None = None
    input_references: InputReferenceCollection | None = None
    previous_job_id: str | None = field(default=None, repr=False)
    upscale_factor: float | int | None = None
    creativity: int | None = None
    provider_options: tuple[ProviderOption, ...] = ()

    def __post_init__(self) -> None:
        if self.previous_job_id is not None and (
            not isinstance(self.previous_job_id, str)
            or re.fullmatch(r"gen-vid-\d+-[0-9A-Za-z]{20}", self.previous_job_id) is None
        ):
            raise ValueError(
                "previous_job_id must match the OpenRouter video generation ID pattern."
            )
        if self.upscale_factor is not None and (
            type(self.upscale_factor) not in (int, float)
            or not math.isfinite(self.upscale_factor)
            or self.upscale_factor <= 0
        ):
            raise ValueError("upscale_factor must be a positive finite number.")
        if self.creativity is not None and type(self.creativity) is not int:
            raise ValueError("creativity must be an integer.")
        if not isinstance(self.provider_options, tuple) or any(
            not isinstance(option, ProviderOption) for option in self.provider_options
        ):
            raise ValueError("provider_options must be a tuple of ProviderOption entries.")
        seen: set[tuple[str, str | None, str, tuple[str | int, ...]]] = set()
        for option in self.provider_options:
            identity = (option.provider, option.container, option.key, option.path)
            if any(
                prior[:3] == identity[:3]
                and (
                    prior[3][: len(option.path)] == option.path
                    or option.path[: len(prior[3])] == prior[3]
                )
                for prior in seen
            ):
                raise ValueError("Duplicate provider option key for provider.")
            seen.add(identity)
        nested_providers = {option.provider for option in self.provider_options if option.container}
        if any(
            option.provider in nested_providers
            and option.container is None
            and option.key == "parameters"
            for option in self.provider_options
        ):
            raise ValueError(
                "Direct 'parameters' option conflicts with nested provider parameters."
            )

    def to_openrouter_payload(self) -> dict[str, object]:
        if self.size is not None and (self.resolution is not None or self.aspect_ratio is not None):
            raise ValueError("Ambiguous geometry: use exact size or resolution/aspect ratio.")
        references = self.input_references.references if self.input_references else ()
        if any(item.local_media is not None for item in references) or (
            self.source_video is not None and self.source_video.local_media is not None
        ):
            raise ValueError("Native media must be staged before serialization.")
        """Return only the frozen OpenRouter request fields with no passthrough escape hatch."""

        payload: dict[str, object] = {"model": self.model}
        if self.prompt is not None:
            payload["prompt"] = self.prompt
        optional: tuple[tuple[str, object | None], ...] = (
            ("generate_audio", self.generate_audio),
            ("duration", self.duration),
            ("resolution", self.resolution),
            ("aspect_ratio", self.aspect_ratio),
            ("size", self.size),
            ("seed", self.seed),
        )
        for name, value in optional:
            if value is not None:
                payload[name] = value
        for name, value in (
            ("previous_job_id", self.previous_job_id),
            ("upscale_factor", self.upscale_factor),
            ("creativity", self.creativity),
        ):
            if value is not None:
                payload[name] = value
        if self.provider_options:
            provider_options: dict[str, dict[str, object]] = {}
            for option in self.provider_options:
                provider_values = provider_options.setdefault(option.provider, {})
                if option.container == "parameters":
                    parameters = provider_values.setdefault("parameters", {})
                    if not isinstance(parameters, dict):
                        raise ValueError(
                            "Direct 'parameters' option conflicts with nested parameters."
                        )
                    destination = parameters
                else:
                    destination = provider_values
                _insert_provider_leaf(destination, (option.key, *option.path), option.value)
            _check_provider_tree(provider_options)
            payload["provider"] = {"options": provider_options}
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
    supports_text_only: bool | None = None
    source_required: bool | None = None
    evidence_facts: tuple[CapabilityFact, ...] = ()
    unmapped_capability_keys: tuple[str, ...] = ()


class CapabilityFactState(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class CapabilityFact:
    """Exact-model data provenance; unknown facts never become denials."""

    model_id: str
    key: str
    value: object
    state: CapabilityFactState
    authority: str
    source_reference: str
    observed_at: str
    scope: str
    artifact_version: str
    conflicting_evidence: tuple[object, ...] = ()


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


def request_fingerprint_v4(request: GenerationRequest) -> str:
    """Bind extended structural intent while preserving v3 for legacy requests."""

    if (
        request.previous_job_id is None
        and request.upscale_factor is None
        and request.creativity is None
        and not request.provider_options
    ):
        return request_fingerprint_v3(request)
    payload: dict[str, object] = {"schema": 4, "base": request_fingerprint_v3(request)}
    if request.previous_job_id is not None:
        payload["previous_job_id_sha256"] = hashlib.sha256(
            request.previous_job_id.encode("utf-8")
        ).hexdigest()
    if request.upscale_factor is not None:
        payload["upscale_factor"] = request.upscale_factor
    if request.creativity is not None:
        payload["creativity"] = request.creativity
    if request.provider_options:
        payload["provider_options"] = [
            {
                "provider": option.provider,
                "container": option.container,
                "key": option.key,
                "value": ("present" if isinstance(option.value, str) else option.value),
                **({"path": option.path} if option.path else {}),
            }
            for option in request.provider_options
        ]
    canonical_bytes = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"v4:{hashlib.sha256(canonical_bytes).hexdigest()}"


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
    "ProviderOption",
    "PricingEvidence",
    "PricingSku",
    "RemoteJobSnapshot",
    "UsageCost",
    "VideoArtifact",
    "request_fingerprint_v1",
    "request_fingerprint_v2",
    "request_fingerprint_v3",
    "request_fingerprint_v4",
)
