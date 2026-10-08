# Native Media Bridge — canonical verification, 2026-10-08

## 1. BASELINE

BASELINE_SHA / CURRENT_SHA: `08838ab93df2abe370d69dcc0375db3b135aa3fa`.
BRANCH: `phase-10/capability-driven-inference-methods`.
WORKTREE: product source unchanged; verification tests, manual probes and this evidence package are uncommitted. Separately introduced Product Contract Guard files are preserved.
CANONICAL_DEV: `dev/ComfyUI-DEV`, `http://127.0.0.1:8189`, ComfyUI v0.34.3. Governed restart ended RUNNING_HEALTHY, PID 36744, authenticated catalogue 30, UI contract 4, database READY. Source fingerprint `1cc828f5d813325b3ab4da99956cf90c9eaa336440ebe2293a77a5df816f7970`.

## 2. INTENDED DELTA

The existing candidate provides native VIDEO/AUDIO conversion, private S3-compatible staging, signed HTTPS references, exact-object ownership and recovery/cleanup alongside the existing direct IMAGE bridge. This execution added verification, not functionality. Canonical Python lacked the already-declared storage SDK; boto3/botocore 1.43.107 and their dependencies were installed locally, with urllib3 2.8.0. Canonical pip check passed; the governed runtime was restarted.

## 3. PROTECTED BASELINE

MODEL_CATALOG: PASS — all 30 authenticated production models remain selectable, in the existing display-name ordering.
CAPABILITY_MATRIX: PASS — selectors are compared against the actual production projection for every model; no model/capability fixture is injected.
ADAPTIVE_UI: PASS — model changes, supported methods, ten Seedance topologies, resolution, aspect ratio and duration follow that projection. Incompatible method changes retain accepted mixed links.
IMAGE: PASS — protected implementation and real tensor encoding remain unchanged.
GENERATE_RESUME: PASS — existing application/policy tests and the protected contract pass. Real paid Generate and remote Resume are outside this gate.
SAVE_RELOAD: PASS — exact production userdata save/readback, graph reload and full browser reload retain compatible state, order and duplicate connections.

## 4. IMPLEMENTATION VERIFICATION

IMAGE / VIDEO / AUDIO: PASS — real Comfy types, MP4 H.264 and PCM16 WAV conversion probes on v0.34.3 and v0.37.0. The canonical negative queue executed real Load Image/Video/Audio inputs and stopped at missing storage configuration before a PUT or Video POST.
MIXED: PASS — IMAGE, VIDEO, AUDIO, duplicate VIDEO preserve occurrence order and typed labels. Offline materialization reaches the real staging manager with only its cloud boundary substituted.
SOURCE_VIDEO: PASS — native VIDEO and legacy video-reference connections accepted.
STAGING: PASS offline — closed streaming files, byte limits, private random keys, ledger-before-PUT, capability prevalidation and partial failure coverage.
CLEANUP: PASS offline — terminal/no-submit deletion, pending retry, fingerprint mismatch protection and exact owned orphan cleanup.
RECOVERY: PASS offline — interruption, unknown submission/status, concurrent claim, crash recovery, SQLite migration and Resume without resubmission.
SECURITY: PASS offline — credential/header isolation and persistence/log/error canaries. Actual HTTP retry proof covers 3/2/1 PUT attempts and prohibition of attempt four.

## 5. AUTOMATED VERIFICATION

pytest: PASS, **314 passed** (including the concurrently added Product Contract Guard tests).
frontend: PASS, ten migration checks and JavaScript syntax checks.
Ruff: PASS, check and format; 130 Python files formatted.
mypy: PASS, 82 source files.
build: PASS, wheel and sdist.
dependency audit: PASS, no known vulnerabilities in audited dependencies.
v0.34.3 / v0.37.0: PASS, real native conversion/staging probes and existing PromptExecutor compatibility probes. These are offline transport proofs, not provider live proof.

## 6. SEMANTIC CONTRACT DIFF

AUTHORIZED_DELTA: native VIDEO/AUDIO materialization and staging lifecycle already present in 08838ab; this execution adds tests/docs and prepares verification of DELETE absence for the human-approved smoke.
UNAUTHORIZED_DELTA: **NONE** in product source. Negative-space tests protect catalogue, capability matrix, IMAGE and Generate/Resume; canonical checks use current production data. The separately introduced contract artifacts remain candidate records, not PO acceptance.

