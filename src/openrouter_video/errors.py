"""Typed internal failures for safe Headless Core orchestration."""

from __future__ import annotations

from openrouter_video.models import ProductError
from openrouter_video.policy import Operation


class RequestPolicyError(RuntimeError):
    """A request was rejected before unsafe network transmission."""


class TransportError(RuntimeError):
    """A prepared request failed at the byte-transport boundary."""


class OpenRouterHTTPError(RuntimeError):
    """OpenRouter returned a non-success status without retaining its response body."""

    def __init__(
        self,
        status_code: int,
        operation: Operation,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(f"OpenRouter {operation.value.lower()} returned HTTP {status_code}")
        self.status_code = status_code
        self.operation = operation
        self.retry_after_seconds = retry_after_seconds


class MalformedOpenRouterResponseError(RuntimeError):
    """A successful-looking response did not satisfy the minimum safe contract."""


class CapabilityUnavailableError(RuntimeError):
    """No fresh or bounded last-known-good capability catalog is available."""


class PersistenceError(RuntimeError):
    """Durable local state is unavailable, corrupt, or contradictory."""


class MediaDownloadError(RuntimeError):
    """A bounded download failed without creating a valid final artifact."""


class InvalidVideoResponseError(MediaDownloadError):
    """Downloaded bytes are not an accepted Phase-5 video container."""


class LocalDiskError(MediaDownloadError):
    """Local filesystem work failed."""


class ProductFailureError(RuntimeError):
    """Internal exception carrying one sanitized product error contract."""

    def __init__(self, error: ProductError) -> None:
        super().__init__(error.message)
        self.error = error


__all__ = (
    "CapabilityUnavailableError",
    "InvalidVideoResponseError",
    "LocalDiskError",
    "MalformedOpenRouterResponseError",
    "MediaDownloadError",
    "OpenRouterHTTPError",
    "PersistenceError",
    "ProductFailureError",
    "RequestPolicyError",
    "TransportError",
)
