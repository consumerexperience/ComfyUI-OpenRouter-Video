from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openrouter_video.capabilities import (
    CapabilityModeStatus,
    CapabilityService,
    RequestValidator,
    infer_legacy_inference_method,
    inference_method_matrix,
    mode_enforcement_matrix,
)
from openrouter_video.capability_overlays import (
    SEEDANCE_2_5_OVERLAY,
    apply_capability_overlay,
    preferred_inference_method,
)
from openrouter_video.errors import OpenRouterHTTPError, ProductFailureError, TransportError
from openrouter_video.models import (
    CapabilityEvidenceSource,
    FrameReference,
    FrameType,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCapabilities,
    InputReferenceCapabilityField,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
    ProductErrorCode,
)
from openrouter_video.persistence import JobStore
from openrouter_video.policy import Operation

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
MODEL = ModelCapabilities(
    model_id="vendor/model",
    supported_durations=(5, 8),
    supported_resolutions=("720p",),
    supported_aspect_ratios=("16:9",),
    supported_sizes=("1280x720",),
    supported_frame_types=frozenset({FrameType.FIRST}),
    generate_audio=True,
    supports_seed=False,
)


class DiscoveryStub:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, tuple)
        return outcome


def test_fresh_cache_avoids_discovery(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.replace_capability_catalog((MODEL,), NOW)
    client = DiscoveryStub([])
    service = CapabilityService(client=client, store=store, now=lambda: NOW + timedelta(minutes=14))

    assert asyncio.run(service.resolve("vendor/model")) == MODEL
    assert client.calls == 0


def test_successful_live_catalog_beats_stale_lkg(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.replace_capability_catalog((MODEL,), NOW - timedelta(hours=1))
    client = DiscoveryStub([tuple()])
    service = CapabilityService(client=client, store=store, now=lambda: NOW)

    with pytest.raises(ProductFailureError) as caught:
        asyncio.run(service.resolve("vendor/model"))
    assert caught.value.error.code is ProductErrorCode.MODEL_UNAVAILABLE
    assert client.calls == 1


def test_discovery_retries_three_total_then_uses_bounded_lkg(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.replace_capability_catalog((MODEL,), NOW - timedelta(hours=1))
    client = DiscoveryStub([TransportError("x"), TransportError("x"), TransportError("x")])
    sleeps: list[float] = []

    async def sleep(value: float) -> None:
        sleeps.append(value)

    service = CapabilityService(
        client=client,
        store=store,
        now=lambda: NOW,
        sleep=sleep,
        jitter=lambda value: value,
    )

    assert asyncio.run(service.resolve("vendor/model")) == MODEL
    assert client.calls == 3
    assert sleeps == [5.0, 10.0]


def test_expired_lkg_fails_without_submit_context(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.replace_capability_catalog((MODEL,), NOW - timedelta(hours=25))
    client = DiscoveryStub([TransportError("x"), TransportError("x"), TransportError("x")])

    async def sleep(_: float) -> None:
        return None

    service = CapabilityService(
        client=client,
        store=store,
        now=lambda: NOW,
        sleep=sleep,
        jitter=lambda value: value,
    )

    with pytest.raises(ProductFailureError) as caught:
        asyncio.run(service.catalog())
    assert caught.value.error.code is ProductErrorCode.DISCOVERY_UNAVAILABLE


def test_discovery_auth_rejection_maps_to_api_key_invalid(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    client = DiscoveryStub([OpenRouterHTTPError(401, Operation.DISCOVERY)])
    service = CapabilityService(client=client, store=store, now=lambda: NOW)

    with pytest.raises(ProductFailureError) as caught:
        asyncio.run(service.catalog())
    assert caught.value.error.code is ProductErrorCode.API_KEY_INVALID
    assert client.calls == 1


def test_validator_enforces_geometry_and_public_https_media() -> None:
    validator = RequestValidator()
    invalid_requests = (
        GenerationRequest("vendor/model", "prompt", size="1280x720", resolution="720p"),
        GenerationRequest(
            "vendor/model",
            "prompt",
            first_frame=FrameReference(FrameType.FIRST, "http://assets.example/frame.png"),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            first_frame=FrameReference(FrameType.FIRST, "https://127.0.0.1/frame.png"),
        ),
    )

    for request in invalid_requests:
        with pytest.raises(ProductFailureError):
            validator.validate_shape(request)


def test_validator_requires_positive_frame_and_audio_capability() -> None:
    validator = RequestValidator()
    request = GenerationRequest(
        "vendor/model",
        "prompt",
        inference_method=InferenceMethod.FLF2V,
        generate_audio=True,
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/first.png"),
        last_frame=FrameReference(FrameType.LAST, "https://assets.example/frame.png"),
    )
    validator.validate_shape(request)

    with pytest.raises(ProductFailureError) as caught:
        validator.validate_capabilities(request, replace(MODEL, generate_audio=None))
    assert caught.value.error.code is ProductErrorCode.UNSUPPORTED_PARAMETER

    with pytest.raises(ProductFailureError):
        validator.validate_capabilities(request, MODEL)


def test_validator_never_silently_changes_explicit_options() -> None:
    validator = RequestValidator()
    request = GenerationRequest("vendor/model", "prompt", duration=6, resolution="1080p", seed=1)
    validator.validate_shape(request)

    with pytest.raises(ProductFailureError):
        validator.validate_capabilities(request, MODEL)
    assert request.duration == 6
    assert request.resolution == "1080p"
    assert request.seed == 1


def test_mode_matrix_scopes_frame_readiness_and_reference_signal_gaps() -> None:
    matrix = inference_method_matrix(MODEL)

    assert matrix[InferenceMethod.T2V] is CapabilityModeStatus.READY
    assert matrix[InferenceMethod.I2V] is CapabilityModeStatus.READY
    assert matrix[InferenceMethod.FLF2V] is CapabilityModeStatus.UNSUPPORTED
    both_frames = inference_method_matrix(
        replace(MODEL, supported_frame_types=frozenset({FrameType.FIRST, FrameType.LAST}))
    )
    assert both_frames[InferenceMethod.FLF2V] is CapabilityModeStatus.READY
    for method in (
        InferenceMethod.IR2V,
        InferenceMethod.MI2V,
        InferenceMethod.VR2V,
        InferenceMethod.AR2V,
        InferenceMethod.MMR2V,
        InferenceMethod.V2V_EDIT,
        InferenceMethod.V2V_EXTEND,
    ):
        assert matrix[method] is CapabilityModeStatus.CAPABILITY_SIGNAL_GAP
    assert mode_enforcement_matrix(MODEL) == matrix


def test_exact_id_overlay_makes_only_proven_reference_modes_ready() -> None:
    model = apply_capability_overlay(
        ModelCapabilities(
            model_id="bytedance/seedance-2.5",
            canonical_slug="bytedance/seedance-2.5",
            supported_frame_types=frozenset({FrameType.FIRST, FrameType.LAST}),
        )
    )
    references = model.input_reference_capabilities
    assert references is not None
    assert references.reference_kinds == frozenset(
        {InputReferenceKind.IMAGE, InputReferenceKind.VIDEO, InputReferenceKind.AUDIO}
    )
    assert references.max_reference_count == 50
    assert references.mixed_reference_kinds is True
    assert references.reference_kinds_source is CapabilityEvidenceSource.EVIDENCE_OVERLAY
    assert not references.conflicts
    assert apply_capability_overlay(model) == model
    matrix = inference_method_matrix(model)
    for method in InferenceMethod:
        assert matrix[method] is CapabilityModeStatus.READY
    assert preferred_inference_method(model.model_id) is InferenceMethod.MI2V


def test_overlay_is_exact_id_data_not_provider_family_inference() -> None:
    near_matches = (
        ModelCapabilities("bytedance/seedance-2.5-fast"),
        ModelCapabilities("bytedance/seedance-2.0"),
        ModelCapabilities("another/seedance-2.5"),
    )
    assert all(apply_capability_overlay(model) == model for model in near_matches)
    assert SEEDANCE_2_5_OVERLAY.model_id == "bytedance/seedance-2.5"


def test_level_a_is_never_overridden_and_conflicts_fail_closed() -> None:
    level_a = InputReferenceCapabilities(
        reference_kinds=frozenset({InputReferenceKind.IMAGE}),
        max_reference_count=4,
        mixed_reference_kinds=False,
    )
    model = apply_capability_overlay(
        ModelCapabilities(
            "bytedance/seedance-2.5",
            input_reference_capabilities=level_a,
        )
    )
    effective = model.input_reference_capabilities
    assert effective is not None
    assert effective.reference_kinds == level_a.reference_kinds
    assert effective.max_reference_count == 4
    assert effective.mixed_reference_kinds is False
    assert effective.reference_kinds_source is CapabilityEvidenceSource.LEVEL_A
    assert effective.conflicts == frozenset(InputReferenceCapabilityField)
    matrix = inference_method_matrix(model)
    assert matrix[InferenceMethod.MI2V] is CapabilityModeStatus.CONFLICT
    assert matrix[InferenceMethod.VR2V] is CapabilityModeStatus.CONFLICT
    assert matrix[InferenceMethod.MMR2V] is CapabilityModeStatus.CONFLICT


def test_overlay_requires_a_fresh_catalog_observation(tmp_path: Path) -> None:
    model = ModelCapabilities("bytedance/seedance-2.5")
    store = JobStore(tmp_path / "jobs.sqlite3")
    store.replace_capability_catalog((model,), NOW - timedelta(hours=1))
    client = DiscoveryStub([TransportError("x"), TransportError("x"), TransportError("x")])

    async def sleep(_: float) -> None:
        return None

    service = CapabilityService(
        client=client,
        store=store,
        now=lambda: NOW,
        sleep=sleep,
        jitter=lambda value: value,
    )

    assert asyncio.run(service.resolve(model.model_id)) == model


def test_reference_validation_is_https_order_preserving_and_fail_closed() -> None:
    validator = RequestValidator()
    references = InputReferenceCollection(
        (
            InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png"),
            InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png"),
        )
    )
    request = GenerationRequest(
        "vendor/model",
        "prompt",
        inference_method=InferenceMethod.MI2V,
        input_references=references,
    )
    validator.validate_shape(request)

    with pytest.raises(ProductFailureError) as caught:
        validator.validate_capabilities(request, MODEL)
    assert caught.value.error.code is ProductErrorCode.CAPABILITY_SIGNAL_GAP
    assert caught.value.error.billing_context.value == "NO_SUBMIT"

    invalid = replace(
        request,
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, "http://assets.example/a.mp4"),)
        ),
    )
    with pytest.raises(ProductFailureError) as invalid_caught:
        validator.validate_shape(invalid)
    assert invalid_caught.value.error.code is ProductErrorCode.INVALID_MEDIA_URL


def test_frame_and_reference_conflict_fails_before_capability_resolution() -> None:
    validator = RequestValidator()
    request = GenerationRequest(
        "vendor/model",
        "prompt",
        inference_method=InferenceMethod.I2V,
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/frame.png"),
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, "https://assets.example/reference.mp4"),)
        ),
    )

    with pytest.raises(ProductFailureError) as caught:
        validator.validate_shape(request)
    assert caught.value.error.code is ProductErrorCode.UNSUPPORTED_PARAMETER


