# Active execution checkpoint

## Previous phase

- Phase: `PHASE 4 — DONE`
- Canonical merge: `9faa1ed4ffbc5b548aca8e5241afc9ed60e9196e`
- Delivery: protected `main`, merge commit, PR #2, required CI matrix and CodeQL green
- Read-back: local `main == origin/main`; every Phase-4 commit is an ancestor of canonical main

## Current task

Phase 5 — Headless Core II

## State

- Status: `ENGINEERING COMPLETE — DELIVERY PENDING PROTECTED MERGE`
- Baseline branch: `main`
- Baseline commit: `9faa1ed4ffbc5b548aca8e5241afc9ed60e9196e`
- Working branch: `phase-5/headless-core-ii`
- Specification: Product / Engineering Specification v0.1.0, revision 1.1
- Architecture: Validated Architecture & Threat Model v1.1
- Accepted ADRs: ADR-001 through ADR-027
- Additive Phase-5 decisions: ADR-028 and ADR-029 accepted
- Evidence gate: `COMPLETE — 2026-09-04`
- Contract drift: `NONE`
- Upstream expansion: `PRESENT, OUT OF V0.1 SCOPE`
- Live OpenRouter traffic: `PROHIBITED`
- Paid submits: `PROHIBITED`
- Production credential access: `PROHIBITED`

## Verification at feature HEAD

- `pytest`: `102 passed`
- `ruff check`: `PASS`
- `ruff format --check`: `PASS`
- strict `mypy`: `PASS`
- sdist and wheel build: `PASS`
- clean-venv wheel install/import: `PASS`
- `pip-audit`: `No known vulnerabilities found`
- architecture/security scan: `PASS`
- Real OpenRouter API calls: `0`
- Paid submits: `0`
- OpenRouter credits spent: `$0`
- Production key accessed: `NO`
- Project telemetry: `NONE`
- Comfy imports in Core: `NONE`

## First decisions

- ADR-028 fixes local recovery authority, versioned privacy-preserving request fingerprints, and
  SQLite concurrency enforcement.
- ADR-029 fixes the durable disposition of authoritative definite submit rejection as local
  terminal state `SUBMIT_REJECTED`.

## Phase-5 scope

- Typed contracts and exact OpenRouter Video client methods.
- Capability discovery, normalization, validation, fresh cache, and bounded last-known-good data.
- Local lifecycle state machine with unknown-state preservation.
- SQLite recovery state and atomic `operation_id` submit-right claim.
- Billing-safe Generate and submit-incapable Resume services.
- Bounded polling, observation recovery, canonical content streaming, and durable media download.
- Zero-cost tests for billing, privacy, lifecycle, recovery, concurrency, and boundary fitness.

## Deferred by design

- ComfyUI product behavior and VIDEO conversion.
- Live OpenRouter calls, production credentials, live attribution smoke, or paid generation.
- Full scenario DSL, general fake OpenRouter platform, and full Contract Harness.
- Release, tag, and autonomous protected merge.

## Next exact action

Push `phase-5/headless-core-ii`, open its protected-main PR, and read required CI and CodeQL.
Do not merge autonomously; Phase 5 becomes DONE only after human protected merge and canonical
`main` read-back.
