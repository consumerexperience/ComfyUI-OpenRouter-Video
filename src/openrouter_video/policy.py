"""Immutable operation and network policy for the OpenRouter boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Final

CANONICAL_OPENROUTER_ORIGIN: Final = "https://openrouter.ai"
OPENROUTER_API_PREFIX: Final = "/api/v1"


class Operation(Enum):
    """OpenRouter operation classes known by the safe boundary."""

    DISCOVERY = "DISCOVERY"
    SUBMIT = "SUBMIT"
    POLL = "POLL"
    CONTENT = "CONTENT"


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """Per-operation HTTPX timeouts plus an optional higher wall-clock cap."""

    connect_seconds: float
    write_seconds: float
    read_seconds: float
    pool_seconds: float
    wall_clock_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class OperationPolicy:
    """Method, path shape, media expectation, and timeout class."""

    method: str
    path_template: str
    accept: str
    is_json: bool
    timeout: TimeoutPolicy


_OPERATION_POLICIES: Final[Mapping[Operation, OperationPolicy]] = MappingProxyType(
    {
        Operation.DISCOVERY: OperationPolicy(
            method="GET",
            path_template="/api/v1/videos/models",
            accept="application/json",
            is_json=True,
            timeout=TimeoutPolicy(10.0, 10.0, 30.0, 10.0),
        ),
        Operation.SUBMIT: OperationPolicy(
            method="POST",
            path_template="/api/v1/videos",
            accept="application/json",
            is_json=True,
            timeout=TimeoutPolicy(10.0, 30.0, 60.0, 10.0),
        ),
        Operation.POLL: OperationPolicy(
            method="GET",
            path_template="/api/v1/videos/{job_id}",
            accept="application/json",
            is_json=True,
            timeout=TimeoutPolicy(10.0, 10.0, 30.0, 10.0),
        ),
        Operation.CONTENT: OperationPolicy(
            method="GET",
            path_template="/api/v1/videos/{job_id}/content?index=0",
            accept="video/*",
            is_json=False,
            timeout=TimeoutPolicy(10.0, 10.0, 60.0, 10.0, wall_clock_seconds=1200.0),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Bounded runtime settings with no destination or identity overrides."""

    max_connections: int = 10
    max_keepalive_connections: int = 5

    def __post_init__(self) -> None:
        if self.max_connections <= 0 or self.max_keepalive_connections <= 0:
            raise ValueError("Connection limits must be positive")
        if self.max_keepalive_connections > self.max_connections:
            raise ValueError("Keep-alive connections cannot exceed total connections")

    def for_operation(self, operation: Operation) -> OperationPolicy:
        """Return the immutable policy for a known operation."""

        return _OPERATION_POLICIES[operation]


__all__ = (
    "CANONICAL_OPENROUTER_ORIGIN",
    "OPENROUTER_API_PREFIX",
    "Operation",
    "OperationPolicy",
    "RuntimePolicy",
    "TimeoutPolicy",
)
