from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from openrouter_video.application import GenerateService, OperationInterrupted, ResumeService
from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.errors import OpenRouterHTTPError, TransportError
from openrouter_video.execution_hooks import ExecutionControl
from openrouter_video.local_media import LocalMedia, NativeMediaError
from openrouter_video.media import DownloadService
from openrouter_video.models import (
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    LocalLifecycleState,
    ModelCapabilities,
    ProductErrorCode,
    RemoteJobSnapshot,
)
from openrouter_video.persistence import DATABASE_SCHEMA_VERSION, JobStore
from openrouter_video.policy import Operation
from openrouter_video.s3_upload import StorageError
from openrouter_video.staging import StagingManager

MODEL = "bytedance/seedance-2.5"


def native(kind: InputReferenceKind = InputReferenceKind.VIDEO) -> InputReference:
    def write(path: Path) -> None:
        path.write_bytes(b"private-media-canary")

    return InputReference(
        kind,
        local_media=LocalMedia(
            "video/mp4" if kind is InputReferenceKind.VIDEO else "audio/wav",
            ".mp4" if kind is InputReferenceKind.VIDEO else ".wav",
            write,
        ),
    )


def request(*refs: InputReference) -> GenerationRequest:
    refs = refs or (native(),)
    kinds = {ref.kind for ref in refs}
    method = (
        InferenceMethod.MMR2V
        if len(kinds) > 1
        else InferenceMethod.AR2V
        if InputReferenceKind.AUDIO in kinds
        else InferenceMethod.VR2V
    )
    return GenerationRequest(
        MODEL, "private-prompt-canary", method, input_references=InputReferenceCollection(refs)
    )


class Uploader:
    def __init__(self) -> None:
        self.uploaded: list[str] = []
        self.deleted: list[str] = []
        self.paths: list[Path] = []
        self.fingerprint = "config-one"
        self.fail_upload = 0
        self.fail_delete = False
        self.control: ExecutionControl | None = None
        self.store: JobStore | None = None

    def configuration_fingerprint(self) -> str:
        return self.fingerprint

    async def upload(self, key: str, path: Path, content_type: str) -> None:
        # Ownership must be durable BEFORE PUT, and file must be closed (Windows open).
        assert self.store is not None
        with sqlite3.connect(self.store.path) as connection:
            assert (
                connection.execute(
                    "SELECT COUNT(*) FROM staging_objects WHERE object_key=?", (key,)
                ).fetchone()[0]
                == 1
            )
        with path.open("rb+") as file:
            assert file.read() == b"private-media-canary"
        self.uploaded.append(key)
        self.paths.append(path)
        if self.control is not None:
            self.control.request_interrupt()
        if len(self.uploaded) == self.fail_upload:
            raise StorageError("Storage operation failed.")

    async def presign_get(self, key: str) -> str:
        return "https://storage.example.test/" + key + "?signature=private-signed-canary"

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        if self.fail_delete:
            raise StorageError("Storage operation failed.")


class Discovery:
    async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
        return (ModelCapabilities(model_id=MODEL), ModelCapabilities(model_id="vendor/unsupported"))


async def _no_sleep(_: float) -> None:
    return None


class Client:
    def __init__(
        self,
        submit: RemoteJobSnapshot | BaseException,
        polls: list[RemoteJobSnapshot | BaseException],
    ) -> None:
        self.submit_outcome = submit
        self.polls = polls
        self.submit_calls = 0
        self.poll_calls = 0
        self.payload: dict[str, object] = {}

    async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot:
        self.submit_calls += 1
        self.payload = request.to_openrouter_payload()
        if isinstance(self.submit_outcome, BaseException):
            raise self.submit_outcome
        return self.submit_outcome

    async def get_job(self, job_id: str) -> RemoteJobSnapshot:
        outcome = self.polls[min(self.poll_calls, len(self.polls) - 1)]
        self.poll_calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @asynccontextmanager
    async def stream_content(self, job_id: str) -> AsyncIterator[httpx.Response]:
        yield httpx.Response(
            200,
            content=b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32,
            request=httpx.Request("GET", "https://openrouter.ai/api/v1/videos/job-1/content"),
        )


