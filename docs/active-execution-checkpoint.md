# Active execution checkpoint

## Canonical baseline

- Stage: `PHASE 6 COMFYUI ADAPTER — ENGINEERING COMPLETE, DELIVERY PENDING`
- Branch: `phase-6/comfyui-adapter`
- Canonical starting main: `e67d8759eeeaa1bd6c189ea78c974c29dea9022d`
- Baseline suite before Phase 6: `155 passed`
- Specification: Product / Engineering Specification v0.1.0, revision 1.1
- Architecture: Validated Architecture & Threat Model v1.1
- Accepted ADR set: ADR-001 through ADR-029
- Contract drift: `NONE`
- Upstream expansion: `NONE USED`

## Implemented adapter

- Exactly two numbered V3 nodes: `OpenRouterVideoGenerate` and `OpenRouterVideoResume`
- Category: `OpenRouter/Video`
- Outputs: `VIDEO`, `JOB_ID`, `MODEL`, `ACTUAL_COST_USD`, `STATUS`
- Dynamic local model route: `GET /openrouter-video/v1/models`
- Native artifact bridge: pinned `VideoFromFile`, no copy/decode/re-encode/ffmpeg
- Resume owns no submit client and cannot POST
- One lazy process runtime with one SQLite store, one managed client, and one event-loop thread
- Cooperative caller cancellation waits for durable runtime disposition
- Bounded idempotent shutdown closes client/loop/thread with no pending tracked tasks

## Compatibility decision

- Supported host: ComfyUI `v0.34.3`
- Supported commit: `87465b8f1f64a27a46f16f22b13b410494dca66d`
- Supported API: `comfy_api.v0_0_2`, semantic version `0.0.2`
- Other hosts: `UNSUPPORTED`; mismatch: `FAIL CLOSED`
- Production imports no `comfy_api.latest`, `execution.py`, `PromptExecutor`, or
  `comfy_execution` internals
- Pinned `PromptExecutor` proved that `not_idempotent=True` alone reused the cached output across
  Queue requests. The approved fallback is active: a thread-safe process-local monotonic integer
  from `fingerprint_inputs`, JSON-safe and unrelated to business `operation_id`.

## Durable state and billing safety

- SQLite schema v2 makes `model` nullable
- Transactional v1-to-v2 table rebuild changes only exact `unknown/remote-job` to `NULL`
- All other non-empty legacy model values remain byte-for-byte unchanged
- Existing local model wins; only a valid non-empty remote model fills durable `NULL`
- Runtime creation/migration is serialized before publication
- Every Generate execution creates one fresh opaque operation ID immediately before one Core call
- Claim remains durable before POST; accepted `job_id` remains durable before interruption surfaces
- Ambiguous submit remains `SUBMISSION_UNKNOWN` and never resubmits
- Poll/download interrupt remains `OBSERVATION_INTERRUPTED` with the same `job_id`
- Partial download is deleted; no remote cancellation is claimed

## Verification snapshot

- Full pytest: `183 passed`
- Ruff lint: `PASS`
- Ruff format check: `PASS`
- Strict mypy: `PASS — 55 source files`
- sdist and wheel build: `PASS`
- Clean-wheel install/import: `PASS`
- pip-audit: `No known vulnerabilities found`; the unpublished local package name is unauditable
- Security/privacy/billing focused suite: `42 passed`
- Pinned Comfy CPU quick-test: `PASS`; both custom nodes discovered without import failure
- Pinned test-only PromptExecutor: `PASS`; two Queue requests execute Generate twice and Resume twice
- Pinned real V3 schemas: `PASS`; independent outputs and exact public surface
- Pinned native video consumer: `PASS`; generated MP4 and WebM pass
  `VideoFromFile -> GetVideoComponents`
- Deleted artifact boundary: `PASS — sanitized failure`

## Security and real-world state

- Live OpenRouter requests: `0`
- Paid generation submits: `0`
- Credits spent: `$0`
- Production credential access: `NO`
- COMFY PROD touched: `NO`
- External test network: blocked except reviewed loopback harness; adapter tests use MockTransport
- Project telemetry: `NONE`
- Canonical application identity: unchanged

## Delivery state

- Local engineering: `COMPLETE`
- Verified implementation commit: `a08edceacb151bbd0e3f34bb4869f3bc20020bb7`
- Feature branch: `PUSHED`
- PR: `#6 — https://github.com/consumerexperience/ComfyUI-OpenRouter-Video/pull/6`
- Required CI and CodeQL on implementation commit: `7/7 PASS`
- This checkpoint-only update requires the same checks on the final PR head after push
- Protected merge: `HUMAN ONLY — NOT AUTHORIZED`
- Canonical-main ancestry for Phase 6: `PENDING PROTECTED MERGE`

## Next exact action

Push this checkpoint-only update, wait for required CI and CodeQL on the final PR head, and stop
before protected merge.
