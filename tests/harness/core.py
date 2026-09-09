"""Composition helpers that run scenarios against the real Phase-5 Core."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openrouter_video.application import GenerateService, ResumeService
from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.client import OpenRouterVideoClient
from openrouter_video.media import DownloadService
from openrouter_video.persistence import JobStore
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport
from tests.fixtures.identity import EXPECTED_RELEASE_IDENTITY
from tests.harness.scenario import Scenario

SYNTHETIC_API_TOKEN = "SYNTHETIC_HARNESS_TOKEN"  # noqa: S105 - explicit test credential
FIXED_NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)


class SyntheticSecretProvider:
    """Explicit test provider that never consults environment or production keychains."""

    def get_openrouter_api_key(self) -> str:
        return SYNTHETIC_API_TOKEN


class FakeTime:
    """Deterministic monotonic clock and sleeper with no real delay."""

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        self.elapsed += seconds

    def monotonic(self) -> float:
        return self.elapsed

    def now(self) -> datetime:
        return FIXED_NOW + timedelta(seconds=self.elapsed)


@dataclass(frozen=True, slots=True)
class CoreHarness:
    """Real services and durable components attached to one semantic scenario."""

    scenario: Scenario
    store: JobStore
    client: OpenRouterVideoClient
    downloader: DownloadService
    generate: GenerateService
    resume: ResumeService
    clock: FakeTime


@asynccontextmanager
async def core_harness(
    scenario: Scenario,
    root: Path,
    *,
    database: Path | None = None,
) -> AsyncIterator[CoreHarness]:
    """Build and close the real Core using a zero-network MockTransport scenario."""

    store = JobStore(database or root / "jobs.sqlite3")
    clock = FakeTime()
    async with HttpxTransport.for_test(scenario.transport()) as transport:
        client = OpenRouterVideoClient(
            request_policy=OpenRouterRequestPolicy(
                identity=EXPECTED_RELEASE_IDENTITY,
                secret_provider=SyntheticSecretProvider(),
            ),
            transport=transport,
        )
        capabilities = CapabilityService(
            client=client,
            store=store,
            sleep=clock.sleep,
            now=clock.now,
            jitter=lambda value: value,
        )
        downloader = DownloadService(
            client=client,
            output_root=root / "output",
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            jitter=lambda value: value,
        )
        generate = GenerateService(
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
        resume = ResumeService(
            observation_client=client,
            store=store,
            downloader=downloader,
            sleep=clock.sleep,
            now=clock.now,
            monotonic=clock.monotonic,
            jitter=lambda value: value,
        )
        yield CoreHarness(scenario, store, client, downloader, generate, resume, clock)


__all__ = (
    "CoreHarness",
    "FIXED_NOW",
    "FakeTime",
    "SYNTHETIC_API_TOKEN",
    "SyntheticSecretProvider",
    "core_harness",
)
