"""Validated local lifecycle transitions for durable generation recovery."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Final

from openrouter_video.errors import PersistenceError
from openrouter_video.models import JobRecord, LocalLifecycleState


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for durable records."""

    return datetime.now(timezone.utc)


_ALLOWED: Final = MappingProxyType(
    {
        LocalLifecycleState.NOT_SUBMITTED: frozenset({LocalLifecycleState.VALIDATING}),
        LocalLifecycleState.VALIDATING: frozenset({LocalLifecycleState.SUBMITTING}),
        LocalLifecycleState.SUBMITTING: frozenset(
            {
                LocalLifecycleState.ACCEPTED,
                LocalLifecycleState.SUBMIT_REJECTED,
                LocalLifecycleState.SUBMISSION_UNKNOWN,
            }
        ),
        LocalLifecycleState.ACCEPTED: frozenset(
            {
                LocalLifecycleState.POLLING,
                LocalLifecycleState.OBSERVATION_INTERRUPTED,
            }
        ),
        LocalLifecycleState.POLLING: frozenset(
            {
                LocalLifecycleState.POLLING,
                LocalLifecycleState.COMPLETED,
                LocalLifecycleState.FAILED,
                LocalLifecycleState.CANCELLED,
                LocalLifecycleState.EXPIRED,
                LocalLifecycleState.OBSERVATION_INTERRUPTED,
                LocalLifecycleState.UNKNOWN_REMOTE_STATE,
            }
        ),
        LocalLifecycleState.UNKNOWN_REMOTE_STATE: frozenset(
            {
                LocalLifecycleState.POLLING,
                LocalLifecycleState.OBSERVATION_INTERRUPTED,
            }
        ),
        LocalLifecycleState.OBSERVATION_INTERRUPTED: frozenset(
            {
                LocalLifecycleState.POLLING,
                LocalLifecycleState.DOWNLOADING,
            }
        ),
        LocalLifecycleState.COMPLETED: frozenset({LocalLifecycleState.DOWNLOADING}),
        LocalLifecycleState.DOWNLOADING: frozenset(
            {LocalLifecycleState.DONE, LocalLifecycleState.OBSERVATION_INTERRUPTED}
        ),
    }
)


def can_transition(current: LocalLifecycleState, target: LocalLifecycleState) -> bool:
    """Return whether the canonical lifecycle graph permits a transition."""

    return target in _ALLOWED.get(current, frozenset())


def transition(
    record: JobRecord,
    target: LocalLifecycleState,
    *,
    now: datetime | None = None,
    job_id: str | None = None,
    remote_status_raw: str | None = None,
) -> JobRecord:
    """Apply one legal transition and its standard forensic timestamp."""

    if not can_transition(record.local_state, target):
        raise PersistenceError(
            f"Illegal local lifecycle transition: {record.local_state.value} -> {target.value}"
        )
    observed = now or utc_now()
    next_remote_status = (
        remote_status_raw if remote_status_raw is not None else record.remote_status_raw
    )
    next_job_id = job_id if job_id is not None else record.job_id
    if job_id is not None and record.job_id is not None and record.job_id != job_id:
        raise PersistenceError("Durable job identity cannot change")
    submission_started_at = record.submission_started_at
    accepted_at = record.accepted_at
    last_observed_at = record.last_observed_at
    completed_at = record.completed_at
    if target is LocalLifecycleState.SUBMITTING:
        submission_started_at = observed
    if target is LocalLifecycleState.ACCEPTED:
        if next_job_id is None:
            raise PersistenceError("Accepted state requires a durable job identifier")
        accepted_at = observed
    if target in {
        LocalLifecycleState.POLLING,
        LocalLifecycleState.COMPLETED,
        LocalLifecycleState.FAILED,
        LocalLifecycleState.CANCELLED,
        LocalLifecycleState.EXPIRED,
        LocalLifecycleState.UNKNOWN_REMOTE_STATE,
        LocalLifecycleState.OBSERVATION_INTERRUPTED,
    }:
        last_observed_at = observed
    if target is LocalLifecycleState.COMPLETED:
        completed_at = observed
    return replace(
        record,
        local_state=target,
        remote_status_raw=next_remote_status,
        job_id=next_job_id,
        submission_started_at=submission_started_at,
        accepted_at=accepted_at,
        last_observed_at=last_observed_at,
        completed_at=completed_at,
    )


__all__ = ("can_transition", "transition", "utc_now")
