"""Single-process Comfy runtime with one owned Core event loop and HTTP client."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from openrouter_video.app_identity import OFFICIAL_APP_IDENTITY
from openrouter_video.application import GenerateService, ResumeService
from openrouter_video.capabilities import CapabilityObservation, CapabilityService, RequestValidator
from openrouter_video.client import OpenRouterVideoClient
from openrouter_video.execution_hooks import ExecutionControl, ExecutionPhase
from openrouter_video.media import DownloadService
from openrouter_video.models import GenerationRequest, GenerationResult
from openrouter_video.persistence import JobStore
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.secrets import EnvironmentSecretProvider
from openrouter_video.transport import HttpxTransport

from . import compat

T = TypeVar("T")
SHUTDOWN_TIMEOUT_SECONDS = 15.0


class RuntimeShutdownError(RuntimeError):
    """The owned Core runtime did not shut down within its bounded contract."""


@dataclass(frozen=True, slots=True)
class _Resources:
    store: JobStore
    transport: HttpxTransport
    client: OpenRouterVideoClient
    capabilities: CapabilityService
    output_root: Path


class ProcessRuntime:
    """Own all Core async work on one loop regardless of the calling Comfy loop."""

    def __init__(self, database: Path, output_root: Path) -> None:
        self._database = database
        self._output_root = output_root
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="openrouter-video-runtime",
            daemon=True,
        )
        self._ready = threading.Event()
        self._lock = threading.RLock()
        self._tasks: dict[concurrent.futures.Future[Any], ExecutionControl] = {}
        self._resources: _Resources | None = None
        self._startup_error: BaseException | None = None
        self._closing = False
        self._closed = False
        self._thread.start()
        if not self._ready.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS):
            raise RuntimeShutdownError("OpenRouter Video runtime initialization timed out.")
        if self._startup_error is not None:
            raise RuntimeError("OpenRouter Video runtime initialization failed.") from None

    def _thread_main(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            store = JobStore(self._database)
            transport = HttpxTransport.create()
            client = OpenRouterVideoClient(
                request_policy=OpenRouterRequestPolicy(
                    identity=OFFICIAL_APP_IDENTITY,
                    secret_provider=EnvironmentSecretProvider(),
                ),
                transport=transport,
            )
            self._resources = _Resources(
                store=store,
                transport=transport,
                client=client,
                capabilities=CapabilityService(client=client, store=store),
                output_root=self._output_root,
            )
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            self._loop.close()
            return
        self._ready.set()
        self._loop.run_forever()
        self._loop.close()

    def _require_resources(self) -> _Resources:
        resources = self._resources
        if resources is None:
            raise RuntimeError("OpenRouter Video runtime is unavailable.")
        return resources

    @staticmethod
    async def _cooperative_sleep(control: ExecutionControl, seconds: float) -> None:
        deadline = time.monotonic() + max(seconds, 0.0)
        while True:
            control.raise_if_interrupted()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 0.25))

    def _submit(
        self,
        operation: Callable[[ExecutionControl], Awaitable[T]],
        control: ExecutionControl,
    ) -> concurrent.futures.Future[T]:
        async def invoke() -> T:
            return await operation(control)

        with self._lock:
            if self._closing or self._closed:
                raise RuntimeShutdownError("OpenRouter Video runtime is closing.")
            future: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(
                invoke(), self._loop
            )
            self._tasks[future] = control
            future.add_done_callback(self._forget_task)
            return future

    def _forget_task(self, future: concurrent.futures.Future[Any]) -> None:
        with self._lock:
            self._tasks.pop(future, None)

    async def _dispatch(
        self,
        operation: Callable[[ExecutionControl], Awaitable[T]],
    ) -> T:
        control = ExecutionControl(compat.host_interrupted)
        concurrent_future = self._submit(operation, control)
        caller_loop = asyncio.get_running_loop()
        disposition_ready = asyncio.Event()
        concurrent_future.add_done_callback(
            lambda _: caller_loop.call_soon_threadsafe(disposition_ready.set)
        )
        try:
            await asyncio.shield(disposition_ready.wait())
        except asyncio.CancelledError:
            control.request_interrupt()
            while not concurrent_future.done():
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(disposition_ready.wait())
            with contextlib.suppress(BaseException):
                concurrent_future.result()
            raise
        return concurrent_future.result()

    async def catalog(self) -> CapabilityObservation:
        async def run(control: ExecutionControl) -> CapabilityObservation:
            control.raise_if_interrupted()
            return await self._require_resources().capabilities.catalog()

        return await self._dispatch(run)

    async def generate(self, request: GenerationRequest, node_id: str | None) -> GenerationResult:
        async def run(control: ExecutionControl) -> GenerationResult:
            resources = self._require_resources()

            async def progress(phase: ExecutionPhase) -> None:
                await compat.report_phase(phase, node_id)

            async def sleep(seconds: float) -> None:
                await self._cooperative_sleep(control, seconds)

            capabilities = CapabilityService(
                client=resources.client,
                store=resources.store,
                sleep=sleep,
            )
            downloader = DownloadService(
                client=resources.client,
                output_root=resources.output_root,
                sleep=sleep,
                control=control,
            )
            service = GenerateService(
                capabilities=capabilities,
                validator=RequestValidator(),
                store=resources.store,
                submit_client=resources.client,
                observation_client=resources.client,
                downloader=downloader,
                sleep=sleep,
                control=control,
                progress=progress,
            )
            operation_id = secrets.token_urlsafe(32)
            return await service.generate(operation_id, request)

        return await self._dispatch(run)

    async def resume(self, job_id: str, node_id: str | None) -> GenerationResult:
        async def run(control: ExecutionControl) -> GenerationResult:
            resources = self._require_resources()

            async def progress(phase: ExecutionPhase) -> None:
                await compat.report_phase(phase, node_id)

            async def sleep(seconds: float) -> None:
                await self._cooperative_sleep(control, seconds)

            downloader = DownloadService(
                client=resources.client,
                output_root=resources.output_root,
                sleep=sleep,
                control=control,
            )
            service = ResumeService(
                observation_client=resources.client,
                store=resources.store,
                downloader=downloader,
                sleep=sleep,
                control=control,
                progress=progress,
            )
            return await service.resume(job_id)

        return await self._dispatch(run)

    async def aclose(self, timeout: float = SHUTDOWN_TIMEOUT_SECONDS) -> None:
        with self._lock:
            if self._closed:
                return
            self._closing = True
            tasks = tuple(self._tasks.items())
        for _, control in tasks:
            control.request_interrupt()
        started = time.monotonic()
        if tasks:
            _, pending = await asyncio.to_thread(
                concurrent.futures.wait,
                [future for future, _ in tasks],
                timeout=timeout,
            )
            if pending:
                raise RuntimeShutdownError("OpenRouter Video runtime tasks did not stop in time.")
        remaining = max(timeout - (time.monotonic() - started), 0.0)
        close_future = asyncio.run_coroutine_threadsafe(
            self._require_resources().transport.aclose(),
            self._loop,
        )
        try:
            await asyncio.wait_for(asyncio.wrap_future(close_future), timeout=remaining)
        except TimeoutError:
            raise RuntimeShutdownError(
                "OpenRouter Video HTTP client did not close in time."
            ) from None
        self._loop.call_soon_threadsafe(self._loop.stop)
        await asyncio.to_thread(self._thread.join, remaining)
        if self._thread.is_alive():
            raise RuntimeShutdownError("OpenRouter Video runtime thread did not stop in time.")
        with self._lock:
            self._closed = True


_runtime_lock = threading.RLock()
_runtime: ProcessRuntime | None = None


def get_runtime() -> ProcessRuntime:
    """Return the one fully initialized process runtime."""

    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = ProcessRuntime(compat.state_database_path(), compat.output_directory())
        return _runtime


async def close_runtime() -> None:
    """Close and forget the process runtime; intended for controlled host/test shutdown."""

    global _runtime
    with _runtime_lock:
        runtime = _runtime
    if runtime is None:
        return
    await runtime.aclose()
    with _runtime_lock:
        if _runtime is runtime:
            _runtime = None


__all__ = (
    "ProcessRuntime",
    "RuntimeShutdownError",
    "SHUTDOWN_TIMEOUT_SECONDS",
    "close_runtime",
    "get_runtime",
)
