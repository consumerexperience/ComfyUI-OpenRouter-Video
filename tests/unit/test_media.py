from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from openrouter_video.errors import InvalidVideoResponseError, OpenRouterHTTPError
from openrouter_video.execution_hooks import CooperativeInterrupt, ExecutionControl
from openrouter_video.media import MAX_VIDEO_BYTES, DownloadService
from openrouter_video.policy import Operation

MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
WEBM = b"\x1aE\xdf\xa3\x00\x00webm" + b"\x00" * 32
QUICKTIME = b"\x00\x00\x00\x18ftypqt  " + b"\x00" * 32


class ContentStub:
    def __init__(
        self, outcomes: list[bytes | BaseException | tuple[bytes, dict[str, str]]]
    ) -> None:
        self.outcomes = outcomes
        self.calls = 0

    @asynccontextmanager
    async def stream_content(self, job_id: str) -> AsyncIterator[httpx.Response]:
        assert job_id == "job-1"
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        content, headers = outcome if isinstance(outcome, tuple) else (outcome, {})
        request = httpx.Request("GET", "https://openrouter.ai/api/v1/videos/job-1/content")
        yield httpx.Response(200, content=content, headers=headers, request=request)


async def _no_sleep(_: float) -> None:
    return None


def test_download_streams_to_part_then_fsyncs_and_atomically_renames(tmp_path: Path) -> None:
    client = ContentStub([MP4])
    service = DownloadService(
        client=client,
        output_root=tmp_path,
        sleep=_no_sleep,
        jitter=lambda value: value,
    )

    artifact = asyncio.run(service.download("job-1"))

    assert artifact.path.suffix == ".mp4"
    assert artifact.path.read_bytes() == MP4
    assert artifact.media_type == "video/mp4"
    assert not tuple(tmp_path.glob("*.part"))
    assert service.relative_path(artifact) == artifact.path.name


def test_download_accepts_webm_and_reuses_valid_existing_artifact(tmp_path: Path) -> None:
    client = ContentStub([WEBM])
    service = DownloadService(client=client, output_root=tmp_path, sleep=_no_sleep)

    first = asyncio.run(service.download("job-1"))
    second = asyncio.run(service.download("job-1"))

    assert first == second
    assert first.media_type == "video/webm"
    assert client.calls == 1


def test_quicktime_is_disabled_and_invalid_content_is_bounded_to_three_gets(tmp_path: Path) -> None:
    client = ContentStub([QUICKTIME, QUICKTIME, QUICKTIME])
    service = DownloadService(
        client=client,
        output_root=tmp_path,
        sleep=_no_sleep,
        jitter=lambda value: value,
    )

    with pytest.raises(InvalidVideoResponseError):
        asyncio.run(service.download("job-1"))
    assert client.calls == 3
    assert not tuple(tmp_path.iterdir())


def test_download_retries_retry_safe_get_without_submit(tmp_path: Path) -> None:
    client = ContentStub([OpenRouterHTTPError(500, Operation.CONTENT), MP4])
    delays: list[float] = []

    async def sleep(value: float) -> None:
        delays.append(value)

    service = DownloadService(
        client=client,
        output_root=tmp_path,
        sleep=sleep,
        jitter=lambda value: value,
    )

    assert asyncio.run(service.download("job-1")).path.suffix == ".mp4"
    assert client.calls == 2
    assert delays == [5.0]


def test_download_rejects_declared_oversize_before_writing(tmp_path: Path) -> None:
    headers = {"Content-Length": str(MAX_VIDEO_BYTES + 1)}
    client = ContentStub([(MP4, headers), (MP4, headers), (MP4, headers)])
    service = DownloadService(client=client, output_root=tmp_path, sleep=_no_sleep)

    with pytest.raises(InvalidVideoResponseError):
        asyncio.run(service.download("job-1"))
    assert not tuple(tmp_path.iterdir())


def test_durable_relative_path_cannot_escape_output_root(tmp_path: Path) -> None:
    service = DownloadService(client=ContentStub([]), output_root=tmp_path)

    with pytest.raises(Exception, match="unavailable"):
        service.load_artifact("../outside.mp4")


def test_download_interrupt_deletes_partial_artifact(tmp_path: Path) -> None:
    control = ExecutionControl()

    class InterruptingStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield MP4[:16]
            control.request_interrupt()
            yield MP4[16:]

    class InterruptingClient:
        @asynccontextmanager
        async def stream_content(self, job_id: str) -> AsyncIterator[httpx.Response]:
            request = httpx.Request("GET", "https://openrouter.ai/api/v1/videos/job-1/content")
            yield httpx.Response(200, stream=InterruptingStream(), request=request)

    service = DownloadService(
        client=InterruptingClient(),
        output_root=tmp_path,
        sleep=_no_sleep,
        control=control,
    )

    with pytest.raises(CooperativeInterrupt):
        asyncio.run(service.download("job-1"))
    assert not tuple(tmp_path.iterdir())
