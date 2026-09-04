"""Release-critical billing, recovery, concurrency, and ambiguity fitness."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from openrouter_video.application import GenerateService
from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.client import OpenRouterVideoClient
from openrouter_video.media import DownloadService
from openrouter_video.models import (
    GenerationRequest,
    LocalLifecycleState,
    ModelCapabilities,
    ProductErrorCode,
)
from openrouter_video.persistence import JobStore
from openrouter_video.policy import Operation
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport
from tests.fixtures.identity import EXPECTED_RELEASE_IDENTITY
from tests.harness.core import FIXED_NOW, FakeTime, SyntheticSecretProvider, core_harness
from tests.harness.mock_server import LocalFaultServer, ResponsePlan
from tests.harness.scenario import LoopbackRewriteTransport, Scenario, ScenarioStep

FIXTURES = Path(__file__).parents[1] / "fixtures" / "openrouter_video"
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
REQUEST = GenerationRequest("test/video-alpha", "SYNTHETIC_PRIVATE_PROMPT", duration=4)


def _json(relative: str) -> object:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def _prefix() -> list[ScenarioStep]:
    return [
        ScenarioStep(
            Operation.DISCOVERY,
            "GET",
            "/api/v1/videos/models",
            json_body=_json("discovery/catalog.json"),
        ),
        ScenarioStep(
            Operation.SUBMIT,
            "POST",
            "/api/v1/videos",
            status=202,
            json_body=_json("submit/accepted.json"),
        ),
    ]


def _completed_steps() -> list[ScenarioStep]:
    return [
        ScenarioStep(
            Operation.POLL,
            "GET",
            "/api/v1/videos/job_123",
            json_body=_json("poll/completed_cost.json"),
        ),
        ScenarioStep(
            Operation.CONTENT,
            "GET",
            "/api/v1/videos/job_123/content?index=0",
            body=MP4,
        ),
    ]


@pytest.mark.parametrize(
    "fault",
    [
        httpx.ReadTimeout("synthetic timeout"),
        httpx.ReadError("synthetic disconnect"),
        429,
        500,
        502,
        503,
    ],
    ids=["timeout", "disconnect", "429", "500", "502", "503"],
)
def test_poll_failure_must_not_create_generation(
    fault: httpx.HTTPError | int, tmp_path: Path
) -> None:
    if isinstance(fault, int):
        step = ScenarioStep(
            Operation.POLL,
            "GET",
            "/api/v1/videos/job_123",
            status=fault,
            headers={"Retry-After": "7"} if fault == 429 else {},
        )
    else:
        step = ScenarioStep(
            Operation.POLL,
            "GET",
            "/api/v1/videos/job_123",
            exception=fault,
        )
    scenario = Scenario("poll-failure-does-not-generate", _prefix() + [step] + _completed_steps())

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-poll-recovery", REQUEST)
            assert result.state is LocalLifecycleState.DONE
            assert result.job_id == "job_123"

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)


def test_poll_retry_exhaustion_is_observation_interrupted_then_resume_zero_post(
    tmp_path: Path,
) -> None:
    failed = Scenario(
        "poll-exhaustion",
        _prefix()
        + [
            ScenarioStep(Operation.POLL, "GET", "/api/v1/videos/job_123", status=500)
            for _ in range(5)
        ],
    )
    database = tmp_path / "jobs.sqlite3"

    async def first_run() -> None:
        async with core_harness(failed, tmp_path, database=database) as core:
            result = await core.generate.generate("operation-restart", REQUEST)
            assert result.state is LocalLifecycleState.OBSERVATION_INTERRUPTED
            assert result.job_id == "job_123"
            assert result.error is not None
            assert result.error.code is ProductErrorCode.STATUS_CHECK_FAILED
            assert core.clock.delays == [5.0, 10.0, 20.0, 30.0]

    asyncio.run(first_run())
    failed.assert_complete()
    failed.ledger.assert_generation_submit_count(1)

    resumed = Scenario("resume-after-restart", _completed_steps())

    async def second_run() -> None:
        async with core_harness(resumed, tmp_path, database=database) as core:
            result = await core.resume.resume("job_123")
            assert result.state is LocalLifecycleState.DONE
            assert result.job_id == "job_123"

    asyncio.run(second_run())
    resumed.assert_complete()
    resumed.ledger.assert_resume_submits_zero()


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, ProductErrorCode.UNSUPPORTED_PARAMETER),
        (401, ProductErrorCode.API_KEY_INVALID),
        (402, ProductErrorCode.INSUFFICIENT_CREDITS),
        (404, ProductErrorCode.MODEL_UNAVAILABLE),
        (429, ProductErrorCode.RATE_LIMITED_SUBMIT),
    ],
)
def test_definite_submit_rejection_is_durable_and_restart_submits_zero(
    status: int, code: ProductErrorCode, tmp_path: Path
) -> None:
    rejected = Scenario(
        f"submit-{status}",
        [
            _prefix()[0],
            ScenarioStep(Operation.SUBMIT, "POST", "/api/v1/videos", status=status),
        ],
    )
    database = tmp_path / "jobs.sqlite3"

    async def first_run() -> None:
        async with core_harness(rejected, tmp_path, database=database) as core:
            result = await core.generate.generate("operation-rejected", REQUEST)
            assert result.state is LocalLifecycleState.SUBMIT_REJECTED
            assert result.job_id is None
            assert result.error is not None and result.error.code is code

    asyncio.run(first_run())
    rejected.assert_complete()
    rejected.ledger.assert_generation_submit_count(1)

    restart = Scenario("rejected-restart", [])

    async def second_run() -> None:
        async with core_harness(restart, tmp_path, database=database) as core:
            result = await core.generate.generate("operation-rejected", REQUEST)
            assert result.state is LocalLifecycleState.SUBMIT_REJECTED

    asyncio.run(second_run())
    restart.assert_complete()
    restart.ledger.assert_no_additional_generation_submit(0)


def test_unknown_remote_status_preserves_job_and_submits_no_additional_generation(
    tmp_path: Path,
) -> None:
    scenario = Scenario(
        "future-status",
        _prefix()
        + [
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/future_unknown.json"),
            )
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-unknown", REQUEST)
            assert result.state is LocalLifecycleState.UNKNOWN_REMOTE_STATE
            assert result.job_id == "job_123"
            assert result.error is not None
            assert result.error.code is ProductErrorCode.UNKNOWN_REMOTE_STATE

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)


@pytest.mark.parametrize(
    ("fixture", "state", "code"),
    [
        ("poll/failed.json", LocalLifecycleState.FAILED, ProductErrorCode.GENERATION_FAILED),
        ("poll/cancelled.json", LocalLifecycleState.CANCELLED, ProductErrorCode.JOB_CANCELLED),
        ("poll/expired.json", LocalLifecycleState.EXPIRED, ProductErrorCode.JOB_EXPIRED),
    ],
)
def test_remote_terminal_outcomes_remain_distinct_from_transport_failure(
    fixture: str,
    state: LocalLifecycleState,
    code: ProductErrorCode,
    tmp_path: Path,
) -> None:
    scenario = Scenario(
        fixture,
        _prefix()
        + [
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json(fixture),
            )
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate(f"operation-{state.value.lower()}", REQUEST)
            assert result.state is state
            assert result.job_id == "job_123"
            assert result.error is not None and result.error.code is code

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)


def test_download_failure_exhaustion_is_recoverable_and_never_generates(tmp_path: Path) -> None:
    failed = Scenario(
        "download-failure",
        _prefix()
        + [
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/completed_no_cost.json"),
            )
        ]
        + [
            ScenarioStep(
                Operation.CONTENT,
                "GET",
                "/api/v1/videos/job_123/content?index=0",
                status=502,
            )
            for _ in range(3)
        ],
    )
    database = tmp_path / "jobs.sqlite3"

    async def first_run() -> None:
        async with core_harness(failed, tmp_path, database=database) as core:
            result = await core.generate.generate("operation-download", REQUEST)
            assert result.state is LocalLifecycleState.OBSERVATION_INTERRUPTED
            assert result.job_id == "job_123"
            assert result.artifact is None
            assert not tuple((tmp_path / "output").glob("*.part"))

    asyncio.run(first_run())
    failed.assert_complete()
    failed.ledger.assert_generation_submit_count(1)

    resumed = Scenario(
        "download-resume",
        [
            ScenarioStep(
                Operation.CONTENT,
                "GET",
                "/api/v1/videos/job_123/content?index=0",
                body=MP4,
            )
        ],
    )

    async def second_run() -> None:
        async with core_harness(resumed, tmp_path, database=database) as core:
            result = await core.resume.resume("job_123")
            assert result.state is LocalLifecycleState.DONE

    asyncio.run(second_run())
    resumed.assert_complete()
    resumed.ledger.assert_resume_submits_zero()


@pytest.mark.parametrize("redirect_status", [302, 307, 308])
def test_content_redirect_is_not_followed_and_cannot_leak_headers(
    redirect_status: int, tmp_path: Path
) -> None:
    scenario = Scenario(
        "content-redirect",
        _prefix()
        + [
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/completed_no_cost.json"),
            ),
            ScenarioStep(
                Operation.CONTENT,
                "GET",
                "/api/v1/videos/job_123/content?index=0",
                status=redirect_status,
                headers={"Location": "https://example.invalid/steal"},
            ),
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-redirect", REQUEST)
            assert result.state is LocalLifecycleState.OBSERVATION_INTERRUPTED

    asyncio.run(run())
    scenario.assert_complete()
    assert scenario.ledger.total_requests == 4
    assert all("example.invalid" not in item.canonical_path for item in scenario.ledger.requests)
    scenario.ledger.assert_generation_submit_count(1)


def test_content_transport_interruption_retries_same_job_and_never_generates(
    tmp_path: Path,
) -> None:
    scenario = Scenario(
        "content-interruption",
        _prefix()
        + [
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/completed_no_cost.json"),
            ),
            ScenarioStep(
                Operation.CONTENT,
                "GET",
                "/api/v1/videos/job_123/content?index=0",
                exception=httpx.ReadError("synthetic content disconnect"),
            ),
            ScenarioStep(
                Operation.CONTENT,
                "GET",
                "/api/v1/videos/job_123/content?index=0",
                body=MP4,
            ),
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-content-retry", REQUEST)
            assert result.state is LocalLifecycleState.DONE
            assert core.clock.delays == [5.0]

    asyncio.run(run())
    scenario.assert_complete()
    assert scenario.ledger.content_request_count == 2
    scenario.ledger.assert_generation_submit_count(1)


def test_local_poll_interruption_preserves_job_for_zero_submit_resume(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"

    async def interrupt() -> Scenario:
        entered = asyncio.Event()
        release = asyncio.Event()
        scenario = Scenario(
            "local-interruption",
            _prefix()
            + [
                ScenarioStep(
                    Operation.POLL,
                    "GET",
                    "/api/v1/videos/job_123",
                    entered_event=entered,
                    release_event=release,
                )
            ],
        )
        async with core_harness(scenario, tmp_path, database=database) as core:
            task = asyncio.create_task(core.generate.generate("operation-interrupted", REQUEST))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            stored = core.store.get_by_job_id("job_123")
            assert stored is not None
            assert stored.local_state is LocalLifecycleState.POLLING
        return scenario

    interrupted = asyncio.run(interrupt())
    interrupted.assert_complete()
    interrupted.ledger.assert_generation_submit_count(1)

    resumed = Scenario("resume-after-local-interrupt", _completed_steps())

    async def resume() -> None:
        async with core_harness(resumed, tmp_path, database=database) as core:
            result = await core.resume.resume("job_123")
            assert result.state is LocalLifecycleState.DONE

    asyncio.run(resume())
    resumed.assert_complete()
    resumed.ledger.assert_resume_submits_zero()


def test_poll_local_ceiling_uses_fake_time_and_preserves_known_job(tmp_path: Path) -> None:
    pending = _json("poll/pending.json")
    scenario = Scenario(
        "poll-ceiling",
        _prefix()
        + [
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=pending,
            )
            for _ in range(120)
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-ceiling", REQUEST)
            assert result.state is LocalLifecycleState.OBSERVATION_INTERRUPTED
            assert result.job_id == "job_123"
            assert core.clock.elapsed == 3600.0

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)


def test_same_operation_concurrency_acquires_exactly_one_submit_right(tmp_path: Path) -> None:
    async def run() -> tuple[LocalLifecycleState, LocalLifecycleState, Scenario]:
        entered = asyncio.Event()
        release = asyncio.Event()
        steps = _prefix()
        steps[1] = ScenarioStep(
            Operation.SUBMIT,
            "POST",
            "/api/v1/videos",
            status=202,
            json_body=_json("submit/accepted.json"),
            entered_event=entered,
            release_event=release,
        )
        scenario = Scenario("same-operation-concurrency", steps + _completed_steps())
        async with core_harness(scenario, tmp_path) as core:
            winner = asyncio.create_task(core.generate.generate("operation-concurrent", REQUEST))
            await entered.wait()
            loser = await core.generate.generate("operation-concurrent", REQUEST)
            release.set()
            completed = await winner
            return completed.state, loser.state, scenario

    winner_state, loser_state, scenario = asyncio.run(run())
    scenario.assert_complete()
    assert winner_state is LocalLifecycleState.DONE
    assert loser_state is LocalLifecycleState.SUBMISSION_UNKNOWN
    scenario.ledger.assert_generation_submit_count(1)


def test_fingerprint_mismatch_and_corrupt_state_never_restore_submit_right(tmp_path: Path) -> None:
    rejected = Scenario(
        "seed-rejected",
        [_prefix()[0], ScenarioStep(Operation.SUBMIT, "POST", "/api/v1/videos", status=429)],
    )
    database = tmp_path / "jobs.sqlite3"

    async def seed() -> None:
        async with core_harness(rejected, tmp_path, database=database) as core:
            await core.generate.generate("operation-protected", REQUEST)

    asyncio.run(seed())
    rejected.assert_complete()

    mismatch = Scenario("mismatch", [])

    async def mismatch_run() -> None:
        async with core_harness(mismatch, tmp_path, database=database) as core:
            changed = GenerationRequest("test/video-alpha", "different prompt", duration=8)
            result = await core.generate.generate("operation-protected", changed)
            assert result.error is not None
            assert result.error.code is ProductErrorCode.LOCAL_STATE_CORRUPT

    asyncio.run(mismatch_run())
    mismatch.assert_complete()
    mismatch.ledger.assert_generation_submit_count(0)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE jobs SET local_state = ? WHERE operation_id = ?",
            ("CORRUPT_VALUE", "operation-protected"),
        )
        connection.commit()
    corrupt = Scenario("corrupt", [])

    async def corrupt_run() -> None:
        async with core_harness(corrupt, tmp_path, database=database) as core:
            result = await core.generate.generate("operation-protected", REQUEST)
            assert result.error is not None
            assert result.error.code is ProductErrorCode.LOCAL_STATE_CORRUPT

    asyncio.run(corrupt_run())
    corrupt.assert_complete()
    corrupt.ledger.assert_generation_submit_count(0)


def test_real_socket_post_received_response_lost_is_submission_unknown_once(
    tmp_path: Path,
) -> None:
    model = ModelCapabilities(model_id="test/video-alpha", supported_durations=(4,))
    database = tmp_path / "jobs.sqlite3"
    store = JobStore(database)
    store.replace_capability_catalog((model,), FIXED_NOW)
    plan = ResponsePlan(
        disconnect_after_request=True,
        expected_method="POST",
        expected_path="/api/v1/videos",
    )

    async def run_socket(server: LocalFaultServer) -> LocalLifecycleState:
        clock = FakeTime()
        byte_transport = LoopbackRewriteTransport(*server.address)
        async with HttpxTransport.for_test(byte_transport) as transport:
            client = OpenRouterVideoClient(
                request_policy=OpenRouterRequestPolicy(
                    identity=EXPECTED_RELEASE_IDENTITY,
                    secret_provider=SyntheticSecretProvider(),
                ),
                transport=transport,
            )
            capabilities = CapabilityService(client=client, store=store, now=clock.now)
            downloader = DownloadService(client=client, output_root=tmp_path / "output")
            service = GenerateService(
                capabilities=capabilities,
                validator=RequestValidator(),
                store=store,
                submit_client=client,
                observation_client=client,
                downloader=downloader,
                sleep=clock.sleep,
                now=clock.now,
                monotonic=clock.monotonic,
                jitter=lambda value: value,
            )
            result = await service.generate("operation-ambiguous", REQUEST)
            return result.state

    with LocalFaultServer([plan]) as server:
        state = asyncio.run(run_socket(server))
        assert server.wait_until_request_received()
        assert server.generation_submit_count == 1
    assert state is LocalLifecycleState.SUBMISSION_UNKNOWN

    restart = Scenario("ambiguous-restart", [])

    async def restart_run() -> None:
        async with core_harness(restart, tmp_path, database=database) as core:
            result = await core.generate.generate("operation-ambiguous", REQUEST)
            assert result.state is LocalLifecycleState.SUBMISSION_UNKNOWN

    asyncio.run(restart_run())
    restart.assert_complete()
    restart.ledger.assert_generation_submit_count(0)