def test_prompt_omission_is_outside_the_phase_8_product_contract() -> None:
    validator = RequestValidator()
    request = GenerationRequest(
        "vendor/model",
        None,
        inference_method=InferenceMethod.VR2V,
        input_references=InputReferenceCollection(
            (InputReference(InputReferenceKind.VIDEO, "https://assets.example/reference.mp4"),)
        ),
    )
    with pytest.raises(ProductFailureError) as caught:
        validator.validate_shape(request)
    assert caught.value.error.code is ProductErrorCode.UNSUPPORTED_PARAMETER


def test_reference_count_above_overlay_limit_is_rejected() -> None:
    validator = RequestValidator()
    model = apply_capability_overlay(ModelCapabilities("bytedance/seedance-2.5"))
    references = InputReferenceCollection(
        tuple(
            InputReference(InputReferenceKind.IMAGE, f"https://assets.example/{index}.png")
            for index in range(51)
        )
    )
    request = GenerationRequest(
        model.model_id,
        "prompt",
        inference_method=InferenceMethod.MI2V,
        input_references=references,
    )

    validator.validate_shape(request)
    with pytest.raises(ProductFailureError) as caught:
        validator.validate_capabilities(request, model)
    assert caught.value.error.code is ProductErrorCode.UNSUPPORTED_PARAMETER


