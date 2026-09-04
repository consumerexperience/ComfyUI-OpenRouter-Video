"""Billing-safe Generate and submit-incapable Resume application services."""

from __future__ import annotations

import asyncio
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timezone

from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.client import ObservationClient, SubmitClient
from openrouter_video.errors import (
    InvalidVideoResponseError,
    LocalDiskError,
    MalformedOpenRouterResponseError,
    MediaDownloadError,
    OpenRouterHTTPError,
    PersistenceError,
    ProductFailureError,
    RequestPolicyError,
    TransportError,
)
from openrouter_video.lifecycle import transition
from openrouter_video.media import DownloadService
from openrouter_video.models import (
    BillingContext,
    GenerationRequest,
    GenerationResult,
    JobRecord,
    LocalLifecycleState,
    ProductError,
    ProductErrorCode,
    RemoteJobSnapshot,
    VideoArtifact,
    request_fingerprint_v1,
)
from openrouter_video.persistence import SCHEMA_VERSION, JobStore

POLL_INTERVAL_SECONDS = 30.0
POLL_CEILING_SECONDS = 60 * 60.0
POLL_TRANSIENT_ATTEMPTS = 5
_BACKOFF_SECONDS = (5.0, 10.0, 20.0, 30.0, 60.0)

Sleep = Callable[[float], Awaitable[None]]
Now = Callable[[], datetime]
Monotonic = Callable[[], float]
Jitter = Callable[[float], float]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jitter(value: float) -> float:
    return random.uniform(value * 0.8, value * 1.2)  # noqa: S311 - retry timing only


def _product_error(
    code: ProductErrorCode,
    context: BillingContext,
    *,
    retryable: bool = False,
) -> ProductError:
    messages = {
        ProductErrorCode.API_KEY_MISSING: "Configure the OpenRouter API key before continuing.",
        ProductErrorCode.API_KEY_INVALID: "OpenRouter rejected the configured API key.",
        ProductErrorCode.INSUFFICIENT_CREDITS: "OpenRouter reported insufficient credits.",
        ProductErrorCode.MODEL_UNAVAILABLE: "The selected video model is unavailable.",
        ProductErrorCode.UNSUPPORTED_PARAMETER: "OpenRouter rejected a generation parameter.",
        ProductErrorCode.RATE_LIMITED_SUBMIT: "OpenRouter rate-limited the submit attempt.",
        ProductErrorCode.RATE_LIMITED_POLL: "OpenRouter rate-limited job observation.",
        ProductErrorCode.SUBMISSION_UNKNOWN: "The submit outcome is unknown; do not resubmit.",
        ProductErrorCode.STATUS_CHECK_FAILED: "Job observation was interrupted.",
        ProductErrorCode.GENERATION_FAILED: "The remote video generation failed.",
        ProductErrorCode.JOB_CANCELLED: "The remote video generation was cancelled.",
        ProductErrorCode.JOB_EXPIRED: "The remote video generation expired.",
        ProductErrorCode.JOB_NOT_FOUND: "OpenRouter could not find the supplied job.",
        ProductErrorCode.UNKNOWN_REMOTE_STATE: "OpenRouter returned an unknown job state.",
        ProductErrorCode.DOWNLOAD_FAILED: "The generated video download was interrupted.",
        ProductErrorCode.INVALID_VIDEO_RESPONSE: "The downloaded content is not a supported video.",
        ProductErrorCode.DISK_ERROR: "The local video artifact could not be stored.",
        ProductErrorCode.LOCAL_STATE_CORRUPT: (
            "Durable recovery state is unavailable or inconsistent."
        ),
        ProductErrorCode.ATTRIBUTION_CONFIG_INVALID: "Official application identity is invalid.",
    }
    return ProductError(code, messages.get(code, code.value), context, retryable)


def _result(
    record: JobRecord,
    *,
    error: ProductError | None = None,
    artifact: VideoArtifact | None = None,
) -> GenerationResult:
    return GenerationResult(
        state=record.local_state,
        job_id=record.job_id,
        actual_cost_usd=record.actual_cost_usd,
        artifact=artifact,
        error=error,
    )


