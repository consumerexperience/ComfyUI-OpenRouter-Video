# Active execution checkpoint

## Authority and baseline

- Stage: `PHASE 9 — LOCAL ZERO-COST RC GATE PASSED / PRE-LIVE FREEZE`
- Branch: `phase-9/release-hardening-live-validation`
- Canonical starting main: `d0d200f54b629d1298546274ebc91b8f3004dde7`
- Phase 8: `COMPLETE`
- Paid Phase-9 submits: `0`
- Paid live execution: `NOT AUTHORIZED`
- Production ComfyUI `8188`: `NOT TOUCHED`
- Local Zero-Cost RC Gate: `PASS`
- RC UX and local fixture corpus: `FROZEN`
- Push / draft PR / Pre-Live Remote Gate: `NOT STARTED`

## Implemented checkpoint

- Typed catalogue `pricing_skus` evidence retained inside Core only.
- Conservative model-agnostic `PreflightCostEstimator` returns `AVAILABLE` or `UNAVAILABLE`.
- Sanitized capability-only UI projection and local routes added.
- New Generate nodes start at unresolved `SELECT MODEL`; the first catalogue model is not selected.
- Seed uses native integer and `ControlAfterGenerate.randomize`; `-1` is the local omission sentinel.
- A presentation-only frontend helper projects complete catalogue values, paid-intent invalidation,
  geometry mode, capability status, and prepared estimate results without model or pricing tables.
- Core `RequestValidator` remains final submit authority.
- Progress presents `NATIVE VIDEO` before adapter-level `DONE` without changing Core lifecycle.
- Capability cache schema v4 stores typed pricing evidence; v3 cache truth is invalidated while jobs,
  operation/job identity and output bytes remain preserved across repeated initialization.
- AppIdentity equality and absence of the public-attribution opt-out header are regression-tested.
- Synthetic five-case fixture corpus and prompts are locally frozen and hash-validated.
- Real browser verification on both release-blocking Comfy hosts proves native V3 alone does not
  reliably refresh the complete selected-model option surface. The retained helper is the minimal
  presentation-only implementation and contains no provider/model tables, pricing formula,
  credential handling, billing authority, or submit authority.

## Compatibility snapshot

| Host | Commit | Classification | Probe result |
| --- | --- | --- | --- |
| ComfyUI `v0.34.3` | `87465b8f1f64a27a46f16f22b13b410494dca66d` | release-blocking historical anchor | `PASS` |
| ComfyUI `v0.35.0` | `40c4fcdf513a4523e39d54a9d391908af8df8171` | intermediate probe | `PASS` |
| ComfyUI `v0.36.0` | `ee71d5c4993f29086b27fde1629a945ae48425bf` | intermediate probe | `PASS` |
| ComfyUI `v0.37.0` | `73c9bad4d21e7addbe1d13bc92eee0f1431b017d` | release-blocking frozen current target | `PASS` |

The v0.35–v0.37 probes used detached worktrees and the pinned CPU DEV interpreter. Exact v0.37
frontend/template/document/kitchen/aimdo dependencies were installed only into a temporary probe
target; the v0.34.3 DEV environment was not mutated.

## Real Windows Portable UX verification

The Generate node was exercised in a real browser against isolated CPU-only Comfy runtimes, never
against production port `8188`:

| Host | Frontend | Native-V3-only result | Final RC helper result |
| --- | --- | --- | --- |
| ComfyUI `v0.34.3` | `1.49.6` | insufficient dependent-option refresh | `PASS` |
| ComfyUI `v0.37.0` | `1.52.7` | insufficient dependent-option refresh | `PASS` |

The final RC path passed unresolved initial model, reactive model switching, complete forward-value
projection (`768p`, `5:4`), exact duration controls, paid-intent preservation and visible
invalidation, geometry/seed/audio/frame/reference behavior, estimate presentation, reference-link
invalidation, truthful lifecycle ordering, workflow save/reload, Phase-8 value migration, native
`VIDEO`, and a real `SaveVideo.execute` bridge. Browser routes used synthetic sanitized loopback
capability/estimate responses; Core equivalence and pre-submit authority remain independently covered
by repository tests.

## Current verification

- Repository pytest: `221 passed`.
- Focused adapter/persistence/fixture/frontend tests: `40 passed`.
- Local media validator: `PASS — 9 files / 5 cases`.
- Ruff lint: `PASS`.
- Ruff format: `PASS`.
- Strict mypy: `PASS — 63 source files`.
- Node syntax check for the presentation helper: `PASS`.
- Core sdist/wheel build and clean-wheel import: `PASS`.
- `pip-audit`: `PASS — no known vulnerabilities`.
- `pip check`: `PASS`.
- Comfy runtime probe, including native `VIDEO` and `SaveVideo`: `PASS` on all matrix entries.
- Real Windows Portable browser UX/save-reload verification: `PASS` on both release-blocking hosts.
- Schema-v4 migration/reinstall idempotence: `PASS` with job, identity and output preservation.
- Five-case manifest/runbook exact-configuration consistency: `PASS`.
- Local fixture validation: `PASS`; remote commit-addressed URL validation is correctly deferred.

## Evidence semantics

- `CONTRACT_DRIFT`: `NOT CONFIRMED`.
- `COMPATIBILITY_RISK`: `PRESENT` because `comfy_api.v0_0_2` delegates into mutable latest code.
- `DOCUMENTATION_DRIFT`: corrected for the current checkpoint.
- `UPSTREAM EXPANSION`: recorded only; no Phase-9 product expansion.
- Phase-7 T2V evidence: retrospective record exists; evidence-impact review remains required if the
  shared submit/serialization/lifecycle/content/native-VIDEO path changes materially.

## Freeze boundary and next exact action

The commit containing this checkpoint is the exact local pre-live RC candidate. Read its identity
from branch `HEAD` after commit creation. Any subsequent UX, fixture-byte, prompt-content, serialized
input, projection-schema, estimate-schema, or exact live-case configuration change reopens Gate A.

Next: push this exact commit, open the draft PR, validate commit-addressed public fixture/prompt URLs,
and run the Pre-Live Remote Gate. Those actions have not been performed in this tranche. Do not
access a production key or execute any paid POST without later immediate Product Owner approval.
