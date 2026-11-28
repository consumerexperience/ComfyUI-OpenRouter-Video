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
    min_duration_seconds: float | None = None
    geometry: Callable[[], tuple[int, int]] | None = field(default=None, repr=False)
    min_width: int | None = None
    max_width: int | None = None
    min_height: int | None = None
    max_height: int | None = None
    min_pixels: int | None = None
    max_pixels: int | None = None
    combined_duration_check: Callable[[], None] | None = field(default=None, repr=False)

    def encode(self, destination: Path) -> int:
        try:
            if self.combined_duration_check is not None:
                self.combined_duration_check()
            if any(
                v is not None
                for v in (
                    self.min_width,
                    self.max_width,
                    self.min_height,
                    self.max_height,
                    self.min_pixels,
                    self.max_pixels,
                )
            ):
                if self.geometry is None:
                    raise NativeMediaError("Native VIDEO geometry could not be verified.")
                width, height = self.geometry()
                pixels = width * height
                if (
                    type(width) is not int
                    or type(height) is not int
                    or width <= 0
                    or height <= 0
                    or any(
                        (
                            self.min_width is not None and width < self.min_width,
                            self.max_width is not None and width > self.max_width,
                            self.min_height is not None and height < self.min_height,
                            self.max_height is not None and height > self.max_height,
                            self.min_pixels is not None and pixels < self.min_pixels,
                            self.max_pixels is not None and pixels > self.max_pixels,
                        )
                    )
                ):
                    raise NativeMediaError(
                        "Native VIDEO geometry exceeds the selected method's limits."
                    )
            if self.max_duration_seconds is not None or self.min_duration_seconds is not None:
                if self.duration is None:
                    raise NativeMediaError("Native VIDEO duration could not be verified.")
                duration = self.duration()
                if (
                    not math.isfinite(duration)
                    or duration <= 0
                    or (
                        self.min_duration_seconds is not None
                        and duration < self.min_duration_seconds
                    )
                    or (
                        self.max_duration_seconds is not None
                        and duration > self.max_duration_seconds
                    )
                ):
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
