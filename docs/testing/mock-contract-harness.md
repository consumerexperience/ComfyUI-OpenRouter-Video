# Mock / Contract Test Harness

## Purpose and boundary

This zero-cost harness turns the paid asynchronous OpenRouter Video lifecycle into deterministic,
local tests of the real Headless Core. It is test infrastructure, not a fake product service. It
does not prove live OpenRouter behavior, contact OpenRouter, consume ambient credentials, provide a
production base URL override, or expand frozen v0.1.

Contract tests mean that implementation assumptions match the reviewed first-party contract
snapshot in `tests/fixtures/openrouter_video`. A live-service claim requires a separately approved
live test and is intentionally absent from the default suite.

## Two layers

1. `Scenario` uses `httpx.MockTransport` for fast ordered JSON, HTTP, malformed-response, and
   deterministic transport-exception matrices.
2. `LocalFaultServer` binds only to an ephemeral loopback port for actual connection faults. The
   test-only `LoopbackRewriteTransport` maps a policy-approved canonical request below the
   production policy boundary to that listener. Production still sees no destination override.

Default tests install a socket guard that rejects non-loopback real destinations. MockTransport
does not open sockets. The harness uses `SyntheticSecretProvider`; it never reads
`OPENROUTER_API_KEY` or arbitrary process environment.

## Scenario model

`Scenario` owns a name and ordered `ScenarioStep` values. Each step declares the expected
`Operation`, method, canonical path, and one outcome: JSON, bytes, HTTP status, or an `httpx`
transport exception. Optional events provide deterministic concurrency synchronization. A wrong
method, path, operation, job ID/path, extra request, or submit body fails immediately.

Always call `scenario.assert_complete()` after the Core flow. It proves that every required step
was consumed; an accidental half-scenario cannot pass.

```python
scenario = Scenario(
    "poll-timeout-recovers",
    [
        ScenarioStep(Operation.POLL, "GET", "/api/v1/videos/job_123", exception=httpx.ReadTimeout("synthetic")),
        ScenarioStep(Operation.POLL, "GET", "/api/v1/videos/job_123", json_body={"id": "job_123", "status": "completed"}),
    ],
)
```

## RequestLedger and billing assertions

Every semantic scenario has one `RequestLedger`. It exposes total/ordered requests, counts by
method, operation, path and job ID, content count, and the first-class
`generation_submit_count`. A generation submit means exactly `POST /api/v1/videos`, not every POST.

```python
scenario.ledger.assert_generation_submit_count(1)
scenario.ledger.assert_no_additional_generation_submit(baseline)
scenario.ledger.assert_resume_submits_zero()
```

Captured request diagnostics expose structured authorization presence, attribution, path, parsed
JSON, and operation. Raw authorization is not retained. Request JSON may remain in test memory for
assertions, but is excluded from safe repr and never persisted as product state.

## Contract corpus

The manifest at `tests/fixtures/openrouter_video/MANIFEST.md` records source authority, evidence
date, classification, required/optional fields, intentionally ignored additions, and uncertainty.
Fixtures are reviewed executable snapshots, not permanent API truth.

To add or change a fixture:

1. Review current first-party OpenRouter evidence without making a live API request.
2. Classify the concept as CONFIRMED, OBSERVED, INFERRED, UNKNOWN, CONFLICT, or UNSTABLE.
3. Update the smallest fixture family and its manifest row.
4. Run contract tests to reveal parser/writer impact.
5. Request architecture/product review only if semantics actually conflict. Additive upstream
   fields do not expand v0.1.

## Common recipes

- Poll timeout: use a POLL step with `httpx.ReadTimeout`, followed by the same canonical job path.
- Malformed JSON: use `body=b"{invalid"` rather than `json_body`.
- Ambiguous submit: use `LocalFaultServer(ResponsePlan(disconnect_after_request=True))`; assert its
  request-received event and `generation_submit_count == 1`.
- Restart: finish the first `core_harness` context, then build a fresh context against the same
  temporary SQLite path and output root.
- Content failure: return 5xx/429, inject `httpx.ReadError`, or use the loopback server's
  disconnect-after-headers/mid-body controls.
- Delay/stall: use `ResponsePlan(delay_seconds=...)` only in focused socket self-tests; Core retry
  and cadence tests use `FakeTime` and do not wait.
- Concurrency: attach `entered_event` and `release_event` to the submit step so the second caller
  executes only after the first submit right is durably claimed.

## Media and persistence

Tests construct minimal deterministic MP4/WebM signature bytes. They prove the current container
validator and atomic artifact lifecycle, not video playability. Temporary directories own SQLite,
artifacts, and `.part` files. Context managers close HTTP clients/listeners, and failure paths must
leave no `.part` file.

## Known limitations

- The corpus cannot prove undocumented live behavior or provider availability.
- Synthetic model capabilities are deliberately model-agnostic and do not describe vendors.
- Socket tests use HTTP loopback below policy; they do not weaken canonical production HTTPS.
- No webhook, callback, remote cancel, provider passthrough, arbitrary reference, ComfyUI, or live
  inference behavior is provided by this harness.