class _ObservationCoordinator:
    __slots__ = ("_downloader", "_jitter", "_monotonic", "_now", "_observation", "_sleep", "_store")

    def __init__(
        self,
        *,
        observation_client: ObservationClient,
        store: JobStore,
        downloader: DownloadService,
        sleep: Sleep,
        now: Now,
        monotonic: Monotonic,
        jitter: Jitter,
    ) -> None:
        self._observation = observation_client
        self._store = store
        self._downloader = downloader
        self._sleep = sleep
        self._now = now
        self._monotonic = monotonic
        self._jitter = jitter

    async def reconcile(self, record: JobRecord) -> GenerationResult:
        """Continue only the known durable operation represented by record."""

        if record.local_state is LocalLifecycleState.DONE:
            if record.output_relpath is None:
                return _result(
                    record,
                    error=_product_error(
                        ProductErrorCode.LOCAL_STATE_CORRUPT,
                        BillingContext.KNOWN_JOB_EXISTS,
                    ),
                )
            try:
                artifact = self._downloader.load_artifact(record.output_relpath)
            except (LocalDiskError, InvalidVideoResponseError):
                return _result(
                    record,
                    error=_product_error(
                        ProductErrorCode.LOCAL_STATE_CORRUPT,
                        BillingContext.KNOWN_JOB_EXISTS,
                    ),
                )
            return _result(record, artifact=artifact)
        if record.local_state is LocalLifecycleState.SUBMIT_REJECTED:
            code = record.product_error_code or ProductErrorCode.LOCAL_STATE_CORRUPT
            return _result(record, error=_product_error(code, BillingContext.NO_SUBMIT))
        if record.local_state in {
            LocalLifecycleState.SUBMITTING,
            LocalLifecycleState.SUBMISSION_UNKNOWN,
        }:
            return _result(
                replace(record, local_state=LocalLifecycleState.SUBMISSION_UNKNOWN),
                error=_product_error(
                    ProductErrorCode.SUBMISSION_UNKNOWN,
                    BillingContext.MAY_HAVE_SUBMITTED,
                ),
            )
        terminal_codes = {
            LocalLifecycleState.FAILED: ProductErrorCode.GENERATION_FAILED,
            LocalLifecycleState.CANCELLED: ProductErrorCode.JOB_CANCELLED,
            LocalLifecycleState.EXPIRED: ProductErrorCode.JOB_EXPIRED,
        }
        if record.local_state in terminal_codes:
            return _result(
                record,
                error=_product_error(
                    terminal_codes[record.local_state],
                    BillingContext.KNOWN_JOB_EXISTS,
                ),
            )
        if record.local_state in {
            LocalLifecycleState.COMPLETED,
            LocalLifecycleState.DOWNLOADING,
        } or (
            record.local_state is LocalLifecycleState.OBSERVATION_INTERRUPTED
            and record.remote_status_raw == "completed"
        ):
            return await self._download(record)
        if record.local_state in {
            LocalLifecycleState.ACCEPTED,
            LocalLifecycleState.POLLING,
            LocalLifecycleState.OBSERVATION_INTERRUPTED,
            LocalLifecycleState.UNKNOWN_REMOTE_STATE,
        }:
            return await self._poll(record)
        return _result(
            record,
            error=_product_error(
                ProductErrorCode.LOCAL_STATE_CORRUPT,
                BillingContext.KNOWN_JOB_EXISTS
                if record.job_id is not None
                else BillingContext.MAY_HAVE_SUBMITTED,
            ),
        )

    async def _poll(self, record: JobRecord) -> GenerationResult:
        if record.job_id is None:
            return _result(
                record,
                error=_product_error(
                    ProductErrorCode.LOCAL_STATE_CORRUPT,
                    BillingContext.MAY_HAVE_SUBMITTED,
                ),
            )
        job_id = record.job_id
        if record.local_state is not LocalLifecycleState.POLLING:
            record = transition(record, LocalLifecycleState.POLLING, now=self._now())
            self._store.save(record)
        started = self._monotonic()
        consecutive_failures = 0
        last_http_status: int | None = None
        while self._monotonic() - started < POLL_CEILING_SECONDS:
            try:
                snapshot = await self._observation.get_job(job_id)
            except (TransportError, OpenRouterHTTPError) as exc:
                if not _retryable_observation(exc):
                    code = _poll_error_code(exc)
                    return self._interrupt(record, code, retryable=False)
                consecutive_failures += 1
                last_http_status = exc.status_code if isinstance(exc, OpenRouterHTTPError) else None
                if consecutive_failures >= POLL_TRANSIENT_ATTEMPTS:
                    code = (
                        ProductErrorCode.RATE_LIMITED_POLL
                        if last_http_status == 429
                        else ProductErrorCode.STATUS_CHECK_FAILED
                    )
                    return self._interrupt(record, code, retryable=True)
                retry_after = (
                    exc.retry_after_seconds if isinstance(exc, OpenRouterHTTPError) else None
                )
                backoff = _BACKOFF_SECONDS[consecutive_failures - 1]
                await self._sleep(retry_after if retry_after is not None else self._jitter(backoff))
                continue
            except RequestPolicyError as exc:
                code = (
                    ProductErrorCode.API_KEY_MISSING
                    if "credential" in str(exc).lower()
                    else ProductErrorCode.ATTRIBUTION_CONFIG_INVALID
                )
                return self._interrupt(record, code, retryable=False)
            except MalformedOpenRouterResponseError:
                return self._interrupt(record, ProductErrorCode.STATUS_CHECK_FAILED, retryable=True)

            consecutive_failures = 0
            record = self._apply_observation(record, snapshot)
            if record.local_state is LocalLifecycleState.POLLING:
                self._store.save(record)
                await self._sleep(POLL_INTERVAL_SECONDS)
                continue
            if record.local_state is LocalLifecycleState.COMPLETED:
                self._store.save(record)
                return await self._download(record)
            self._store.save(record)
            if record.local_state is LocalLifecycleState.UNKNOWN_REMOTE_STATE:
                return _result(
                    record,
                    error=_product_error(
                        ProductErrorCode.UNKNOWN_REMOTE_STATE,
                        BillingContext.KNOWN_JOB_EXISTS,
                    ),
                )
            return await self.reconcile(record)
        return self._interrupt(record, ProductErrorCode.STATUS_CHECK_FAILED, retryable=True)

    def _apply_observation(self, record: JobRecord, snapshot: RemoteJobSnapshot) -> JobRecord:
        status = snapshot.status_raw.lower()
        cost = snapshot.usage.actual_cost_usd
        next_cost = cost if cost is not None else record.actual_cost_usd
        if status in {"pending", "in_progress"}:
            updated = transition(
                record,
                LocalLifecycleState.POLLING,
                now=self._now(),
                remote_status_raw=status,
            )
        elif status == "completed":
            updated = transition(
                record,
                LocalLifecycleState.COMPLETED,
                now=self._now(),
                remote_status_raw=status,
            )
        elif status == "failed":
            updated = transition(
                record,
                LocalLifecycleState.FAILED,
                now=self._now(),
                remote_status_raw=status,
            )
        elif status == "cancelled":
            updated = transition(
                record,
                LocalLifecycleState.CANCELLED,
                now=self._now(),
                remote_status_raw=status,
            )
        elif status == "expired":
            updated = transition(
                record,
                LocalLifecycleState.EXPIRED,
                now=self._now(),
                remote_status_raw=status,
            )
        else:
            updated = transition(
                record,
                LocalLifecycleState.UNKNOWN_REMOTE_STATE,
                now=self._now(),
                remote_status_raw=snapshot.status_raw,
            )
        code_by_state = {
            LocalLifecycleState.FAILED: ProductErrorCode.GENERATION_FAILED,
            LocalLifecycleState.CANCELLED: ProductErrorCode.JOB_CANCELLED,
            LocalLifecycleState.EXPIRED: ProductErrorCode.JOB_EXPIRED,
            LocalLifecycleState.UNKNOWN_REMOTE_STATE: ProductErrorCode.UNKNOWN_REMOTE_STATE,
        }
        return replace(
            updated,
            actual_cost_usd=next_cost,
            product_error_code=code_by_state.get(updated.local_state),
        )

    async def _download(self, record: JobRecord) -> GenerationResult:
        if record.job_id is None:
            return _result(
                record,
                error=_product_error(
                    ProductErrorCode.LOCAL_STATE_CORRUPT,
                    BillingContext.MAY_HAVE_SUBMITTED,
                ),
            )
        job_id = record.job_id
        if record.local_state is not LocalLifecycleState.DOWNLOADING:
            record = transition(record, LocalLifecycleState.DOWNLOADING, now=self._now())
            self._store.save(record)
        try:
            artifact = await self._downloader.download(job_id)
        except InvalidVideoResponseError:
            return self._interrupt(record, ProductErrorCode.INVALID_VIDEO_RESPONSE, retryable=True)
        except LocalDiskError:
            return self._interrupt(record, ProductErrorCode.DISK_ERROR, retryable=False)
        except MediaDownloadError:
            return self._interrupt(record, ProductErrorCode.DOWNLOAD_FAILED, retryable=True)
        record = transition(record, LocalLifecycleState.DONE, now=self._now())
        record = replace(record, output_relpath=self._downloader.relative_path(artifact))
        self._store.save(record)
        return _result(record, artifact=artifact)

    def _interrupt(
        self,
        record: JobRecord,
        code: ProductErrorCode,
        *,
        retryable: bool,
    ) -> GenerationResult:
        if record.local_state is not LocalLifecycleState.OBSERVATION_INTERRUPTED:
            record = transition(
                record,
                LocalLifecycleState.OBSERVATION_INTERRUPTED,
                now=self._now(),
            )
        record = replace(record, product_error_code=code)
        self._store.save(record)
        return _result(
            record,
            error=_product_error(
                code,
                BillingContext.KNOWN_JOB_EXISTS,
                retryable=retryable,
            ),
        )


