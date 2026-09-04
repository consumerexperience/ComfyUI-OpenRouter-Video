from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.errors import ProductFailureError, TransportError
from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    ModelCapabilities,
    ProductErrorCode,
)
from openrouter_video.persistence import JobStore

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
        generate_audio=True,
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