def setup(
    tmp_path: Path,
    client: Client,
    uploader: Uploader | None = None,
    control: ExecutionControl | None = None,
) -> tuple[GenerateService, JobStore, Uploader, StagingManager]:
    store = JobStore(tmp_path / "jobs.sqlite3")
    up = uploader or Uploader()
    up.store = store
    staging = StagingManager(store, up)
    service = GenerateService(
        capabilities=CapabilityService(client=Discovery(), store=store),
        validator=RequestValidator(),
        store=store,
        submit_client=client,
        observation_client=client,
        downloader=DownloadService(client=client, output_root=tmp_path / "output", sleep=_no_sleep),
        sleep=_no_sleep,
        monotonic=lambda: 0.0,
        staging=staging,
        control=control,
    )
    return service, store, up, staging


def rows(store: JobStore) -> list[Any]:
    with sqlite3.connect(store.path) as connection:
        return connection.execute("SELECT * FROM staging_objects").fetchall()


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "expired"])
def test_terminal_cleanup_and_mixed_order(tmp_path: Path, status: str) -> None:
    client = Client(RemoteJobSnapshot("job-1", "pending"), [RemoteJobSnapshot("job-1", status)])
    service, store, up, _ = setup(tmp_path, client)
    video = native()
    audio = native(InputReferenceKind.AUDIO)
    image = InputReference(InputReferenceKind.IMAGE, "https://assets.example/image.png")
    result = asyncio.run(service.generate("op-1", request(video, image, audio, video)))
    assert client.submit_calls == 1
    refs: Any = client.payload["input_references"]
    assert [item["type"] for item in refs] == ["video_url", "image_url", "audio_url", "video_url"]
    assert refs[0] != refs[3]  # Duplicate occurrences retained, independently owned random keys.
    assert len(up.uploaded) == 3 and set(up.deleted) == set(up.uploaded)
    assert not rows(store) and all(not path.exists() for path in up.paths)
    assert result.state is (
        LocalLifecycleState.DONE if status == "completed" else LocalLifecycleState(status.upper())
    )
    data = store.path.read_bytes()
    assert all(
        canary not in data
        for canary in [
            b"private-media-canary",
            b"private-signed-canary",
            b"private-prompt-canary",
            str(tmp_path).encode(),
        ]
    )


@pytest.mark.parametrize(
    "failure", [TransportError("ambiguous"), OpenRouterHTTPError(500, Operation.SUBMIT)]
)
def test_ambiguous_submit_retains_objects_and_never_reuploads(
    tmp_path: Path, failure: BaseException
) -> None:
    client = Client(failure, [])
    service, store, up, _ = setup(tmp_path, client)
    first = asyncio.run(service.generate("op-1", request()))
    second = asyncio.run(service.generate("op-1", request()))
    assert first.state is second.state is LocalLifecycleState.SUBMISSION_UNKNOWN
    assert client.submit_calls == 1 and len(up.uploaded) == 1 and not up.deleted
    assert len(rows(store)) == 1


def test_partial_upload_failure_proves_no_submit_and_deletes_exact_owned_objects(
    tmp_path: Path,
) -> None:
    client = Client(RemoteJobSnapshot("job-1", "pending"), [])
    up = Uploader()
    up.fail_upload = 2
    service, store, up, _ = setup(tmp_path, client, up)
    result = asyncio.run(
        service.generate("op-1", request(native(), native(InputReferenceKind.AUDIO)))
    )
    assert result.error and result.error.code is ProductErrorCode.STORAGE_UPLOAD_FAILED
    assert client.submit_calls == 0 and len(up.uploaded) == 2 and up.deleted == up.uploaded
    assert not rows(store) and all(not path.exists() for path in up.paths)


def test_capabilities_fail_before_conversion_or_upload(tmp_path: Path) -> None:
    client = Client(RemoteJobSnapshot("job-1", "pending"), [])
    service, store, up, _ = setup(tmp_path, client)

    def forbidden(path: Path) -> None:
        raise AssertionError("conversion must not run")

    media = InputReference(
        InputReferenceKind.VIDEO, local_media=LocalMedia("video/mp4", ".mp4", forbidden)
    )
    result = asyncio.run(
        service.generate("op-1", replace(request(media), model="vendor/unsupported"))
    )
    assert result.error and not up.uploaded and client.submit_calls == 0 and not rows(store)