class GenerateService:
    """Own the sole paid-submit capability and reconcile operation_id before POST."""

    __slots__ = ("_capabilities", "_coordinator", "_now", "_store", "_submit", "_validator")

    def __init__(
        self,
        *,
        capabilities: CapabilityService,
        validator: RequestValidator,
        store: JobStore,
        submit_client: SubmitClient,
        observation_client: ObservationClient,
        downloader: DownloadService,
        sleep: Sleep = asyncio.sleep,
        now: Now = _utc_now,
        monotonic: Monotonic = time.monotonic,
        jitter: Jitter = _jitter,
    ) -> None:
        self._capabilities = capabilities
        self._validator = validator
        self._store = store
        self._submit = submit_client
        self._now = now
        self._coordinator = _ObservationCoordinator(
            observation_client=observation_client,
            store=store,
            downloader=downloader,
            sleep=sleep,
            now=now,
            monotonic=monotonic,
            jitter=jitter,
        )

    async def generate(self, operation_id: str, request: GenerationRequest) -> GenerationResult:
        """Validate, atomically claim, submit once, persist job_id, then observe."""

        if not operation_id or operation_id != operation_id.strip():
            return GenerationResult(
                LocalLifecycleState.NOT_SUBMITTED,
                None,
                error=_product_error(
                    ProductErrorCode.UNSUPPORTED_PARAMETER,
                    BillingContext.NO_SUBMIT,
                ),
            )
        try:
            self._validator.validate_shape(request)
        except ProductFailureError as exc:
            return GenerationResult(LocalLifecycleState.NOT_SUBMITTED, None, error=exc.error)
        fingerprint = request_fingerprint_v1(request)
        try:
            existing = self._store.get_by_operation_id(operation_id)
        except PersistenceError:
            return _local_state_failure(None)
        if existing is not None:
            return await self._reconcile_existing(existing, fingerprint)

        try:
            capability = await self._capabilities.resolve(request.model)
            self._validator.validate_capabilities(request, capability)
        except ProductFailureError as exc:
            return GenerationResult(LocalLifecycleState.NOT_SUBMITTED, None, error=exc.error)
        except PersistenceError:
            return _local_state_failure(None)

        now = self._now()
        record = JobRecord(
            schema_version=SCHEMA_VERSION,
            operation_id=operation_id,
            request_fingerprint=fingerprint,
            model=request.model,
            local_state=LocalLifecycleState.SUBMITTING,
            created_at=now,
            submission_started_at=now,
        )
        try:
            acquired = self._store.claim_submitting(record)
        except PersistenceError:
            return _local_state_failure(None)
        if not acquired:
            try:
                raced = self._store.get_by_operation_id(operation_id)
            except PersistenceError:
                return _local_state_failure(None)
            if raced is None:
                return _local_state_failure(None)
            return await self._reconcile_existing(raced, fingerprint)

        try:
            snapshot = await self._submit.submit_video(request)
        except RequestPolicyError as exc:
            try:
                self._store.release_unsubmitted_claim(operation_id, fingerprint)
            except PersistenceError:
                return _local_state_failure(record)
            code = (
                ProductErrorCode.API_KEY_MISSING
                if "credential" in str(exc).lower()
                else ProductErrorCode.ATTRIBUTION_CONFIG_INVALID
            )
            return GenerationResult(
                LocalLifecycleState.NOT_SUBMITTED,
                None,
                error=_product_error(code, BillingContext.NO_SUBMIT),
            )
        except OpenRouterHTTPError as exc:
            if 400 <= exc.status_code <= 499:
                return self._persist_definite_rejection(record, _submit_rejection_code(exc))
            return self._persist_submission_unknown(record)
        except (TransportError, MalformedOpenRouterResponseError):
            return self._persist_submission_unknown(record)

        record = transition(
            record,
            LocalLifecycleState.ACCEPTED,
            now=self._now(),
            job_id=snapshot.job_id,
            remote_status_raw=snapshot.status_raw,
        )
        try:
            self._store.save(record)
        except PersistenceError:
            return _local_state_failure(record)
        try:
            return await self._coordinator.reconcile(record)
        except PersistenceError:
            return _local_state_failure(record)

    async def _reconcile_existing(self, record: JobRecord, fingerprint: str) -> GenerationResult:
        if record.request_fingerprint != fingerprint:
            context = (
                BillingContext.KNOWN_JOB_EXISTS
                if record.job_id is not None
                else BillingContext.MAY_HAVE_SUBMITTED
            )
            return _result(
                record,
                error=_product_error(ProductErrorCode.LOCAL_STATE_CORRUPT, context),
            )
        try:
            return await self._coordinator.reconcile(record)
        except PersistenceError:
            return _local_state_failure(record)

    def _persist_definite_rejection(
        self, record: JobRecord, code: ProductErrorCode
    ) -> GenerationResult:
        rejected = transition(record, LocalLifecycleState.SUBMIT_REJECTED, now=self._now())
        rejected = replace(rejected, product_error_code=code)
        try:
            self._store.save(rejected)
        except PersistenceError:
            return _local_state_failure(record)
        return _result(rejected, error=_product_error(code, BillingContext.NO_SUBMIT))

    def _persist_submission_unknown(self, record: JobRecord) -> GenerationResult:
        unknown = transition(record, LocalLifecycleState.SUBMISSION_UNKNOWN, now=self._now())
        unknown = replace(unknown, product_error_code=ProductErrorCode.SUBMISSION_UNKNOWN)
        try:
            self._store.save(unknown)
        except PersistenceError:
            return _local_state_failure(record)
        return _result(
            unknown,
            error=_product_error(
                ProductErrorCode.SUBMISSION_UNKNOWN,
                BillingContext.MAY_HAVE_SUBMITTED,
            ),
        )


