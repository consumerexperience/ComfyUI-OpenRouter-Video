"""Transient native media sources. No host imports or durable content."""

import asyncio
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

    def encode(self, destination: Path) -> int:
        try:
            self.write(destination)
            size = destination.stat().st_size
        except NativeMediaError:
            raise
        except Exception:
            raise NativeMediaError("Native media could not be converted.") from None
        if not 0 < size <= MAX_OBJECT_BYTES:
            raise NativeMediaError("Native media exceeds the 256 MiB object limit or is empty.")
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
