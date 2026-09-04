"""Bounded canonical content download and durable artifact validation."""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path

from openrouter_video.client import ContentClient
from openrouter_video.errors import (
    InvalidVideoResponseError,
    LocalDiskError,
    MediaDownloadError,
    OpenRouterHTTPError,
    TransportError,
)
from openrouter_video.models import VideoArtifact

MAX_VIDEO_BYTES = 1 << 30
DOWNLOAD_WALL_SECONDS = 20 * 60.0
DOWNLOAD_ATTEMPTS = 3
_BACKOFF_SECONDS = (5.0, 10.0)

Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]
Jitter = Callable[[float], float]


def _jitter(value: float) -> float:
    return random.uniform(value * 0.8, value * 1.2)  # noqa: S311 - retry timing only


class DownloadService:
    """Download index zero through ContentClient into one configured local root."""

    __slots__ = ("_client", "_jitter", "_monotonic", "_output_root", "_sleep")

    def __init__(
        self,
        *,
        client: ContentClient,
        output_root: str | Path,
        sleep: Sleep = asyncio.sleep,
        monotonic: Monotonic = time.monotonic,
        jitter: Jitter = _jitter,
    ) -> None:
        self._client = client
        self._output_root = Path(output_root)
        self._sleep = sleep
        self._monotonic = monotonic
        self._jitter = jitter

    async def download(self, job_id: str) -> VideoArtifact:
        """Return a valid existing artifact or perform up to three GET attempts."""

        existing = self._find_existing(job_id)
        if existing is not None:
            return existing
        last_error: MediaDownloadError | OpenRouterHTTPError | TransportError | None = None
        for attempt in range(DOWNLOAD_ATTEMPTS):
            try:
                return await self._download_once(job_id)
            except (TransportError, OpenRouterHTTPError, InvalidVideoResponseError) as exc:
                last_error = exc
                if attempt == DOWNLOAD_ATTEMPTS - 1 or not _retryable_download(exc):
                    break
                retry_after = (
                    exc.retry_after_seconds if isinstance(exc, OpenRouterHTTPError) else None
                )
                delay = (
                    retry_after
                    if retry_after is not None
                    else self._jitter(_BACKOFF_SECONDS[attempt])
                )
                await self._sleep(delay)
            except LocalDiskError:
                raise
        if isinstance(last_error, InvalidVideoResponseError):
            raise last_error
        raise MediaDownloadError("Video download failed") from None

    async def _download_once(self, job_id: str) -> VideoArtifact:
        stem = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:24]
        part = self._output_root / f"{stem}.{secrets.token_hex(8)}.part"
        started = self._monotonic()
        bytes_written = 0
        header = bytearray()
        expected_length: int | None = None
        try:
            self._output_root.mkdir(parents=True, exist_ok=True)
            async with self._client.stream_content(job_id) as response:
                length_header = response.headers.get("Content-Length")
                if length_header is not None:
                    try:
                        expected_length = int(length_header)
                    except ValueError:
                        raise InvalidVideoResponseError("Invalid content length") from None
                    if expected_length < 0 or expected_length > MAX_VIDEO_BYTES:
                        raise InvalidVideoResponseError("Video content length is outside limits")
                with part.open("xb") as handle:
                    async for chunk in response.aiter_bytes():
                        if self._monotonic() - started > DOWNLOAD_WALL_SECONDS:
                            raise MediaDownloadError("Video download exceeded wall-clock limit")
                        if not chunk:
                            continue
                        bytes_written += len(chunk)
                        if bytes_written > MAX_VIDEO_BYTES:
                            raise InvalidVideoResponseError("Video content exceeds size limit")
                        if len(header) < 4096:
                            header.extend(chunk[: 4096 - len(header)])
                        handle.write(chunk)
                    if expected_length is not None and bytes_written != expected_length:
                        raise InvalidVideoResponseError("Video content was truncated")
                    media_type, extension = _detect_container(bytes(header))
                    handle.flush()
                    os.fsync(handle.fileno())
            final = self._output_root / f"{stem}{extension}"
            os.replace(part, final)
            return VideoArtifact(final, media_type, bytes_written)
        except (OpenRouterHTTPError, TransportError, MediaDownloadError):
            raise
        except OSError:
            raise LocalDiskError("Local artifact storage failed") from None
        finally:
            with suppress(OSError):
                part.unlink(missing_ok=True)

    def relative_path(self, artifact: VideoArtifact) -> str:
        """Return a normalized path only when the artifact is inside the configured root."""

        try:
            return artifact.path.resolve().relative_to(self._output_root.resolve()).as_posix()
        except (OSError, ValueError):
            raise LocalDiskError("Artifact path is outside the configured output root") from None

    def load_artifact(self, relative_path: str) -> VideoArtifact:
        """Revalidate a durable relative output path without network access."""

        candidate = (self._output_root / relative_path).resolve()
        try:
            candidate.relative_to(self._output_root.resolve())
            size = candidate.stat().st_size
            if size <= 0 or size > MAX_VIDEO_BYTES:
                raise InvalidVideoResponseError("Durable video artifact is invalid")
            with candidate.open("rb") as handle:
                media_type, _ = _detect_container(handle.read(4096))
        except (OSError, ValueError):
            raise LocalDiskError("Durable video artifact is unavailable") from None
        return VideoArtifact(candidate, media_type, size)

    def _find_existing(self, job_id: str) -> VideoArtifact | None:
        stem = hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:24]
        for extension in (".mp4", ".webm"):
            candidate = self._output_root / f"{stem}{extension}"
            if candidate.exists():
                return self.load_artifact(candidate.name)
        return None


def _detect_container(header: bytes) -> tuple[str, str]:
    if len(header) >= 12 and header[4:8] == b"ftyp":
        if header[8:12] == b"qt  ":
            raise InvalidVideoResponseError("QuickTime content is disabled in Phase 5")
        return "video/mp4", ".mp4"
    if header.startswith(b"\x1aE\xdf\xa3") and b"webm" in header.lower():
        return "video/webm", ".webm"
    raise InvalidVideoResponseError("Video content is not MP4 or WebM")


def _retryable_download(error: BaseException) -> bool:
    if isinstance(error, (TransportError, InvalidVideoResponseError)):
        return True
    return isinstance(error, OpenRouterHTTPError) and (
        error.status_code in {408, 429} or 500 <= error.status_code <= 599
    )


__all__ = (
    "DOWNLOAD_ATTEMPTS",
    "DOWNLOAD_WALL_SECONDS",
    "DownloadService",
    "MAX_VIDEO_BYTES",
)
