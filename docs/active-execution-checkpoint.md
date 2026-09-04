# Active execution checkpoint

## Canonical baseline

- Stage: `MOCK / CONTRACT TEST HARNESS — ENGINEERING COMPLETE, DELIVERY PENDING`
- Canonical starting main: `3923c2570862ae496a494787e6e17329c244d974`
- Phase-5 completion evidence: protected-main merge PR #3; expected Phase-5 merge is canonical and an
  ancestor of `origin/main`
- Branch: `phase-5a/mock-contract-harness`
- Verified implementation/docs tip before this checkpoint refresh:
  `182788484f0ac22952cd2a5ef752fcd11d480d3a`
- HEAD: this checkpoint commit becomes the branch tip; exact immutable SHA is read back after push
- Canonical main at branch creation: `origin/main == 3923c2570862ae496a494787e6e17329c244d974`
- Specification: Product / Engineering Specification v0.1.0, revision 1.1
- Architecture: Validated Architecture & Threat Model v1.1
- Accepted ADR set: ADR-001 through ADR-029; ADR-028 and ADR-029 present and `ACCEPTED`

## Contract evidence

- Evidence date: `2026-09-05`
- Sources: first-party OpenRouter Video model discovery, submit, poll, content, guide, cookbook, and
  app-attribution documentation
- Contract drift: `NONE`
- Upstream expansion: `PRESENT, OUT OF V0.1 SCOPE` — `input_references`, `provider`,
  `callback_url`, webhook behavior, returned URLs, passthrough metadata, and additional attribution
  headers are represented only as tolerant-reader/non-authority evidence where relevant
- Live API requests: `0`

## Harness components

- Strict typed `Scenario` / ordered `ScenarioStep` semantic engine
- Canonical test-only `RequestLedger` with first-class `generation_submit_count`
- `httpx.MockTransport` semantic layer around the real OpenRouterVideoClient/Core
- Existing `LocalFaultServer` extended with strict matching, completion audit, deterministic
  request-received synchronization, disconnect-after-request/headers/body, truncation, delay, and
  generation-submit counting
- Test-only loopback rewrite below the production RequestPolicy boundary
- Suite-wide non-loopback socket guard
- Fake clock/sleeper for retry, cadence, and 60-minute ceiling checks
- Explicit synthetic credential provider with no environment access

## Contract corpus

- Discovery: synthetic two-model capability matrix, additive fields, empty and malformed catalog
- Submit: accepted job, polling URL, hostile returned URL additions
- Poll: pending, in_progress, completed with/without exact `usage.cost`, failed, cancelled, expired,
  and future unknown status
- Errors: reviewed 400/401/402/404/413/429/500/502/503 evidence-classified matrix
- Malformed: invalid JSON, wrong top-level shape, missing required fields, wrong types
- Content/media: deterministic MP4/WebM and invalid/truncated/oversize behavior through existing
  production media tests plus harness fault coverage

## Fault capabilities

- Timeout/read error through semantic transport
- Request observed then response lost through real loopback socket
- Disconnect after request, headers, or partial body
- Response truncation and bounded delay
- 302/307/308 redirect isolation
- Poll and content transient status matrices
- Restart, SQLite corruption, operation concurrency, and local cancellation/re-entry

## Product fitness results

- Normal Generate: total generation POST `1`
- Poll timeout/disconnect/429/5xx recovery: total generation POST `1`
- Ambiguous submit after server observation: total generation POST `1`; state `SUBMISSION_UNKNOWN`
- Submit 429/definite rejection: total generation POST `1`; restart additional POST `0`
- Resume: generation POST `0`
- Restart after known accepted job: additional generation POST `0`
- Concurrent same `operation_id`: total generation POST `1`
- Fingerprint mismatch/corrupt durable state: additional generation POST `0`
- Download retry/exhaustion/recovery: additional generation POST `0`
- Unknown remote status: additional generation POST `0`
- Polling failure remains observation failure of the same known job

## Verification snapshot

- Baseline before changes: `102 passed`
- Feature suite before final docs: `155 passed`
- Harness self-tests: `10 passed`
- Contract/security tests: `46 passed`
- Fault/billing tests: `26 passed`
- Integration tests: `12 passed`
- Full `pytest`: `155 passed`
- Ruff lint: `PASS`
- Ruff format check: `PASS`
- Strict mypy (`src tests`): `PASS`
- sdist and wheel build: `PASS`
- Clean-wheel install/import: `PASS`
- pip-audit: `No known vulnerabilities found`; local package itself is not published on PyPI and
  is explicitly reported as unauditable by name
- CI / CodeQL: pending push and PR

## Security / real-world state

- Real OpenRouter API calls: `0`
- Paid submits: `0`
- OpenRouter credits spent: `$0`
- Production key accessed: `NO`
- External test network: `BLOCKED`; real sockets are loopback-only
- Project telemetry: `NONE`
- ComfyUI required for harness: `NO`
- Production files changed for defects: `NONE`

## Open gates

1. Push feature branch and open protected-main PR.
2. Wait for required CI matrix and CodeQL; fix only demonstrated root causes.
3. Human protected merge and canonical `origin/main` ancestry/read-back are required for `DONE`.

## Next exact action

Push `phase-5a/mock-contract-harness`, open the PR, and wait for required checks. Do not merge
autonomously and do not start the next roadmap stage.
