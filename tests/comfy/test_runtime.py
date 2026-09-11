"""Cross-loop and lifecycle tests for the single process runtime."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest

from openrouter_video.comfy import runtime
from openrouter_video.execution_hooks import ExecutionControl
from openrouter_video.models import GenerationRequest, GenerationResult, LocalLifecycleState
from openrouter_video.persistence import JobStore

REQUEST = GenerationRequest("vendor/model", "private prompt")


@pytest.fixture(autouse=True)
def mock_owned_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("runtime lifecycle tests must not issue network requests")

    monkeypatch.setattr(
        runtime.HttpxTransport,
        "create",
        classmethod(lambda cls, runtime_policy=None: cls.for_test(httpx.MockTransport(handler))),
    )
    monkeypatch.setattr(runtime.compat, "host_interrupted", lambda: False)


def test_two_generate_dispatches_create_two_unique_operation_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    operation_ids: list[str] = []

    class GenerateSpy:
        def __init__(self, **_: Any) -> None:
            pass

        async def generate(self, operation_id: str, request: GenerationRequest) -> GenerationResult:
            operation_ids.append(operation_id)
            assert request is REQUEST
            return GenerationResult(LocalLifecycleState.NOT_SUBMITTED, None, model=request.model)

    monkeypatch.setattr(runtime, "GenerateService", GenerateSpy)

    async def scenario() -> tuple[GenerationResult, GenerationResult, runtime.ProcessRuntime]:
        process = runtime.ProcessRuntime(tmp_path / "jobs.sqlite3", tmp_path / "output")
        first, second = await asyncio.gather(
            process.generate(REQUEST, "node-1"),
            process.generate(REQUEST, "node-1"),
        )
        await process.aclose(timeout=2.0)
        await process.aclose(timeout=2.0)
        return first, second, process

    first, second, process = asyncio.run(scenario())

    assert first.model == second.model == "vendor/model"
    assert len(operation_ids) == 2
    assert len(set(operation_ids)) == 2
    assert all(len(operation_id) >= 32 for operation_id in operation_ids)
    assert not process._thread.is_alive()
    assert process._tasks == {}
    resources = process._resources
    assert resources is not None and resources.transport._client.is_closed


def test_concurrent_first_use_publishes_one_migrated_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    constructions = 0
    counter_lock = threading.Lock()

    class CountingStore(JobStore):
        def __init__(self, path: str | Path) -> None:
            nonlocal constructions
            with counter_lock:
                constructions += 1
            super().__init__(path)

    monkeypatch.setattr(runtime, "JobStore", CountingStore)
    monkeypatch.setattr(runtime.compat, "state_database_path", lambda: tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(runtime.compat, "output_directory", lambda: tmp_path / "output")
    monkeypatch.setattr(runtime, "_runtime", None)

    with ThreadPoolExecutor(max_workers=8) as executor:
        instances = tuple(executor.map(lambda _: runtime.get_runtime(), range(8)))

    assert len({id(instance) for instance in instances}) == 1
    assert constructions == 1
    process = instances[0]
    asyncio.run(process.aclose(timeout=2.0))
    monkeypatch.setattr(runtime, "_runtime", None)


def test_caller_cancellation_waits_for_cooperative_runtime_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    completed: list[GenerationResult] = []

    class CooperativeGenerate:
        def __init__(self, **values: Any) -> None:
            self.control: ExecutionControl = values["control"]

        async def generate(self, operation_id: str, request: GenerationRequest) -> GenerationResult:
            del operation_id, request
            started.set()
            while not self.control.interrupted():
                await asyncio.sleep(0.001)
            result = GenerationResult(
                LocalLifecycleState.OBSERVATION_INTERRUPTED,
                "job-accepted",
                model="vendor/model",
            )
            completed.append(result)
            return result

    monkeypatch.setattr(runtime, "GenerateService", CooperativeGenerate)

    async def scenario() -> runtime.ProcessRuntime:
        process = runtime.ProcessRuntime(tmp_path / "jobs.sqlite3", tmp_path / "output")
        caller = asyncio.create_task(process.generate(REQUEST, "node-1"))
        await asyncio.to_thread(started.wait, 2.0)
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        assert process._tasks == {}
        await process.aclose(timeout=2.0)
        return process

    process = asyncio.run(scenario())

    assert len(completed) == 1
    assert completed[0].job_id == "job-accepted"
    assert completed[0].state is LocalLifecycleState.OBSERVATION_INTERRUPTED
    assert not process._thread.is_alive()


def test_aclose_reports_bounded_failure_for_noncooperative_task(
    tmp_path: Path,
) -> None:
    async def scenario() -> runtime.ProcessRuntime:
        process = runtime.ProcessRuntime(tmp_path / "jobs.sqlite3", tmp_path / "output")

        async def never_finishes(_: ExecutionControl) -> None:
            await asyncio.Event().wait()

        control = ExecutionControl()
        pending = process._submit(never_finishes, control)
        with pytest.raises(runtime.RuntimeShutdownError, match="did not stop"):
            await process.aclose(timeout=0.01)
        pending.cancel()
        await asyncio.sleep(0)
        await process.aclose(timeout=2.0)
        return process

    process = asyncio.run(scenario())
    assert not process._thread.is_alive()
