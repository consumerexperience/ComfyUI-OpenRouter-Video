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

Prompts, frame URLs, and input-reference URLs remain transient. Their values are excluded from the
fingerprint and all SQLite tables. A caller that reuses one `operation_id` for different sensitive content has still
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

## Phase-8 request and capability contracts

`frame_images` and `input_references` are distinct. Frames use typed nested `image_url` objects and
first/last temporal positions. Input references use ordered typed image/video objects for guidance;
duplicates are never collapsed. The two arrays cannot be combined. Video references are transport
media only and never create Edit/Extend semantics or a separate lifecycle.

Capability enforcement is mode-scoped. Current Level A metadata authorizes per-model frame modes
through `supported_frame_images`. It exposes no direct reference kind/count/mix signal. ADR-030
therefore permits reviewed exact-ID evidence data to fill only absent fields after a fresh catalog
observation confirms that model still exists. The initial overlay enables image/video kinds, a
maximum count of 50, and mixed image/video collections only for `bytedance/seedance-2.5`.

An explicit Level-A value is never overwritten; disagreement produces `CONFLICT` and blocks the
affected intent. Unknown and near-matching models remain fail-closed. No provider, family, slug
pattern, display-name, or cross-model inference exists. Prompt is required for every Phase-8
Generate operation; prompt-optional reference generation is deferred.

New Generate calls use fingerprint v2. It includes model/options, prompt/frame/reference presence,
reference schema/count, and ordered reference kinds, but never prompt text, URLs, credentials,
media, application identity, or user/workflow identity. Existing v1 rows are not rewritten; an
operation-ID fingerprint-version mismatch fails conservatively and never restores submit authority.

## SQLite recovery

Database schema v4 and JobRecord schema v2 are independent. Supported migration paths are fresh to
v4, v1 to v2 to v3 to v4, v2 to v3 to v4, and v3 to v4. Cache migrations leave job
bytes/semantics unchanged, delete both capability-cache tables, and recreate them empty; only fresh
successful discovery can repopulate external capability and pricing truth. Unsupported versions
fail before mutation.

The store uses WAL, foreign keys, a 5000 ms busy timeout, and synchronous FULL. `operation_id` is
the jobs-table primary key; non-null `job_id` is unique. The advisory fingerprint is neither unique
nor indexed. A uniqueness race makes the losing Generate call reload and reconcile the winner's
record; it never retries POST.

`SUBMITTING` is committed before POST. `ACCEPTED` plus trustworthy `job_id` is committed before
polling. A crash after remote acceptance but before local job-ID persistence remains the explicit
distributed crash window; no client-side retry can eliminate it safely without upstream
idempotency/reconciliation.

Only approved recovery fields are stored. Capability cache rows contain normalized model metadata
and typed pricing evidence, not raw discovery payloads. `actual_cost_usd` is stored as exact decimal TEXT and is `None` when
OpenRouter omits `usage.cost`; no local estimate is labelled actual cost.

## Media durability

Success uses only the reconstructed canonical authenticated
`GET /api/v1/videos/{job_id}/content?index=0` path. Server-returned polling and media URLs never
become destination authority.

The downloader streams to a generated `.part` file with a 1 GiB ceiling, 20-minute wall clock, and
the transport's 60-second read inactivity timeout. It validates basic MP4 or WebM container magic,
flushes and fsyncs the file, then atomically renames it. QuickTime remains disabled until a future
Comfy compatibility decision.
