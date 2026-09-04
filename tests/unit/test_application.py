from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from openrouter_video.application import GenerateService, ResumeService
from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.errors import OpenRouterHTTPError, RequestPolicyError, TransportError
from openrouter_video.media import DownloadService
from openrouter_video.models import (
    GenerationRequest,
    LocalLifecycleState,
    ModelCapabilities,
    ProductErrorCode,
    RemoteJobSnapshot,
    UsageCost,
    request_fingerprint_v1,
)
from openrouter_video.persistence import JobStore
from openrouter_video.policy import Operation

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
MODEL = ModelCapabilities(model_id="vendor/model")
REQUEST = GenerationRequest("vendor/model", "private prompt")


class DiscoveryStub:
    async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
        return (MODEL,)


class ScenarioClient:
    def __init__(
        self,
        *,
        submit: RemoteJobSnapshot | BaseException,
        polls: list[RemoteJobSnapshot | BaseException],
        content: bytes = MP4,
    ) -> None:
        self.submit_outcome = submit
        self.polls = polls
        self.content = content
        self.submit_calls = 0
        self.poll_calls = 0
        self.content_calls = 0

    async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot:
        assert request.model == "vendor/model"
        self.submit_calls += 1
        if isinstance(self.submit_outcome, BaseException):
            raise self.submit_outcome
        return self.submit_outcome

    async def get_job(self, job_id: str) -> RemoteJobSnapshot:
        assert job_id == "job-1"
        outcome = self.polls[min(self.poll_calls, len(self.polls) - 1)]
        self.poll_calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @asynccontextmanager
    async def stream_content(self, job_id: str) -> AsyncIterator[httpx.Response]:
        assert job_id == "job-1"
        self.content_calls += 1
        request = httpx.Request("GET", "https://openrouter.ai/api/v1/videos/job-1/content")
        yield httpx.Response(200, content=self.content, request=request)


class ObservationOnlyClient:
    def __init__(self, status: str = "completed") -> None:
        self.status = status
        self.poll_calls = 0
        self.content_calls = 0

    async def get_job(self, job_id: str) -> RemoteJobSnapshot:
        self.poll_calls += 1
        return RemoteJobSnapshot(job_id, self.status)

    @asynccontextmanager
    async def stream_content(self, job_id: str) -> AsyncIterator[httpx.Response]:
        self.content_calls += 1
        request = httpx.Request("GET", f"https://openrouter.ai/api/v1/videos/{job_id}/content")
        yield httpx.Response(200, content=MP4, request=request)


async def _no_sleep(_: float) -> None:
    return None


def _generate_service(tmp_path: Path, client: ScenarioClient) -> tuple[GenerateService, JobStore]:
    store = JobStore(tmp_path / "jobs.sqlite3")
    capabilities = CapabilityService(
        client=DiscoveryStub(),
        store=store,
        sleep=_no_sleep,
        now=lambda: NOW,
        jitter=lambda value: value,
    )
    downloader = DownloadService(
        client=client,
        output_root=tmp_path / "output",
        sleep=_no_sleep,
        jitter=lambda value: value,
    )
    service = GenerateService(
        capabilities=capabilities,
        validator=RequestValidator(),
        store=store,
        submit_client=client,
        observation_client=client,
        downloader=downloader,
        sleep=_no_sleep,
        now=lambda: NOW,
        monotonic=lambda: 0.0,
        jitter=lambda value: value,
    )
    return service, store


def test_generate_happy_path_has_one_total_post_and_durable_artifact(tmp_path: Path) -> None:
    client = ScenarioClient(
        submit=RemoteJobSnapshot("job-1", "pending"),
        polls=[RemoteJobSnapshot("job-1", "completed", usage=UsageCost(Decimal("0.25")))],
    )
    service, store = _generate_service(tmp_path, client)

    result = asyncio.run(service.generate("operation-1", REQUEST))

    assert result.state is LocalLifecycleState.DONE
    assert result.artifact is not None and result.artifact.path.exists()
    assert result.actual_cost_usd == Decimal("0.25")
    assert client.submit_calls == 1
    assert store.get_by_operation_id("operation-1") == store.get_by_job_id("job-1")


def test_ambiguous_submit_is_durable_and_restart_adds_zero_posts(tmp_path: Path) -> None:
    client = ScenarioClient(submit=TransportError("ambiguous"), polls=[])
    service, store = _generate_service(tmp_path, client)

    first = asyncio.run(service.generate("operation-1", REQUEST))
    second = asyncio.run(service.generate("operation-1", REQUEST))

    assert first.state is LocalLifecycleState.SUBMISSION_UNKNOWN
    assert second.state is LocalLifecycleState.SUBMISSION_UNKNOWN
    assert client.submit_calls == 1
    persisted = store.get_by_operation_id("operation-1")
    assert persisted is not None
    assert persisted.local_state is LocalLifecycleState.SUBMISSION_UNKNOWN