def test_definite_rejection_deletes_without_resubmit(tmp_path: Path) -> None:
    client = Client(OpenRouterHTTPError(422, Operation.SUBMIT), [])
    service, _, up, _ = setup(tmp_path, client)
    asyncio.run(service.generate("op-1", request()))
    asyncio.run(service.generate("op-1", request()))
    assert client.submit_calls == 1 and len(up.uploaded) == len(up.deleted) == 1


def test_interrupt_before_submit_deletes_and_posts_zero(tmp_path: Path) -> None:
    control = ExecutionControl()
    up = Uploader()
    up.control = control
    client = Client(RemoteJobSnapshot("job-1", "pending"), [])
    service, store, up, _ = setup(tmp_path, client, up, control)
    with pytest.raises(OperationInterrupted):
        asyncio.run(service.generate("op-1", request()))
    assert client.submit_calls == 0 and up.deleted == up.uploaded and not rows(store)


@pytest.mark.parametrize(
    "outcome", [TransportError("poll failure"), RemoteJobSnapshot("job-1", "future-status")]
)
def test_poll_failure_or_unknown_status_retains_until_resume(
    tmp_path: Path, outcome: RemoteJobSnapshot | BaseException
) -> None:
    client = Client(RemoteJobSnapshot("job-1", "pending"), [outcome])
    service, store, up, staging = setup(tmp_path, client)
    asyncio.run(service.generate("op-1", request()))
    assert not up.deleted and len(rows(store)) == 1
    client.polls = [RemoteJobSnapshot("job-1", "failed")]
    client.poll_calls = 0
    resume = ResumeService(
        observation_client=client,
        store=store,
        downloader=DownloadService(client=client, output_root=tmp_path / "output"),
        staging=staging,
        sleep=_no_sleep,
        monotonic=lambda: 0.0,
    )
    assert asyncio.run(resume.resume("job-1")).state is LocalLifecycleState.FAILED
    assert client.submit_calls == 1 and len(up.uploaded) == len(up.deleted) == 1


def test_cleanup_failure_survives_restart_and_configuration_mismatch(tmp_path: Path) -> None:
    client = Client(OpenRouterHTTPError(422, Operation.SUBMIT), [])
    up = Uploader()
    up.fail_delete = True
    service, store, up, _ = setup(tmp_path, client, up)
    asyncio.run(service.generate("op-1", request()))
    assert len(rows(store)) == 1 and rows(store)[0][-1] == 1
    up.fail_delete = False
    up.fingerprint = "other-config"
    up.deleted = []
    restart = StagingManager(JobStore(store.path), up)
    asyncio.run(restart.cleanup())
    assert not up.deleted and len(rows(store)) == 1
    up.fingerprint = "config-one"
    asyncio.run(restart.cleanup())
    assert not rows(store)


def test_orphan_48h_cleanup_only_ledger_keys(tmp_path: Path) -> None:
    client = Client(TransportError("ambiguous"), [])
    service, store, up, staging = setup(tmp_path, client)
    asyncio.run(service.generate("op-1", request()))
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE staging_objects SET created_at=?",
            ((datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(),),
        )
    asyncio.run(staging.cleanup())
    assert up.deleted == up.uploaded and not rows(store)
    # Expiry never authorizes regenerate/reupload.
    asyncio.run(service.generate("op-1", request()))
    assert client.submit_calls == 1 and len(up.uploaded) == 1


def test_cancellation_waits_for_conversion_then_removes_temp_file(tmp_path: Path) -> None:
    client = Client(RemoteJobSnapshot("job-1", "pending"), [])
    _, _, up, staging = setup(tmp_path, client)
    started = threading.Event()
    release = threading.Event()
    paths: list[Path] = []

    def encode(path: Path) -> None:
        paths.append(path)
        started.set()
        release.wait(5)
        path.write_bytes(b"private-media-canary")

    async def scenario() -> None:
        task = asyncio.create_task(
            staging.materialize(
                "op-1",
                request(
                    InputReference(
                        InputReferenceKind.VIDEO,
                        local_media=LocalMedia("video/mp4", ".mp4", encode),
                    )
                ),
            )
        )
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert paths and not paths[0].exists() and not up.uploaded


