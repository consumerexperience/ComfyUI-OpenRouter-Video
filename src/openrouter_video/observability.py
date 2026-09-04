"""Allowlisted local logging for the OpenRouter request boundary."""

from __future__ import annotations

import logging

from openrouter_video.policy import CANONICAL_OPENROUTER_ORIGIN, Operation


def log_boundary_event(
    logger: logging.Logger,
    *,
    operation: Operation,
    result: str,
    http_status: int | None = None,
    attribution_applied: bool | None = None,
) -> None:
    """Log only approved non-payload boundary metadata."""

    fields: dict[str, object] = {
        "openrouter_operation": operation.value,
        "openrouter_host": CANONICAL_OPENROUTER_ORIGIN.removeprefix("https://"),
        "openrouter_result": result,
    }
    if http_status is not None:
        fields["openrouter_http_status"] = http_status
    if attribution_applied is not None:
        fields["openrouter_attribution_applied"] = attribution_applied
    logger.info("openrouter_boundary", extra=fields)


__all__ = ("log_boundary_event",)