def test_definite_rejection_is_durable_and_never_resubmitted(tmp_path: Path) -> None:
    client = ScenarioClient(
        submit=OpenRouterHTTPError(402, Operation.SUBMIT),
        polls=[],
    )
    service, store = _generate_service(tmp_path, client)

    first = asyncio.run(service.generate("operation-1", REQUEST))
    second = asyncio.run(service.generate("operation-1", REQUEST))

    assert first.state is LocalLifecycleState.SUBMIT_REJECTED
    assert first.error is not None and first.error.code is ProductErrorCode.INSUFFICIENT_CREDITS
    assert second.state is LocalLifecycleState.SUBMIT_REJECTED
    assert client.submit_calls == 1
    persisted = store.get_by_operation_id("operation-1")
    assert persisted is not None
    assert persisted.product_error_code is ProductErrorCode.INSUFFICIENT_CREDITS


def test_submit_429_is_one_total_post_and_terminal_rejection(tmp_path: Path) -> None:
    client = ScenarioClient(submit=OpenRouterHTTPError(429, Operation.SUBMIT), polls=[])
    service, _ = _generate_service(tmp_path, client)

    result = asyncio.run(service.generate("operation-1", REQUEST))

    assert result.state is LocalLifecycleState.SUBMIT_REJECTED
    assert result.error is not None and result.error.code is ProductErrorCode.RATE_LIMITED_SUBMIT
    assert client.submit_calls == 1


def test_polling_outage_preserves_known_job_and_total_post_count(tmp_path: Path) -> None:
    client = ScenarioClient(
        submit=RemoteJobSnapshot("job-1", "pending"),
        polls=[TransportError("poll")],
    )
    service, _ = _generate_service(tmp_path, client)

    result = asyncio.run(service.generate("operation-1", REQUEST))

    assert result.state is LocalLifecycleState.OBSERVATION_INTERRUPTED
    assert result.job_id == "job-1"
    assert client.submit_calls == 1
    assert client.poll_calls == 5


def test_restart_after_accepted_job_adds_zero_posts_and_keeps_lifecycle_total_one(
    tmp_path: Path,
) -> None:
    client = ScenarioClient(
        submit=RemoteJobSnapshot("job-1", "pending"),
        polls=[TransportError("poll")],
    )
    generate, store = _generate_service(tmp_path, client)
    interrupted = asyncio.run(generate.generate("operation-1", REQUEST))
    assert interrupted.state is LocalLifecycleState.OBSERVATION_INTERRUPTED
    assert client.submit_calls == 1

    client.polls = [RemoteJobSnapshot("job-1", "completed")]
    client.poll_calls = 0
    resume = ResumeService(
        observation_client=client,
        store=store,
        downloader=DownloadService(
            client=client,
            output_root=tmp_path / "output",
            sleep=_no_sleep,
        ),
        sleep=_no_sleep,
        now=lambda: NOW,
        monotonic=lambda: 0.0,
    )
    recovered = asyncio.run(resume.resume("job-1"))

    assert recovered.state is LocalLifecycleState.DONE
    assert client.submit_calls == 1


def test_unknown_remote_status_is_preserved_without_additional_post(tmp_path: Path) -> None:
    client = ScenarioClient(
        submit=RemoteJobSnapshot("job-1", "pending"),
        polls=[RemoteJobSnapshot("job-1", "provider_future_state")],
    )
    service, store = _generate_service(tmp_path, client)

    result = asyncio.run(service.generate("operation-1", REQUEST))

    assert result.state is LocalLifecycleState.UNKNOWN_REMOTE_STATE
    assert result.error is not None and result.error.code is ProductErrorCode.UNKNOWN_REMOTE_STATE
    assert client.submit_calls == 1
    persisted = store.get_by_job_id("job-1")
    assert persisted is not None
    assert persisted.remote_status_raw == "provider_future_state"


def test_prompt_change_same_fingerprint_reconciles_existing_operation(tmp_path: Path) -> None:
    client = ScenarioClient(submit=TransportError("ambiguous"), polls=[])
    service, _ = _generate_service(tmp_path, client)
    changed_prompt = GenerationRequest("vendor/model", "different private prompt")
    assert request_fingerprint_v1(REQUEST) == request_fingerprint_v1(changed_prompt)

    asyncio.run(service.generate("operation-1", REQUEST))
    result = asyncio.run(service.generate("operation-1", changed_prompt))

    assert result.state is LocalLifecycleState.SUBMISSION_UNKNOWN
    assert client.submit_calls == 1