def test_v4_migration_preserves_jobs_and_creates_empty_ledger(tmp_path: Path) -> None:
    client = Client(TransportError("ambiguous"), [])
    service, store, _, _ = setup(tmp_path, client)
    asyncio.run(service.generate("legacy-op", GenerationRequest(MODEL, "prompt")))
    before = store.get_by_operation_id("legacy-op")
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TABLE staging_objects")
        connection.execute("DROP TABLE staging_operations")
        connection.execute("PRAGMA user_version=4")
    migrated = JobStore(store.path)
    assert migrated.get_by_operation_id("legacy-op") == before and rows(migrated) == []
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == DATABASE_SCHEMA_VERSION


def test_closed_file_size_checks(tmp_path: Path) -> None:
    for size in (0, 256 * 1024 * 1024 + 1):

        def encode(path: Path, length: int = size) -> None:
            with path.open("wb") as file:
                file.truncate(length)

        with pytest.raises(NativeMediaError):
            LocalMedia("video/mp4", ".mp4", encode).encode(tmp_path / "bounded.mp4")


def test_request_byte_limit_removes_partial_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import openrouter_video.staging as module

    monkeypatch.setattr(module, "MAX_REQUEST_BYTES", len(b"private-media-canary"))
    client = Client(RemoteJobSnapshot("job-1", "pending"), [])
    service, store, up, _ = setup(tmp_path, client)
    result = asyncio.run(
        service.generate("op-1", request(native(), native(InputReferenceKind.AUDIO)))
    )
    assert result.error and result.error.code is ProductErrorCode.NATIVE_MEDIA_INVALID
    assert (
        client.submit_calls == 0
        and len(up.uploaded) == 1
        and up.deleted == up.uploaded
        and not rows(store)
    )


def test_concurrent_claim_stages_only_once(tmp_path: Path) -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()

        class BlockingClient(Client):
            async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot:
                started.set()
                await release.wait()
                return await super().submit_video(request)

        client = BlockingClient(
            RemoteJobSnapshot("job-1", "pending"), [RemoteJobSnapshot("job-1", "failed")]
        )
        service, _, up, _ = setup(tmp_path, client)
        winner = asyncio.create_task(service.generate("op-1", request()))
        await started.wait()
        loser = await service.generate("op-1", request())
        assert (
            loser.state is LocalLifecycleState.SUBMISSION_UNKNOWN
            and len(up.uploaded) == 1
            and not up.deleted
        )
        release.set()
        await winner
        assert client.submit_calls == 1 and len(up.uploaded) == len(up.deleted) == 1

    asyncio.run(scenario())


def test_missing_storage_credentials_posts_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openrouter_video.s3_upload import S3MediaUploader

    for name in (
        "ENDPOINT",
        "REGION",
        "BUCKET",
        "ACCESS_KEY_ID",
        "SECRET_ACCESS_KEY",
        "SESSION_TOKEN",
    ):
        monkeypatch.delenv("OPENROUTER_VIDEO_S3_" + name, raising=False)
    client = Client(RemoteJobSnapshot("job-1", "pending"), [])
    service, store, _, _ = setup(tmp_path, client)
    service._staging = StagingManager(store, S3MediaUploader())
    result = asyncio.run(service.generate("op-1", request()))
    assert result.error and "Configure local S3" in result.error.message
    assert client.submit_calls == 0 and not rows(store)


def test_source_video_native_edit_stages_first(tmp_path: Path) -> None:
    client = Client(RemoteJobSnapshot("job-1", "pending"), [RemoteJobSnapshot("job-1", "failed")])
    service, _, up, _ = setup(tmp_path, client)
    intent = replace(
        request(native(InputReferenceKind.AUDIO)),
        inference_method=InferenceMethod.V2V_EDIT,
        source_video=native(),
    )
    asyncio.run(service.generate("op-1", intent))
    refs: Any = client.payload["input_references"]
    assert [item["type"] for item in refs] == ["video_url", "audio_url"]
    assert len(up.uploaded) == len(up.deleted) == 2 and client.submit_calls == 1
