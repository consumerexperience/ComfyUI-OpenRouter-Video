# Active execution checkpoint

## Authority and baseline

- Stage: `PHASE 9 — LOCAL ZERO-COST IMPLEMENTATION IN PROGRESS`
- Branch: `phase-9/release-hardening-live-validation`
- Canonical starting main: `d0d200f54b629d1298546274ebc91b8f3004dde7`
- Phase 8: `COMPLETE`
- Paid Phase-9 submits: `0`
- Paid live execution: `NOT AUTHORIZED`
- Production ComfyUI `8188`: `NOT TOUCHED`

## Implemented checkpoint

- Typed catalogue `pricing_skus` evidence retained inside Core only.
- Conservative model-agnostic `PreflightCostEstimator` returns `AVAILABLE` or `UNAVAILABLE`.
- Sanitized capability-only UI projection and local routes added.
- New Generate nodes start at unresolved `SELECT MODEL`; the first catalogue model is not selected.
- Seed uses native integer and `ControlAfterGenerate.randomize`; `-1` is the local omission sentinel.
- A presentation-only frontend helper projects complete catalogue values, paid-intent invalidation,
  geometry mode, capability status, and prepared estimate results without model or pricing tables.
- Core `RequestValidator` remains final submit authority.
- Progress now presents `NATIVE VIDEO` before adapter-level `DONE` without changing Core lifecycle.
- Capability cache schema v4 stores typed pricing evidence; v3 cache truth is invalidated while jobs
  remain preserved.
- AppIdentity equality and absence of the public-attribution opt-out header are regression-tested.
- Synthetic five-case fixture corpus and prompts are locally frozen and hash-validated.

## Compatibility snapshot

| Host | Commit | Classification | Probe result |
| --- | --- | --- | --- |
| ComfyUI `v0.34.3` | `87465b8f1f64a27a46f16f22b13b410494dca66d` | release-blocking historical anchor | `PASS` |
| ComfyUI `v0.35.0` | `40c4fcdf513a4523e39d54a9d391908af8df8171` | intermediate probe | `PASS` |
| ComfyUI `v0.36.0` | `ee71d5c4993f29086b27fde1629a945ae48425bf` | intermediate probe | `PASS` |
| ComfyUI `v0.37.0` | `73c9bad4d21e7addbe1d13bc92eee0f1431b017d` | release-blocking frozen current target | `PASS` |

The v0.35–v0.37 probes used detached worktrees and the pinned CPU DEV interpreter. Their exact
upstream `comfy-aimdo==0.5.5` dependency was installed only into a temporary probe target; the
v0.34.3 DEV environment was not mutated.

## Current verification

- Repository pytest: `219 passed`.
- Focused fixture/frontend/adapter/pricing tests: `23 passed`.
- Local media validator: `PASS — 9 files / 5 cases`.
- Ruff lint: `PASS`.
- Ruff format: `PASS`.
- Strict mypy: `PASS — 63 source files`.
- Node syntax check for the presentation helper: `PASS`.
- Core sdist/wheel build and clean-wheel import: `PASS`.
- `pip-audit`: `PASS — no known vulnerabilities`.
- `pip check`: `PASS`.
- Comfy runtime probe: `PASS` on all four frozen matrix entries.

## Evidence semantics

- `CONTRACT_DRIFT`: `NOT CONFIRMED`.
- `COMPATIBILITY_RISK`: `PRESENT` because `comfy_api.v0_0_2` delegates into mutable latest code.
- `DOCUMENTATION_DRIFT`: being corrected in this tranche.
- `UPSTREAM EXPANSION`: record only; no Phase-9 product expansion.
- Phase-7 T2V evidence: retrospective record added; evidence-impact review remains required if the
  shared submit/serialization/lifecycle/content/native-VIDEO path changes materially.

## Next exact action

Complete the remaining Local Zero-Cost RC Gate: install/upgrade/archive/security verification,
workflow migration coverage, full repository gates, and exact local commit freeze. Do not push,
publish assets, access a production key, or execute any paid POST before the remote gate and a new
immediate Product Owner authorization.
