"""Small Comfy-agnostic hooks for progress and cooperative interruption."""

from __future__ import annotations

import inspect
import threading
from collections.abc import Awaitable, Callable
from enum import Enum


class ExecutionPhase(str, Enum):
    """Coarse local execution stages; never remote completion percentages."""

    VALIDATING = "VALIDATING"
    SUBMITTING = "SUBMITTING"
    ACCEPTED = "ACCEPTED"
    POLLING = "POLLING"
    DOWNLOADING = "DOWNLOADING"
    DONE = "DONE"


class CooperativeInterrupt(RuntimeError):  # noqa: N818 - internal control signal
    """Internal signal requesting a billing-safe local observation stop."""


class ExecutionControl:
    """Thread-safe per-execution cooperative interruption state."""

    __slots__ = ("_event", "_host_check")

    def __init__(self, host_check: Callable[[], bool] | None = None) -> None:
        self._event = threading.Event()
        self._host_check = host_check

    def request_interrupt(self) -> None:
        """Request local interruption without cancelling a runtime task."""

        self._event.set()

    def interrupted(self) -> bool:
        """Return local or host interruption state without mutating authority."""

        if self._event.is_set():
            return True
        return bool(self._host_check is not None and self._host_check())

    def raise_if_interrupted(self) -> None:
        """Raise the internal cooperative signal when interruption was requested."""

        if self.interrupted():
            raise CooperativeInterrupt


ProgressObserver = Callable[[ExecutionPhase], Awaitable[None] | None]


async def report_progress(observer: ProgressObserver | None, phase: ExecutionPhase) -> None:
    """Report a phase without allowing presentation failures to affect Core state."""

    if observer is None:
        return
    try:
        outcome = observer(phase)
        if inspect.isawaitable(outcome):
            await outcome
    except Exception:
        return


__all__ = (
    "CooperativeInterrupt",
    "ExecutionControl",
    "ExecutionPhase",
    "ProgressObserver",
    "report_progress",
)
