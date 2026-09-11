# Phase 6 ComfyUI adapter

## Public surface

The extension registers exactly two numbered V3 nodes in `OpenRouter/Video`:

- `OpenRouterVideoGenerate` creates one fresh local operation per Queue execution and delegates to
  `GenerateService` once.
- `OpenRouterVideoResume` accepts only a stripped, non-empty `job_id` and is constructed without a
  submit client.

Both return `VIDEO`, `JOB_ID`, `MODEL`, `ACTUAL_COST_USD`, and `STATUS`. `VIDEO` is the pinned
native `VideoFromFile` bridge over the already validated Core artifact. The adapter does not copy,
decode, re-encode, or invoke ffmpeg. Before returning, it rechecks that the path is an existing file
inside the Comfy output root.

Generate model choices come from `GET /openrouter-video/v1/models`. The route calls only the Core
capability catalog and returns a sorted JSON list of valid model IDs. Expected catalog failures are
`503 {"error":"model_catalog_unavailable"}`; malformed internal catalogs are
`500 {"error":"model_catalog_internal_error"}`. Route registration is process-local,
thread-safe, idempotent, lazy, and performs no network I/O.

## Compatibility matrix

| Comfy host | Adapter status |
| --- | --- |
| `v0.34.3`, commit `87465b8f1f64a27a46f16f22b13b410494dca66d`, `comfy_api.v0_0_2` | `SUPPORTED` |
| Any other release/commit | `UNSUPPORTED` |
| Missing/mismatched version or required capability surface | `FAIL CLOSED` |

Production imports only `comfy_api.v0_0_2`. There is no direct `latest` fallback and no
best-effort compatibility. All host imports and paths are isolated in `comfy/compat.py`.

The pinned executor reuses a cached result across separate Queue requests when only
`not_idempotent=True` is present. The compatibility probe therefore activates the approved
fallback: `fingerprint_inputs` returns a thread-safe, process-local monotonic integer. It is JSON
safe, never `NaN`, is not serialized as operation identity, and has no billing authority.

## Runtime and durable state

One lazily published process runtime owns a single SQLite store, Core client, and event-loop thread.
Creation and v1-to-v2 migration are serialized before publication. Schema v2 makes `model`
nullable; only the exact legacy sentinel `unknown/remote-job` migrates to `NULL`. A valid remote
model fills `NULL`, while an existing local model always wins.

Cross-loop caller cancellation sets a cooperative control event without cancelling the runtime
future. The adapter waits for the Core task to reach a durable disposition and then surfaces the
host cancellation. Shutdown is idempotent and bounded: it rejects new dispatch, interrupts and
waits for tracked work, closes the client, stops the loop, and joins the thread or reports an
explicit failure.

The durable submit rules are unchanged: the claim is written before POST, an accepted `job_id` is
written before interruption can surface, ambiguity never retries, and Resume cannot POST. Polling
or download interruption produces `OBSERVATION_INTERRUPTED`, preserves the same `job_id`, deletes
partial content, and does not claim remote cancellation.

## Privacy and verification

Workflows expose no credential, provider/base URL, arbitrary header or JSON, attribution override,
operation identity, or tracking identity. Expected node/route errors contain only sanitized product
messages. The default suite blocks external sockets; the pinned DEV gate injects a mock runtime and
uses generated temporary MP4/WebM artifacts.

`PromptExecutor` is a test-only compatibility surface in `tests/comfy_dev_probe.py`. Production
does not import `execution.py`, `PromptExecutor`, or `comfy_execution` internals.