def test_fingerprint_mismatch_is_local_state_error_and_never_submits(tmp_path: Path) -> None:
    client = ScenarioClient(submit=TransportError("ambiguous"), polls=[])
    service, _ = _generate_service(tmp_path, client)
    asyncio.run(service.generate("operation-1", REQUEST))

    result = asyncio.run(
        service.generate("operation-1", GenerationRequest("vendor/model", "prompt", duration=5))
    )

    assert result.error is not None and result.error.code is ProductErrorCode.LOCAL_STATE_CORRUPT
    assert client.submit_calls == 1


def test_resume_unknown_job_has_no_submit_capability_or_post(tmp_path: Path) -> None:
    client = ObservationOnlyClient()
    store = JobStore(tmp_path / "jobs.sqlite3")
    downloader = DownloadService(client=client, output_root=tmp_path / "output", sleep=_no_sleep)
    service = ResumeService(
        observation_client=client,
        store=store,
        downloader=downloader,
        sleep=_no_sleep,
        now=lambda: NOW,
        monotonic=lambda: 0.0,
    )

    result = asyncio.run(service.resume("job-1"))

    assert result.state is LocalLifecycleState.DONE
    assert client.poll_calls == 1
    assert client.content_calls == 1
    assert not hasattr(service, "submit_video")
    assert store.get_by_job_id("job-1") is not None


def test_corrupt_state_adds_zero_posts(tmp_path: Path) -> None:
    client = ScenarioClient(submit=RemoteJobSnapshot("job-1", "pending"), polls=[])
    service, store = _generate_service(tmp_path, client)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                schema_version, operation_id, request_fingerprint, model,
                local_state, created_at
            ) VALUES (1, ?, ?, ?, 'BROKEN', ?)
            """,
            (
                "operation-1",
                request_fingerprint_v1(REQUEST),
                "vendor/model",
                NOW.isoformat(),
            ),
        )
        connection.commit()

    result = asyncio.run(service.generate("operation-1", REQUEST))

    assert result.error is not None and result.error.code is ProductErrorCode.LOCAL_STATE_CORRUPT
    assert client.submit_calls == 0


def test_two_concurrent_generate_calls_share_one_submit_right(tmp_path: Path) -> None:
    class BlockingClient(ScenarioClient):
        def __init__(self) -> None:
            super().__init__(
                submit=RemoteJobSnapshot("job-1", "pending"),
                polls=[RemoteJobSnapshot("job-1", "completed")],
            )
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot:
            self.submit_calls += 1
            self.started.set()
            await self.release.wait()
            assert not isinstance(self.submit_outcome, BaseException)
            return self.submit_outcome

    async def scenario() -> tuple[LocalLifecycleState, LocalLifecycleState, int]:
        client = BlockingClient()
        service, _ = _generate_service(tmp_path, client)
        winner = asyncio.create_task(service.generate("operation-1", REQUEST))
        await client.started.wait()
        loser = await service.generate("operation-1", REQUEST)
        client.release.set()
        completed = await winner
        return completed.state, loser.state, client.submit_calls

    winner_state, loser_state, submit_calls = asyncio.run(scenario())
    assert winner_state is LocalLifecycleState.DONE
    assert loser_state is LocalLifecycleState.SUBMISSION_UNKNOWN
    assert submit_calls == 1


def test_missing_key_failure_occurs_before_submit_claim(tmp_path: Path) -> None:
    class MissingKeyDiscovery:
        async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
            raise RequestPolicyError("OpenRouter API credential is not configured")

    client = ScenarioClient(submit=RemoteJobSnapshot("job-1", "pending"), polls=[])
    store = JobStore(tmp_path / "jobs.sqlite3")
    capabilities = CapabilityService(client=MissingKeyDiscovery(), store=store, now=lambda: NOW)
    service = GenerateService(
        capabilities=capabilities,
        validator=RequestValidator(),
        store=store,
        submit_client=client,
        observation_client=client,
        downloader=DownloadService(client=client, output_root=tmp_path / "output"),
        sleep=_no_sleep,
        now=lambda: NOW,
        monotonic=lambda: 0.0,
    )

    result = asyncio.run(service.generate("operation-1", REQUEST))

    assert result.error is not None and result.error.code is ProductErrorCode.API_KEY_MISSING
    assert client.submit_calls == 0
    assert store.get_by_operation_id("operation-1") is None
