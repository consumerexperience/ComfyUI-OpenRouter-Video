# Nodes 2.0 Beta compatibility — Product Owner review

RESULT: READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW

PRE_TASK_HEAD: e89b513da94ec74640ecff15f227e675bbc75533
POST_IMPLEMENTATION_HEAD: f493f0019bf2edfd79cb965989306b45bff742fa
BRANCH: feature/adaptive-duration-slider
ACCEPTED_PARENT_CHECKPOINT: 8ec71ba94575f8b02105a0cd0e5feba7d7083b87 (untouched)
SOURCE_SHA256: 930b1f5692f1eb7585ba938175b7779f7b334b226ead3f675cd4b70d780c6022

Implemented one presentation-only delta in web/openrouter_video.js. Visibility now retains and mutates the original widget options object, preserving native Beta metadata. Exact Size is deliberately primary. Legacy URL backing values remain serializable but absent from both forms. Estimate is plain state, with Classic canvas header and Beta normal-flow header span. Beta native grid gives spare height only to Prompt. Public widget label setter invalidates cached native display metadata after asynchronous projection; it leaves labels and values unchanged. Seed -1 remains the existing supported backend sentinel, including native input blur.

## Verification

| Gate | Result |
| --- | --- |
| Python | 379 passed, 3 skipped (existing official Golden Pack media MATERIALIZATION_REQUIRED) |
| Frontend | 68 passed, 0 failed |
| Ruff / Ruff format | PASS / PASS |
| Mypy | PASS, 96 source files |
| Isolated wheel / sdist build | PASS |
| Dependency audit | No known vulnerabilities in audited installed dependencies; local openrouter-video package skipped because absent from PyPI |
| Frozen semantic contract comparison | PASS, 0 unauthorized delta |
| Exact negative-space comparison | Existing semantic frontend functions and all Python source match immediate e89b513 baseline |
| Canonical DEV | 8189 only; frontend 1.49.6; 30 live catalogue models; code fingerprint current |
| Paid Video POST | 0; no Generate/Run/Resume submitted |

Real Classic and Beta loads covered T2V, I2V, FLF2V, IR2V, MI2V, MMR2V, VR2V, AR2V, V2V_EDIT and V2V_EXTEND. Appropriate first/last frame, image, video, audio and source video sockets were observed. Interactive Beta FLF2V→T2V then Seedance 2.5→Veo 3.1 reprojected sockets/domains; entering Duration 7 snapped to supported 6, and header estimate became $1.20. Seed -1 survived input focus/blur. References summary is read-only and visible only when meaningful.

Four actual native UI Save As / file-chooser reload paths preserved all named generation values, input reference ordering, media paths and repeated video occurrences: Classic→Classic, Beta→Beta, Classic→Beta, Beta→Classic. Numeric slot indices may shift when native Comfy restores unlinked optional schema inputs. Comparison therefore resolves each saved link through the saved input name, and verifies both occurrence order and actual endpoint; it does not pretend raw link arrays are identical. Evidence: evidence/cross-mode-readback.json and six actual saved media workflows.

## Size policy and limits

SIZE_SEMANTICS: UNKNOWN. All 30 live models are enumerated in size-semantics-matrix.md. Exact Size retains the confirmed model catalogue domain and blank/omit choice; it is not guessed from Resolution or Aspect Ratio. No automatic conversion, silent clearing or wire precedence change. The official guide describes interchangeable representations, but neither the current catalogue nor documentation establishes per-model simultaneous-field precedence or a coupling relation. Existing behavior remains conservative; this is not provider-level confirmation of independent override.

Beta's native price_badge is a Comfy credits facility. There is no documented arbitrary BYOK USD header slot in the inspected frontend. The small scoped header span is therefore a guarded fallback tied to observed 1.49.6 DOM selectors; no core Vue replacement, absolute positioning, extra runtime or dependency. A future frontend revision needs this renderer smoke repeated. No paid provider runtime proof is claimed.

## Layout measurements

| Metric | Classic | Beta |
| --- | --- | --- |
| Width | 400 | 400 |
| Standard row | 20 | 24 |
| Row gap | 4 | 4 |
| Duration row | native 24 allocation | native 29 |
| Prompt minimum in observed compact node | 42 | native textarea 60 |
| Prompt in loaded height-700 fixture | 342 | 303 |
| Prompt padding | 4px 6px | 20px 6px 4px (native floating label) |