class ResumeService:
    """Observe/download an existing job with no typed access to submit capability."""

    __slots__ = ("_coordinator", "_now", "_store")

    def __init__(
        self,
        *,
        observation_client: ObservationClient,
        store: JobStore,
        downloader: DownloadService,
        sleep: Sleep = asyncio.sleep,
        now: Now = _utc_now,
        monotonic: Monotonic = time.monotonic,
        jitter: Jitter = _jitter,
    ) -> None:
        self._store = store
        self._now = now
        self._coordinator = _ObservationCoordinator(
            observation_client=observation_client,
            store=store,
            downloader=downloader,
            sleep=sleep,
            now=now,
            monotonic=monotonic,
            jitter=jitter,
        )

    async def resume(self, job_id: str) -> GenerationResult:
        """Resume a durable or user-supplied job identity using GET/content only."""

        if not job_id or job_id != job_id.strip():
            return GenerationResult(
                LocalLifecycleState.NOT_SUBMITTED,
                None,
                error=_product_error(ProductErrorCode.JOB_NOT_FOUND, BillingContext.NO_SUBMIT),
            )
        try:
            record = self._store.get_by_job_id(job_id)
            if record is None:
                record = self._claim_imported_job(job_id)
            return await self._coordinator.reconcile(record)
        except PersistenceError:
            return _local_state_failure(None)

    def _claim_imported_job(self, job_id: str) -> JobRecord:
        model = "unknown/remote-job"
        request = GenerationRequest(model=model, prompt="")
        now = self._now()
        record = JobRecord(
            schema_version=SCHEMA_VERSION,
            operation_id=f"resume-{secrets.token_hex(16)}",
            request_fingerprint=request_fingerprint_v1(request),
            model=model,
            local_state=LocalLifecycleState.ACCEPTED,
            created_at=now,
            job_id=job_id,
            accepted_at=now,
        )
        if self._store.insert(record):
            return record
        existing = self._store.get_by_job_id(job_id)
        if existing is None:
            raise PersistenceError("Unable to claim imported remote job identity")
        return existing


