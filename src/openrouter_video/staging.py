"""Exact-object staging ownership and opportunistic cleanup; no scheduler."""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from openrouter_video.capabilities import RequestValidator
from openrouter_video.errors import PersistenceError
from openrouter_video.execution_hooks import ExecutionControl
from openrouter_video.local_media import MAX_REQUEST_BYTES, NativeMediaError, run_file_worker
from openrouter_video.models import (
    GenerationRequest,
    InputReference,
    InputReferenceCollection,
    LocalLifecycleState,
)
from openrouter_video.persistence import JobStore
from openrouter_video.s3_upload import MediaUploader, StorageError

_TERMINAL = {
    LocalLifecycleState.COMPLETED,
    LocalLifecycleState.DOWNLOADING,
    LocalLifecycleState.DONE,
    LocalLifecycleState.FAILED,
    LocalLifecycleState.CANCELLED,
    LocalLifecycleState.EXPIRED,
    LocalLifecycleState.SUBMIT_REJECTED,
}


def has_local_media(request: GenerationRequest) -> bool:
    references = request.input_references.references if request.input_references else ()
    return any(item.local_media is not None for item in references) or (
        request.source_video is not None and request.source_video.local_media is not None
    )


class StagingManager:
    def __init__(self, store: JobStore, uploader: MediaUploader) -> None:
        self._store = store
        self._uploader = uploader

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._store.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    async def materialize(
        self, operation_id: str, request: GenerationRequest, control: ExecutionControl | None = None
    ) -> GenerationRequest:
        if not has_local_media(request):
            return request
        fingerprint = self._uploader.configuration_fingerprint()
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as connection:
                inserted = connection.execute(
                    "INSERT OR IGNORE INTO staging_operations VALUES (?, ?)", (operation_id, now)
                ).rowcount
            if inserted != 1:
                raise StorageError("Native staging operation already exists; do not resubmit.")
        except sqlite3.Error:
            raise PersistenceError("Unable to claim staging ownership.") from None
        total = 0

        async def stage(reference: InputReference | None) -> InputReference | None:
            nonlocal total
            if reference is None or reference.local_media is None:
                return reference
            if control is not None:
                control.raise_if_interrupted()
            media = reference.local_media
            with TemporaryDirectory(prefix="openrouter-video-") as temporary:
                path = Path(temporary) / ("source" + media.suffix)
                total += await run_file_worker(media.encode, path)
                if total > MAX_REQUEST_BYTES:
                    raise NativeMediaError("Native media exceeds the 512 MiB request limit.")
                if control is not None:
                    control.raise_if_interrupted()
                key = "openrouter-video/staging/" + secrets.token_hex(16) + media.suffix
                try:
                    with self._connect() as connection:
                        connection.execute(
                            "INSERT INTO staging_objects VALUES (?, ?, ?, ?, 0)",
                            (
                                key,
                                operation_id,
                                fingerprint,
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        )
                except sqlite3.Error:
                    raise PersistenceError("Unable to persist object ownership.") from None
                await self._uploader.upload(key, path, media.content_type)
                if control is not None:
                    control.raise_if_interrupted()
                result = InputReference(reference.kind, await self._uploader.presign_get(key))
                RequestValidator._validate_reference(result)
                return result

        try:
            source = await stage(request.source_video)
            references: list[InputReference] = []
            for item in request.input_references.references if request.input_references else ():
                staged = await stage(item)
                if staged is None:
                    raise StorageError("Native staging reference is missing.")
                references.append(staged)
            return replace(
                request,
                source_video=source,
                input_references=InputReferenceCollection(tuple(references))
                if request.input_references is not None
                else None,
            )
        except BaseException:
            await self.cleanup_operation(operation_id)
            raise

    async def cleanup_operation(self, operation_id: str) -> None:
        """Called only for proven no-submit or terminal job disposition."""
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE staging_objects SET cleanup_pending = 1 WHERE operation_id = ?",
                    (operation_id,),
                )
            await self.cleanup()
        except (sqlite3.Error, PersistenceError, StorageError):
            return

    async def cleanup(self) -> None:
        """Bounded opportunistic sweep. Unknown/config-mismatched ownership is preserved."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM staging_objects ORDER BY cleanup_pending DESC, created_at"
                ).fetchall()
            if not rows:
                return
            fingerprint = self._uploader.configuration_fingerprint()
            cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            for row in rows:
                if row["configuration_fingerprint"] != fingerprint:
                    continue
                record = self._store.get_by_operation_id(row["operation_id"])
                terminal = record is not None and (
                    record.local_state in _TERMINAL or record.remote_status_raw == "completed"
                )
                old = datetime.fromisoformat(row["created_at"]) <= cutoff
                if not (row["cleanup_pending"] or terminal or old):
                    continue
                with self._connect() as connection:
                    connection.execute(
                        "UPDATE staging_objects SET cleanup_pending = 1 WHERE object_key = ?",
                        (row["object_key"],),
                    )
                try:
                    await self._uploader.delete(row["object_key"])
                except StorageError:
                    continue
                with self._connect() as connection:
                    connection.execute(
                        "DELETE FROM staging_objects WHERE object_key = ?", (row["object_key"],)
                    )
        except (sqlite3.Error, PersistenceError, StorageError, ValueError, TypeError):
            return
