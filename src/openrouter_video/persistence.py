"""SQLite recovery state with billing-safe identity and concurrency enforcement."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

from openrouter_video.errors import PersistenceError
from openrouter_video.models import (
    FrameType,
    JobRecord,
    LocalLifecycleState,
    ModelCapabilities,
    ProductErrorCode,
)

SCHEMA_VERSION: Final = 1

_JOB_COLUMNS: Final = (
    "schema_version",
    "operation_id",
    "node_instance_id",
    "request_fingerprint",
    "job_id",
    "model",
    "local_state",
    "remote_status_raw",
    "created_at",
    "submission_started_at",
    "accepted_at",
    "last_observed_at",
    "completed_at",
    "actual_cost_usd",
    "output_relpath",
    "product_error_code",
)
_INSERT_JOB_SQL: Final = """
    INSERT INTO jobs (
        schema_version, operation_id, node_instance_id, request_fingerprint, job_id, model,
        local_state, remote_status_raw, created_at, submission_started_at, accepted_at,
        last_observed_at, completed_at, actual_cost_usd, output_relpath, product_error_code
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_UPDATE_JOB_SQL: Final = """
    UPDATE jobs SET
        schema_version = ?, node_instance_id = ?, request_fingerprint = ?, job_id = ?, model = ?,
        local_state = ?, remote_status_raw = ?, created_at = ?, submission_started_at = ?,
        accepted_at = ?, last_observed_at = ?, completed_at = ?, actual_cost_usd = ?,
        output_relpath = ?, product_error_code = ?
    WHERE operation_id = ?
"""


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise PersistenceError("Durable timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PersistenceError("Durable timestamp is corrupt")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise PersistenceError("Durable timestamp is corrupt") from None
    if parsed.tzinfo is None:
        raise PersistenceError("Durable timestamp is corrupt")
    return parsed


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not value.is_finite() or value < 0:
        raise PersistenceError("Actual cost is invalid")
    return format(value, "f")


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PersistenceError("Actual cost state is corrupt")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise PersistenceError("Actual cost state is corrupt") from None
    if not parsed.is_finite() or parsed < 0:
        raise PersistenceError("Actual cost state is corrupt")
    return parsed


def _job_values(record: JobRecord) -> tuple[object, ...]:
    if record.schema_version != SCHEMA_VERSION:
        raise PersistenceError("Unsupported JobRecord schema version")
    if not record.operation_id or not record.model or not record.request_fingerprint:
        raise PersistenceError("Required durable job identity is missing")
    return (
        record.schema_version,
        record.operation_id,
        record.node_instance_id,
        record.request_fingerprint,
        record.job_id,
        record.model,
        record.local_state.value,
        record.remote_status_raw,
        _serialize_datetime(record.created_at),
        _serialize_datetime(record.submission_started_at),
        _serialize_datetime(record.accepted_at),
        _serialize_datetime(record.last_observed_at),
        _serialize_datetime(record.completed_at),
        _serialize_decimal(record.actual_cost_usd),
        record.output_relpath,
        record.product_error_code.value if record.product_error_code else None,
    )


def _as_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PersistenceError("Durable text state is corrupt")
    return value


def _parse_job(row: sqlite3.Row) -> JobRecord:
    try:
        operation_id = row["operation_id"]
        fingerprint = row["request_fingerprint"]
        model = row["model"]
        schema_version = row["schema_version"]
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(fingerprint, str)
            or not fingerprint
            or not isinstance(model, str)
            or not model
            or schema_version != SCHEMA_VERSION
        ):
            raise PersistenceError("Durable job identity is corrupt")
        job_id = _as_optional_string(row["job_id"])
        local_state = LocalLifecycleState(str(row["local_state"]))
        product_error_raw = _as_optional_string(row["product_error_code"])
        product_error = ProductErrorCode(product_error_raw) if product_error_raw else None
        created_at = _parse_datetime(row["created_at"])
        if created_at is None:
            raise PersistenceError("Durable job record is corrupt")
        record = JobRecord(
            schema_version=schema_version,
            operation_id=operation_id,
            node_instance_id=_as_optional_string(row["node_instance_id"]),
            request_fingerprint=fingerprint,
            job_id=job_id,
            model=model,
            local_state=local_state,
            remote_status_raw=_as_optional_string(row["remote_status_raw"]),
            created_at=created_at,
            submission_started_at=_parse_datetime(row["submission_started_at"]),
            accepted_at=_parse_datetime(row["accepted_at"]),
            last_observed_at=_parse_datetime(row["last_observed_at"]),
            completed_at=_parse_datetime(row["completed_at"]),
            actual_cost_usd=_parse_decimal(row["actual_cost_usd"]),
            output_relpath=_as_optional_string(row["output_relpath"]),
            product_error_code=product_error,
        )
    except (KeyError, TypeError, ValueError):
        raise PersistenceError("Durable job record is corrupt") from None
    if record.job_id is None and record.local_state in {
        LocalLifecycleState.ACCEPTED,
        LocalLifecycleState.POLLING,
        LocalLifecycleState.COMPLETED,
        LocalLifecycleState.DOWNLOADING,
        LocalLifecycleState.DONE,
        LocalLifecycleState.OBSERVATION_INTERRUPTED,
        LocalLifecycleState.FAILED,
        LocalLifecycleState.CANCELLED,
        LocalLifecycleState.EXPIRED,
        LocalLifecycleState.UNKNOWN_REMOTE_STATE,
    }:
        raise PersistenceError("Known-job lifecycle state is missing job identity")
    return record


class JobStore:
    """Small schema-v1 SQLite store; every mutation is its own committed transaction."""

    __slots__ = ("_path",)

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except (OSError, sqlite3.Error) as exc:
            raise PersistenceError("Unable to initialize durable local state") from exc

    @property
    def path(self) -> Path:
        """Return the configured database path for controlled diagnostics."""

        return self._path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, SCHEMA_VERSION):
                raise PersistenceError("Unsupported SQLite schema version")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
                    operation_id TEXT NOT NULL PRIMARY KEY,
                    node_instance_id TEXT,
                    request_fingerprint TEXT NOT NULL,
                    job_id TEXT UNIQUE,
                    model TEXT NOT NULL,
                    local_state TEXT NOT NULL,
                    remote_status_raw TEXT,
                    created_at TEXT NOT NULL,
                    submission_started_at TEXT,
                    accepted_at TEXT,
                    last_observed_at TEXT,
                    completed_at TEXT,
                    actual_cost_usd TEXT,
                    output_relpath TEXT,
                    product_error_code TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_catalog_meta (
                    singleton INTEGER NOT NULL PRIMARY KEY CHECK (singleton = 1),
                    observed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_models (
                    model_id TEXT NOT NULL PRIMARY KEY,
                    canonical_slug TEXT,
                    name TEXT,
                    supported_durations TEXT,
                    supported_resolutions TEXT,
                    supported_aspect_ratios TEXT,
                    supported_sizes TEXT,
                    supported_frame_types TEXT NOT NULL,
                    generate_audio INTEGER,
                    supports_seed INTEGER
                )
                """
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.commit()

    def get_by_operation_id(self, operation_id: str) -> JobRecord | None:
        """Load only by authoritative local operation identity."""

        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE operation_id = ?", (operation_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to read durable local state") from exc
        return _parse_job(row) if row is not None else None

    def get_by_job_id(self, job_id: str) -> JobRecord | None:
        """Load the one local record for an authoritative remote job identity."""

        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to read durable local state") from exc
        return _parse_job(row) if row is not None else None

    def insert(self, record: JobRecord) -> bool:
        """Insert one durable record, returning false on an identity race."""

        values = _job_values(record)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(_INSERT_JOB_SQL, values)
                except sqlite3.IntegrityError:
                    connection.rollback()
                    return False
                connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to persist durable local state") from exc
        return True

    def claim_submitting(self, record: JobRecord) -> bool:
        """Atomically acquire the single submit right for an operation_id."""

        if record.local_state is not LocalLifecycleState.SUBMITTING or record.job_id is not None:
            raise PersistenceError("Submit claim must be a pre-network SUBMITTING record")
        return self.insert(record)

    def save(self, record: JobRecord) -> None:
        """Replace one existing operation record without changing its authority key."""

        values = _job_values(record)
        update_values = tuple(
            value
            for column, value in zip(_JOB_COLUMNS, values, strict=True)
            if column != "operation_id"
        ) + (record.operation_id,)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(_UPDATE_JOB_SQL, update_values)
                if cursor.rowcount != 1:
                    connection.rollback()
                    raise PersistenceError("Durable operation record is missing")
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise PersistenceError("Durable job identity conflicts with existing state") from exc
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to persist durable local state") from exc

    def release_unsubmitted_claim(self, operation_id: str, request_fingerprint: str) -> bool:
        """Release only a proven pre-network claim after local request-policy failure."""

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    DELETE FROM jobs
                    WHERE operation_id = ?
                      AND request_fingerprint = ?
                      AND local_state = ?
                      AND job_id IS NULL
                    """,
                    (operation_id, request_fingerprint, LocalLifecycleState.SUBMITTING.value),
                )
                connection.commit()
                return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to release pre-network durable claim") from exc

    def replace_capability_catalog(
        self, capabilities: Iterable[ModelCapabilities], observed_at: datetime
    ) -> None:
        """Persist only normalized catalog fields from one successful live observation."""

        observed = _serialize_datetime(observed_at)
        if observed is None:
            raise PersistenceError("Capability observation timestamp is missing")
        rows = tuple(capabilities)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM capability_models")
                for item in rows:
                    connection.execute(
                        """
                        INSERT INTO capability_models (
                            model_id, canonical_slug, name, supported_durations,
                            supported_resolutions, supported_aspect_ratios, supported_sizes,
                            supported_frame_types, generate_audio, supports_seed
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.model_id,
                            item.canonical_slug,
                            item.name,
                            _json_tuple(item.supported_durations),
                            _json_tuple(item.supported_resolutions),
                            _json_tuple(item.supported_aspect_ratios),
                            _json_tuple(item.supported_sizes),
                            json.dumps(
                                sorted(frame.value for frame in item.supported_frame_types),
                                separators=(",", ":"),
                            ),
                            _optional_bool(item.generate_audio),
                            _optional_bool(item.supports_seed),
                        ),
                    )
                connection.execute(
                    """
                    INSERT INTO capability_catalog_meta (singleton, observed_at)
                    VALUES (1, ?)
                    ON CONFLICT(singleton) DO UPDATE SET observed_at = excluded.observed_at
                    """,
                    (observed,),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to persist capability catalog") from exc

    def load_capability_catalog(
        self,
    ) -> tuple[datetime, tuple[ModelCapabilities, ...]] | None:
        """Load the latest normalized catalog observation, including an empty catalog."""

        try:
            with self._connect() as connection:
                meta = connection.execute(
                    "SELECT observed_at FROM capability_catalog_meta WHERE singleton = 1"
                ).fetchone()
                if meta is None:
                    return None
                rows = connection.execute(
                    "SELECT * FROM capability_models ORDER BY model_id"
                ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError("Unable to read capability catalog") from exc
        observed_at = _parse_datetime(meta["observed_at"])
        if observed_at is None:
            raise PersistenceError("Capability catalog timestamp is corrupt")
        return observed_at, tuple(_parse_capability(row) for row in rows)


def _json_tuple(value: tuple[object, ...] | None) -> str | None:
    return json.dumps(value, separators=(",", ":")) if value is not None else None


def _optional_bool(value: bool | None) -> int | None:
    return int(value) if value is not None else None


def _load_optional_tuple(value: object, item_type: type[int] | type[str]) -> tuple[Any, ...] | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PersistenceError("Capability catalog value is corrupt")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        raise PersistenceError("Capability catalog value is corrupt") from None
    if not isinstance(decoded, list) or any(
        not isinstance(item, item_type) or (item_type is int and isinstance(item, bool))
        for item in decoded
    ):
        raise PersistenceError("Capability catalog value is corrupt")
    return tuple(decoded)


def _load_optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    if value not in (0, 1):
        raise PersistenceError("Capability boolean is corrupt")
    return bool(value)


def _parse_capability(row: sqlite3.Row) -> ModelCapabilities:
    model_id = row["model_id"]
    if not isinstance(model_id, str) or not model_id:
        raise PersistenceError("Capability model identity is corrupt")
    try:
        frame_raw = json.loads(str(row["supported_frame_types"]))
        if not isinstance(frame_raw, list) or any(not isinstance(item, str) for item in frame_raw):
            raise PersistenceError("Capability frame data is corrupt")
        frames = frozenset(FrameType(item) for item in frame_raw)
        durations = _load_optional_tuple(row["supported_durations"], int)
        resolutions = _load_optional_tuple(row["supported_resolutions"], str)
        aspects = _load_optional_tuple(row["supported_aspect_ratios"], str)
        sizes = _load_optional_tuple(row["supported_sizes"], str)
        return ModelCapabilities(
            model_id=model_id,
            canonical_slug=_as_optional_string(row["canonical_slug"]),
            name=_as_optional_string(row["name"]),
            supported_durations=durations,
            supported_resolutions=resolutions,
            supported_aspect_ratios=aspects,
            supported_sizes=sizes,
            supported_frame_types=frames,
            generate_audio=_load_optional_bool(row["generate_audio"]),
            supports_seed=_load_optional_bool(row["supports_seed"]),
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        raise PersistenceError("Capability catalog record is corrupt") from None


__all__ = ("JobStore", "SCHEMA_VERSION")
