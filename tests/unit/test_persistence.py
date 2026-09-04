from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from openrouter_video.errors import PersistenceError
from openrouter_video.models import FrameType, JobRecord, LocalLifecycleState, ModelCapabilities
from openrouter_video.persistence import JobStore

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _submitting() -> JobRecord:
    return JobRecord(
        schema_version=1,
        operation_id="operation-1",
        request_fingerprint="v1:" + "1" * 64,
        model="vendor/model",
        local_state=LocalLifecycleState.SUBMITTING,
        created_at=NOW,
        submission_started_at=NOW,
    )


def test_schema_enforces_operation_and_remote_job_uniqueness(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    first = _submitting()
    second = replace(first, operation_id="operation-2", job_id="job-1")

    assert store.claim_submitting(first)
    assert not store.claim_submitting(first)
    assert store.insert(second)
    with pytest.raises(PersistenceError):
        store.save(replace(first, job_id="job-1"))


def test_concurrent_same_operation_acquires_exactly_one_submit_right(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: store.claim_submitting(_submitting()), range(2)))

    assert sorted(results) == [False, True]
    assert store.get_by_operation_id("operation-1") == _submitting()


def test_decimal_is_stored_as_exact_text_and_none_is_not_zero(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    record = replace(_submitting(), actual_cost_usd=Decimal("0.100000000000000001"))
    assert store.claim_submitting(record)

    with sqlite3.connect(path) as connection:
        value, storage_type = connection.execute(
            "SELECT actual_cost_usd, typeof(actual_cost_usd) FROM jobs"
        ).fetchone()
    assert value == "0.100000000000000001"
    assert storage_type == "text"
    assert store.get_by_operation_id("operation-1") == record


def test_capability_cache_round_trips_normalized_fields_only(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    capability = ModelCapabilities(
        model_id="vendor/model",
        canonical_slug="vendor/model",
        supported_durations=(5, 8),
        supported_resolutions=("720p",),
        supported_frame_types=frozenset({FrameType.FIRST}),
        generate_audio=True,
        supports_seed=False,
    )

    store.replace_capability_catalog((capability,), NOW)

    assert store.load_capability_catalog() == (NOW, (capability,))


def test_corrupt_state_never_degrades_to_missing_record(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    store = JobStore(path)
    assert store.claim_submitting(_submitting())
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE jobs SET local_state = 'BROKEN'")
        connection.commit()

    with pytest.raises(PersistenceError):
        store.get_by_operation_id("operation-1")


def test_release_claim_requires_proven_pre_network_shape(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite3")
    assert store.claim_submitting(_submitting())

    assert not store.release_unsubmitted_claim("operation-1", "v1:" + "2" * 64)
    assert store.release_unsubmitted_claim("operation-1", _submitting().request_fingerprint)
    assert store.get_by_operation_id("operation-1") is None