def test_method_topologies_and_legacy_migration_preserve_intent() -> None:
    validator = RequestValidator()
    image = InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png")
    video = InputReference(InputReferenceKind.VIDEO, "https://assets.example/a.mp4")
    audio = InputReference(InputReferenceKind.AUDIO, "https://assets.example/a.mp3")
    first = FrameReference(FrameType.FIRST, "https://assets.example/first.png")
    last = FrameReference(FrameType.LAST, "https://assets.example/last.png")
    valid = (
        GenerationRequest("vendor/model", "prompt", InferenceMethod.T2V),
        GenerationRequest("vendor/model", "prompt", InferenceMethod.I2V, first_frame=first),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.FLF2V,
            first_frame=first,
            last_frame=last,
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.IR2V,
            input_references=InputReferenceCollection((image,)),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.MI2V,
            input_references=InputReferenceCollection((image, image)),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.VR2V,
            input_references=InputReferenceCollection((video,)),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.AR2V,
            input_references=InputReferenceCollection((audio,)),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.MMR2V,
            input_references=InputReferenceCollection((image, audio, video)),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.V2V_EDIT,
            source_video=video,
            input_references=InputReferenceCollection((audio, image)),
        ),
        GenerationRequest(
            "vendor/model",
            "prompt",
            InferenceMethod.V2V_EXTEND,
            source_video=video,
        ),
    )
    for request in valid:
        validator.validate_shape(request)

    assert (
        infer_legacy_inference_method(first_frame=None, last_frame=None, references=(video,))
        is InferenceMethod.VR2V
    )
    assert (
        infer_legacy_inference_method(first_frame=None, last_frame=None, references=(image,))
        is InferenceMethod.IR2V
    )
    assert (
        infer_legacy_inference_method(first_frame=None, last_frame=None, references=(image, audio))
        is InferenceMethod.MMR2V
    )