def _submit_rejection_code(error: OpenRouterHTTPError) -> ProductErrorCode:
    return {
        400: ProductErrorCode.UNSUPPORTED_PARAMETER,
        401: ProductErrorCode.API_KEY_INVALID,
        402: ProductErrorCode.INSUFFICIENT_CREDITS,
        403: ProductErrorCode.API_KEY_INVALID,
        404: ProductErrorCode.MODEL_UNAVAILABLE,
        422: ProductErrorCode.UNSUPPORTED_PARAMETER,
        429: ProductErrorCode.RATE_LIMITED_SUBMIT,
    }.get(error.status_code, ProductErrorCode.UNSUPPORTED_PARAMETER)


def _retryable_observation(error: BaseException) -> bool:
    if isinstance(error, TransportError):
        return True
    return isinstance(error, OpenRouterHTTPError) and (
        error.status_code in {408, 429} or 500 <= error.status_code <= 599
    )


def _poll_error_code(error: BaseException) -> ProductErrorCode:
    if isinstance(error, OpenRouterHTTPError):
        if error.status_code == 404:
            return ProductErrorCode.JOB_NOT_FOUND
        if error.status_code in {401, 403}:
            return ProductErrorCode.API_KEY_INVALID
    return ProductErrorCode.STATUS_CHECK_FAILED


def _local_state_failure(record: JobRecord | None) -> GenerationResult:
    context = (
        BillingContext.KNOWN_JOB_EXISTS
        if record is not None and record.job_id is not None
        else BillingContext.MAY_HAVE_SUBMITTED
    )
    return GenerationResult(
        record.local_state if record is not None else LocalLifecycleState.NOT_SUBMITTED,
        record.job_id if record is not None else None,
        actual_cost_usd=record.actual_cost_usd if record is not None else None,
        error=_product_error(ProductErrorCode.LOCAL_STATE_CORRUPT, context),
    )


__all__ = (
    "GenerateService",
    "POLL_CEILING_SECONDS",
    "POLL_INTERVAL_SECONDS",
    "POLL_TRANSIENT_ATTEMPTS",
    "ResumeService",
)
