# Active execution checkpoint

## Authority and baseline

- Stage: `PHASE 9 — CORRECTED UX READY FOR KEYED WINDOWS PORTABLE ACCEPTANCE`
- Branch: `phase-9/release-hardening-live-validation`
- Canonical starting main: `d0d200f54b629d1298546274ebc91b8f3004dde7`
- Rejected UX checkpoint: `432f0bcd0f1df0bc4cffadfef11cfb638cd22b51`
- Phase 8: `COMPLETE`
- Paid Phase-9 submits: `0`
- Paid live execution: `NOT AUTHORIZED`
- Production ComfyUI `8188`: `NOT TOUCHED`
- Human-keyed ComfyUI `8189`: `NOT RESTARTED BY CODEX`
- Local Zero-Cost RC Gate: `REOPENED — REAL KEYED ACCEPTANCE PENDING`
- RC UX: `NOT FROZEN`
- Local fixture corpus: `UNCHANGED`
- PR `#16`: `DRAFT — CORRECTED COMMIT NOT PUSHED`
- Pre-Live Remote Gate: `NOT STARTED FOR CORRECTED COMMIT`

## Corrective UX implementation

- The model combo keeps the canonical model ID as its serialized value and renders the catalogue
  display name. Duplicate display names are disambiguated with the model ID.
- The sanitized UI projection now carries effective reference kinds, effective maximum reference
  count, mixed image/video support and the existing normalized mode evidence.
- New workflows connect ordered Public Image URL and Public Video URL nodes directly to Generate.
  The Phase-8 collection node remains available only as an advanced compatibility input.
- Direct reference sockets grow to the selected model's effective limit, preserve heterogeneous
  order and duplicates, and never discard already-linked references after a model-limit change.
- A limit reduction is disclosed visibly and blocks normal submit intent until the user explicitly
  resolves it; the helper never silently removes or substitutes paid intent.
- First/Last Frame inputs and reference nodes now state the proven public-HTTPS URL transport.
  Native local IMAGE/VIDEO transport is not claimed without an authoritative Video API contract.
- Capability status, estimate result and reference status are visibly rendered. The frontend still
  contains no capability table, price formula, credential handling, billing authority or submit
  authority.
- Core `RequestValidator` remains the final paid-submit authority.

## Why the presentation helper remains necessary

Native V3 supplies the node schema, DynamicCombo, Autogrow, VIDEO output, SaveVideo bridge and
ControlAfterGenerate primitives. Across the two release-blocking hosts, native schema alone does not
provide the complete selected-model dependent presentation required here: readable catalogue names,
dependent enum refresh, exact paid-intent invalidation, reference-limit topology and prepared estimate
display. The retained helper is limited to those presentation duties and consumes only sanitized local
projection/estimate results.

## Deterministic verification completed

| Host | Exact Comfy commit | Classification | Corrected runtime probe | Corrected browser interaction |
| --- | --- | --- | --- | --- |
| `v0.34.3` | `87465b8f1f64a27a46f16f22b13b410494dca66d` | release-blocking anchor | `PASS` | `PASS — isolated keyless 8190` |
| `v0.37.0` | `73c9bad4d21e7addbe1d13bc92eee0f1431b017d` | release-blocking current | `PASS` | `PASS — isolated keyless 8191` |

The browser interaction used real mouse input against ComfyUI rather than assigning widget values:

- opened the model combo and selected readable `Phase 9 Model A` / `Phase 9 Model B` labels;
- opened a typed reference socket by dragging it to empty canvas;
- selected Public Image URL and Public Video URL nodes from the actual Comfy node chooser;
- observed direct sockets grow from one to three and stop at the effective limit of three;
- switched to a model with an effective reference maximum of zero;
- observed all three links preserved with an explicit `3/0` invalidation;
- serialized/reloaded the workflow and observed the canonical model ID plus all three ordered links
  preserved.

The loopback browser routes used sanitized synthetic capability/estimate payloads. They prove host and
presentation behavior only; they are not the required real authenticated catalogue acceptance.

Current repository verification:

```text
pytest                                      222 passed
focused adapter/frontend contract tests      22 passed
ruff check                                  PASS
ruff format --check                         PASS after the recorded formatting fix
mypy --strict src                           PASS
node --check web/openrouter_video.js         PASS
git diff --check                            PASS
Comfy v0.34.3 corrected runtime probe        PASS
Comfy v0.37.0 corrected runtime probe        PASS
```

Previously completed and unaffected evidence remains valid for schema-v4 migration/reinstall
idempotence, five-case manifest/runbook consistency, local fixture validation, packaging, dependency
audit, AppIdentity and same-job recovery. The corrective tranche does not change persistence,
fixtures, exact paid configuration, AppIdentity, billing or recovery semantics.

## Open local gate item

The next required check is an actual Windows Portable acceptance on human-restarted keyed `8189`
without route mocks for `/openrouter-video/v1/models` or
`/openrouter-video/v1/ui-capabilities`. It must confirm the real catalogue display names, real
selected-model dependent options and the same interaction/save-reload behavior.

Codex must not restart that key-bearing process, inspect its environment or access its credential.
The Product Owner performs the restart after receiving the corrected local commit identity.

Until that acceptance passes:

```text
LOCAL ZERO-COST RC GATE = OPEN
RC UX = NOT FROZEN
PUSH OF CORRECTED COMMIT = NOT AUTHORIZED BY THIS CHECKPOINT
PAID EXECUTION = NOT AUTHORIZED
```