The native Beta content minimum is taller than Classic; no false claim of pixel-identical minimum. Secondary rows stay fixed at 24 when tall, and native bottom-right drag grows only Prompt. Both nodes are shown beside the native ByteDance reference at identical zoom in each screenshot. Classic original OFF setting was restored at completion.

## Required result fields

PRE_ITERATION_HEAD: e89b513da94ec74640ecff15f227e675bbc75533
POST_ITERATION_HEAD: f493f0019bf2edfd79cb965989306b45bff742fa (verified implementation; following evidence-only commit is reported in delivery message)
CLASSIC_UI: PASS
NODES2_BETA_UI: PASS
CLASSIC_VISUAL_REGRESSION: NO
PYTHON_TESTS: 379 PASS / 3 existing materialization skips
FRONTEND_TESTS: 68 PASS
RUFF: PASS
RUFF_FORMAT: PASS
MYPY: PASS
BUILD: PASS
DEPENDENCY_AUDIT: PASS for installed third-party dependencies; local package not on PyPI skipped

UNKNOWN_BLANK_FIELD_IDENTIFIED: REFERENCES frontend read-only text widget, plus empty STATE; native Beta ignored item.hidden and used stale options metadata.
UNKNOWN_BLANK_FIELD_REMOVED: PASS
COST_HEADER_CLASSIC: PASS
COST_HEADER_BETA: PASS
BODY_COST_DUPLICATE: 0
FIRST_FRAME_SOCKET_CLASSIC: PASS
FIRST_FRAME_SOCKET_BETA: PASS
LAST_FRAME_SOCKET_CLASSIC: PASS
LAST_FRAME_SOCKET_BETA: PASS
DUPLICATE_MEDIA_FORM_FIELDS: 0
SIZE_FINAL_UI_POLICY: optional primary Exact Size combo; only confirmed domain, blank omission, no inferred coupling.
RESOLUTION_SIZE_FALSE_MAPPING: 0
ADVANCED_INPUT_CLASSIFICATION: PASS
DURATION_CLASSIC: PASS
DURATION_BETA: PASS
RESPONSIVE_PROMPT_CLASSIC: PASS
RESPONSIVE_PROMPT_BETA: PASS
NODE_DENSITY_CLASSIC: PASS
NODE_DENSITY_BETA: PASS (native density, measurements above)
CROSS_MODE_SAVE_RELOAD: PASS (semantic values and named link endpoints)
MODEL_METHOD_REPROJECTION: PASS
CAPABILITY_DOMAINS_CHANGED: NO
WIRE_SEMANTICS_CHANGED: NO
UNAUTHORIZED_SEMANTIC_DELTA: 0
REAL_8189_CLASSIC: PASS
REAL_8189_BETA: PASS
OPENROUTER_PAID_POST_COUNT: 0

## Artifacts and ownership

Screenshots: screenshots/01-classic-openrouter-compact.png through screenshots/15-cost-header-beta.png, plus all ten method screenshots per renderer, connected media and native resize evidence. All hashes and implementation head are in evidence-manifest.json. Audit documents were written before the initial implementation. Tests and contract exports were bound under the final cooperative acceptance lease to f493f0019bf2edfd79cb965989306b45bff742fa; browser checks ran during that lease. Evidence files were copied from captured temporary bytes after lease release; the following documentation commit adds no production source change.

Two earlier verification runs were superseded before acceptance when native seed presentation needed correction. One abandoned run was explicitly marked ownership LOST after its source snapshot changed and recovered only after the verifier stopped; none of its output is used as the final acceptance candidate. The final lease completed and released successfully; receipt is verification/lease-receipt.json.

No merge, push, tag, release or new immutable checkpoint. Product Owner visual acceptance remains pending. Beta DOM compatibility and unknown per-model Size precedence are explicit limits.

## Short tracker log

Вход: Nodes 2.0 Beta dual-renderer hardening от e89b513. Исправлены скрытые backing fields, header-only estimate, deliberate Advanced/Exact Size, Beta Prompt flex и metadata cache; сохранён seed -1. Проверены Classic/Beta, 10 методов, native IMAGE/VIDEO/AUDIO и четыре save/reload маршрута. 379 Python + 68 frontend PASS; lint/type/build/dependency audit PASS с указанными skips. Semantic delta 0, paid POST 0. Итог: READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW; Size relation UNKNOWN, merge/release не выполнялись. Исходный промт не изменён.
