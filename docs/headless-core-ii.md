# Headless Core II

Phase 5 implements a model-agnostic, recovery-first OpenRouter Video core without ComfyUI behavior,
live API traffic, production credentials, telemetry, or paid tests.

## Authority and capability boundaries

`GenerateService` is the only application service that receives `SubmitClient`. `ResumeService`
receives only observation and content capabilities and cannot issue a generation POST.

Recovery identity has three levels:

1. `job_id` identifies the accepted remote paid generation.
2. `operation_id` identifies one local logical Generate operation and is claimed atomically before
   network submit.
3. `request_fingerprint` checks only non-sensitive request shape and never grants authority.

Prompts and frame URLs remain transient. Their values are excluded from the fingerprint and all
SQLite tables. A caller that reuses one `operation_id` for different sensitive content has still
declared the same logical operation; the Core reconciles it and does not persist content to detect
caller misuse.

## Lifecycle

```text
NOT_SUBMITTED → VALIDATING → SUBMITTING
                               ├─→ ACCEPTED → POLLING
                               ├─→ SUBMIT_REJECTED
                               └─→ SUBMISSION_UNKNOWN

POLLING ─→ COMPLETED → DOWNLOADING → DONE
        ├→ FAILED
        ├→ CANCELLED
        ├→ EXPIRED
        ├→ OBSERVATION_INTERRUPTED
        └→ UNKNOWN_REMOTE_STATE

UNKNOWN_REMOTE_STATE → POLLING / OBSERVATION_INTERRUPTED
OBSERVATION_INTERRUPTED → POLLING or DOWNLOADING for a completed job
```

`SUBMIT_REJECTED` means an authoritative response proved that no job was accepted. It is distinct
from `SUBMISSION_UNKNOWN`, where a remote job may exist without a returned ID, and from `FAILED`,
where a known remote job reached terminal failure.

## Retry matrix

| Operation | Total attempts | Retry conditions | Submit effect |
| --- | ---: | --- | --- |
| Submit | 1 | none | exactly one application attempt |
| Discovery | 3 | transport, 408, 429, transient 5xx | none |
| Poll | 5 consecutive | transport, 408, 429, transient 5xx | none; same `job_id` |
| Download | 3 | transport, 408, 429, transient 5xx, invalid/truncated transfer | none; same `job_id` |

Backoff uses 5, 10, 20, 30, and 60 seconds capped with 20 percent timing jitter. A valid numeric
`Retry-After` up to 60 seconds is honored for retry-safe GET operations. Ordinary polling cadence
is 30 seconds with a 60-minute local observation ceiling.

## SQLite recovery

Schema v1 uses WAL, foreign keys, a 5000 ms busy timeout, and synchronous FULL. `operation_id` is
the jobs-table primary key; non-null `job_id` is unique. The advisory fingerprint is neither unique
nor indexed. A uniqueness race makes the losing Generate call reload and reconcile the winner's
record; it never retries POST.

`SUBMITTING` is committed before POST. `ACCEPTED` plus trustworthy `job_id` is committed before
polling. A crash after remote acceptance but before local job-ID persistence remains the explicit
distributed crash window; no client-side retry can eliminate it safely without upstream
idempotency/reconciliation.

Only approved recovery fields are stored. Capability cache rows contain normalized model metadata,
not raw discovery payloads. `actual_cost_usd` is stored as exact decimal TEXT and is `None` when
OpenRouter omits `usage.cost`; no local estimate is labelled actual cost.

## Media durability

Success uses only the reconstructed canonical authenticated
`GET /api/v1/videos/{job_id}/content?index=0` path. Server-returned polling and media URLs never
become destination authority.

The downloader streams to a generated `.part` file with a 1 GiB ceiling, 20-minute wall clock, and
the transport's 60-second read inactivity timeout. It validates basic MP4 or WebM container magic,
flushes and fsyncs the file, then atomically renames it. QuickTime remains disabled until a future
Comfy compatibility decision.
