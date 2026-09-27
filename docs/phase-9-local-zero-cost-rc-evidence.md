# Phase 9 Local Zero-Cost RC Evidence

## Verdict

```text
LOCAL ZERO-COST RC GATE = PASS
RC UX = FROZEN
LOCAL FIXTURE CORPUS = FROZEN
PAID GENERATION POSTS = 0
PRE-LIVE REMOTE GATE = NOT STARTED
```

This record covers the local Phase-9 tranche only. It does not claim remote CI/CodeQL,
commit-addressed public URL validation, paid eligibility, or Phase-9 completion.

## Scope and safety boundary

- Branch: `phase-9/release-hardening-live-validation`
- Canonical starting baseline: `d0d200f54b629d1298546274ebc91b8f3004dde7`
- Accepted implementation checkpoint: `8b6c97e590fe04291ddbc78b522016c6691c88bf`
- Production ComfyUI port `8188`: not touched
- OpenRouter credential: not requested, read, enumerated, injected, logged, or persisted
- Paid OpenRouter generation: zero POSTs
- Remote fixture URL checks: deliberately deferred until the exact pre-live commit is pushed

## Release-blocking Windows Portable UI evidence

The final Generate-node UI was exercised in an actual browser against isolated CPU-only ComfyUI
runtimes with separate user, output, database and port state.

| Comfy host | Exact commit | Frontend | Native-only probe | Final helper probe |
| --- | --- | --- | --- | --- |
| `v0.34.3` | `87465b8f1f64a27a46f16f22b13b410494dca66d` | `1.49.6` | insufficient | `PASS` |
| `v0.37.0` | `73c9bad4d21e7addbe1d13bc92eee0f1431b017d` | `1.52.7` | insufficient | `PASS` |

With the helper disabled, the native model widget did not project the complete dependent controls;
for example, resolution remained a free-text field after model selection. This independently
reproduced on both release-blocking hosts. The helper is therefore retained.

The retained helper is presentation-only. It consumes only sanitized local capability and prepared
estimate results. It contains no provider/model capability table, pricing formula, OpenRouter
credential handling, billing authority, request submission, or replacement for Core validation.

The final RC probe verified:

- unresolved `SELECT MODEL` initial state and no implicit first-model selection;
- reactive model switching and complete dependent option refresh;
- forward catalogue values such as `768p` and `5:4` remain reachable;
- exact duration slider/dropdown behavior;
- seed integer and `fixed`, `increment`, `decrement`, `randomize` controls;
- conservative audio and authoritative frame/reference affordances;
- geometry modes and mutual-exclusion presentation;
- valid paid intent survives model switching and save/reload;
- invalid paid intent resets only according to policy and is visibly disclosed;
- estimates refresh on model changes and become unavailable when linked reference shape resolves at execution;
- Phase-8 serialized values migrate without silent intent drift;
- reference links and generated node state survive workflow reload;
- native `VIDEO` connects to `SaveVideo` and the runtime probe executes `SaveVideo.execute` for real MP4 and WebM media;
- progress reports `NATIVE VIDEO` before `DONE` and never invents provider percentages.

The browser probe intercepted only loopback model/capability/estimate routes with synthetic,
sanitized data. It did not contact OpenRouter. Core projection equivalence, validation, pricing and
submit authority are covered by the repository test suite.

## Helper-discovered defects corrected

The real browser scenarios found and corrected three local presentation defects:

1. A remote DynamicCombo refresh could reset a valid serialized model during workflow reload.
2. Adding or removing a reference link could leave a stale numeric estimate visible.
3. A later warning could overwrite an earlier paid-intent reset disclosure.

Regression behavior now preserves valid serialized models, refreshes reference-sensitive estimates,
and accumulates distinct visible reset/warning disclosures.

## Migration and reinstall idempotence

Schema-v3 to schema-v4 migration and repeated schema-v4 initialization prove:

- job rows are preserved;
- `operation_id` and `job_id` are preserved;
- `output_relpath` and existing output bytes are preserved;
- stale capability/pricing catalogue truth is invalidated;
- no duplicate job is created;
- no generation submit side effect occurs.

## Exact five-case consistency

The live manifest, local fixtures and runbook agree on every frozen case:

```text
duration = 4 s
resolution = 480p
aspect_ratio = 16:9
generate_audio = false
```

The exact model IDs and reference modes are asserted in contract tests. Local validation covers
fixture bytes, hashes, MIME/format, dimensions/duration/codec, prompt content, intended repository
paths and absence of sensitive material. Public HTTP and commit-addressed URL validation is not a
local-gate requirement and remains open for the Pre-Live Remote Gate.

## Verification ledger

```text
pytest                                  221 passed
focused adapter/persistence/contracts    40 passed
ruff check                              PASS
ruff format --check                     PASS
mypy --strict                           PASS (63 source files)
pip-audit                               PASS (no known vulnerabilities)
sdist/wheel build                       PASS
local five-case asset validator         PASS (9 files / 5 cases)
Comfy runtime probes                    PASS (v0.34.3/v0.35.0/v0.36.0/v0.37.0)
real browser RC UX probe                PASS (v0.34.3/v0.37.0)
native VIDEO + SaveVideo                PASS
schema-v4 reinstall/migration           PASS
manifest/runbook exact consistency      PASS
```

The intermediate `v0.35.0` and `v0.36.0` probes passed and reveal no defect relevant to the two
release-blocking targets.

## Freeze rule

The commit containing this record is the local pre-live RC candidate. Its exact SHA is obtained from
branch `HEAD` after commit creation. Any post-freeze UX, fixture-byte, prompt-content, serialized
input, capability-projection schema, estimate-result schema, or exact paid-case configuration change
reopens the Local Zero-Cost RC Gate.

The next authorized stage is delivery of this exact commit to a draft PR followed by the Pre-Live
Remote Gate. Paid live execution remains unauthorized.
