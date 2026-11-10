"""Transient native media sources. No host imports or durable content."""

import asyncio
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

MAX_OBJECT_BYTES = 256 * 1024 * 1024
MAX_REQUEST_BYTES = 512 * 1024 * 1024


class NativeMediaError(ValueError):
    """Sanitized conversion or size failure."""


@dataclass(frozen=True, slots=True, repr=False)
class LocalMedia:
    """Deferred conversion, invoked only after capability validation."""

    content_type: str
    suffix: str
    write: Callable[[Path], None] = field(repr=False)
    duration: Callable[[], float] | None = field(default=None, repr=False)
    max_duration_seconds: float | None = None
    max_bytes: int = MAX_OBJECT_BYTES

    def encode(self, destination: Path) -> int:
        try:
            if self.max_duration_seconds is not None:
                if self.duration is None:
                    raise NativeMediaError("Native VIDEO duration could not be verified.")
                duration = self.duration()
                if not math.isfinite(duration) or not 0 < duration <= self.max_duration_seconds:
                    raise NativeMediaError(
                        "Native VIDEO exceeds the selected method's duration limit."
                    )
            self.write(destination)
            size = destination.stat().st_size
        except NativeMediaError:
            raise
        except Exception:
            raise NativeMediaError("Native media could not be converted.") from None
        if not 0 < size <= min(self.max_bytes, MAX_OBJECT_BYTES):
            raise NativeMediaError(
                "Native media exceeds the method or 256 MiB object limit, or is empty."
            )
        return size


_T = TypeVar("_T")


async def run_file_worker(function: Callable[..., _T], *args: object) -> _T:
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.shield(task)
        with suppress(Exception):
            task.result()
        raise