## 7. BROWSER PROOF

Actual production node on canonical DEV8189, own Edge QA session, synthetic media only:

- [Full production model picker](assets/native-media-bridge/canonical-full-model-picker.png).
- [Native mixed connections after full reload](assets/native-media-bridge/canonical-reloaded.png).
- [Configuration error from the actual node](assets/native-media-bridge/canonical-storage-error-details.png).
- [Machine-readable model/method/topology matrix](assets/native-media-bridge/canonical-browser-proof.json).
- [Synthetic native workflow](assets/native-media-bridge/canonical-workflow.json).
- [Negative execution receipt](assets/native-media-bridge/canonical-storage-error-proof.json).
- [Canonical runtime health after restart](assets/native-media-bridge/canonical-runtime-health.json).

The error screenshot predates an input-enum refresh and also shows stale loader warnings. The reloaded screenshot clears those warnings; the actual queued backend execution reached STORAGE_UPLOAD_FAILED for absent configuration. One negative Comfy queue, zero storage PUTs and zero paid Video POSTs. No fixture catalogue/capability data replaces production state. Console history includes this intentional error and transient websocket errors during restart; it is not asserted clean.

## 8. LIVE GATES

R2: **NOT AUTHORIZED**. Prepared command, run only after direct PO permission and owner-local environment configuration:

```powershell
& 'E:\_ARENAS_lab\Bizdev\AI\OPENROUTER\dev\ComfyUI-DEV\.venv\Scripts\python.exe' 'E:\_ARENAS_lab\Bizdev\AI\OPENROUTER\ComfyUI-OpenRouter-Video\tests\manual\native_media_storage_smoke.py' --execute
```

One synthetic mono PCM16 8000 Hz WAV, 800 samples, one random private staging object; maximum three actual PUT sends; presigned GET without auth headers, exact byte comparison, exact DELETE, then the same GET must return 404. No account/bucket/lifecycle creation or administration. Credentials stay owner-local; signed URLs stay in memory. The user's prefix-scoped 48-hour lifecycle is a deployment prerequisite.

OpenRouter: **NOT AUTHORIZED**. Prepared paid smoke specification:

| Field | Value |
| --- | --- |
| MODEL | bytedance/seedance-2.5 |
| METHOD | MMR2V, currently READY in production |
| MEDIA KINDS | synthetic IMAGE + VIDEO + AUDIO; duplicate VIDEO occurrence retained from canonical proof graph |
| Prepared local inputs | 1280x720 PNG; 1280x720 H.264 MP4, 24 fps, 4 seconds; mono PCM16 WAV, 48000 Hz, 4 seconds |
| Output | 4 seconds, 480p, 16:9, generate_audio=false |
| EXPECTED / MAXIMUM PAID POST COUNT | 1 / 1 |
| ESTIMATED COST IF AVAILABLE | unavailable in current node; a monetary key cap must be chosen and configured locally by PO before approval |
| RECOVERY BEHAVIOR | observe same job; Resume only, no new upload or POST; ambiguity retains owned sources |
| CLEANUP BEHAVIOR | terminal state triggers exact ledger-owned DELETE; failures remain pending; signed URL expiry never authorizes regeneration |

The tiny canonical conversion fixtures are not the proposed paid inputs. Larger synthetic inputs were generated locally in `output/playwright/prepared-live-inputs/` and decoded/read back: 96 H.264 frames and 192000 PCM16 samples, all within the local limits. They were not uploaded. Current production capabilities establish model/method/reference-kind and output-setting compatibility; provider acceptance of these exact bytes is still a live result. Before approval, the owner must choose and configure a monetary key cap locally. No automatic paid request is authorized by this report.

PAID_POST_COUNT: **0**.

## 9. RESULT

**CANONICAL_OFFLINE_PASS**. Canonical product behavior and offline transport have been verified; live storage/provider proof remains separate. Next action requires explicit PO permission for the prepared R2 smoke, per attached prompt Phase 8. No accepted tag, push, publication or merge was performed. `phase10-native-media-v1` can be created only after explicit PO ACCEPT / ПРИНИМАЮ for the reviewed checkpoint.
