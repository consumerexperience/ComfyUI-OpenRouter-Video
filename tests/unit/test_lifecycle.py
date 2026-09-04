from __future__ import annotations

from datetime import datetime, timezone

import pytest

from openrouter_video.errors import PersistenceError
from openrouter_video.lifecycle import can_transition, transition
from openrouter_video.models import JobRecord, LocalLifecycleState

NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


def _record(state: LocalLifecycleState) -> JobRecord:
    return JobRecord(
        schema_version=1,
        operation_id="operation-1",
        request_fingerprint="v1:" + "0" * 64,
        model="vendor/model",
        local_state=state,
        created_at=NOW,
        job_id="job-1" if state not in {LocalLifecycleState.SUBMITTING} else None,
    )


def test_submit_branches_are_explicit() -> None:
    for target in (
        LocalLifecycleState.ACCEPTED,
        LocalLifecycleState.SUBMIT_REJECTED,
        LocalLifecycleState.SUBMISSION_UNKNOWN,
    ):
        assert can_transition(LocalLifecycleState.SUBMITTING, target)

    assert not can_transition(LocalLifecycleState.SUBMITTING, LocalLifecycleState.FAILED)


def test_acceptance_requires_and_preserves_remote_job_identity() -> None:
    accepted = transition(
        _record(LocalLifecycleState.SUBMITTING),
        LocalLifecycleState.ACCEPTED,
        now=NOW,
        job_id="job-1",
        remote_status_raw="pending",
    )

    assert accepted.job_id == "job-1"
    assert accepted.accepted_at == NOW
    with pytest.raises(PersistenceError):
        transition(accepted, LocalLifecycleState.POLLING, job_id="job-2")


def test_illegal_terminal_transition_fails_safe() -> None:
    with pytest.raises(PersistenceError):
        transition(_record(LocalLifecycleState.DONE), LocalLifecycleState.POLLING)
