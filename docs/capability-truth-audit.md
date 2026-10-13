# Capability-truth audit — current observation

**PARTIAL. RC capability-truth gate: FAIL. Runtime reconciliation has not been implemented.**

This report inventories all 30 current catalogue models and all 300 model × ontology-method rows. It does **not** certify 100% of their Provider → OpenRouter intersections. The evidence artifact is an audit observation in the existing product evidence architecture; it is deliberately not loaded as an executable capability overlay. Existing accepted snapshots, live evidence, catalogue logic and global ontology are unchanged.

## Source binding and scope

- Repair branch: `repair/capability-truth`; starting/current product head `ab34768cdfdf977bafe217ad09d2ddd11b7f998e`.
- Accepted baseline: annotated `adaptive-duration-slider-v1`, peeled `f9c19c669735d08fc12b5460eaf2198cdde2d714`; remote main verified at that SHA during this audit.
- Current catalogue: local canonical DEV projection and authenticated normalized SQLite catalogue; public OpenRouter catalogue has the same exact model set. All 30 current OpenRouter model pages returned HTTP 200 and published structured descriptions and endpoint parameter metadata.
- Primary native documentation is supplemental evidence, not automatic OpenRouter authority. Actual provider routes matter: Wan 2.6/2.7 and Kling may be served by AtlasCloud; nominal family documentation alone does not establish their served tuple.
- No generation request, paid POST, credential inspection, PROD 8188 access, PR #28 mutation, merge, tag or release was performed.

## Complete model inventory

The unproven column means the current public method cannot yet be justified from the reviewed shape intersection. It does not mean the native model lacks that conceptual capability.

| Model | Current public methods | Public method requiring removal/review | Remaining intersection certification |
|---|---|---|---|
| `alibaba/happyhorse-1.0` | T2V, I2V, IR2V, MI2V | IR2V, MI2V | Method-specific domains/couplings pending |
| `alibaba/happyhorse-1.1` | T2V, I2V, IR2V, MI2V | IR2V, MI2V | Method-specific domains/couplings pending |
| `alibaba/wan-2.6` | T2V, I2V | NONE | Method-specific domains/couplings pending |
| `alibaba/wan-2.7` | T2V, I2V, FLF2V, IR2V, MI2V | IR2V, MI2V | Method-specific domains/couplings pending |
| `alibaba/wan-3.0` | T2V, I2V | NONE | Method-specific domains/couplings pending |
| `alibaba/wan-3.0-prime` | T2V, I2V | NONE | Method-specific domains/couplings pending |
| `black-forest-labs/flux-3-video` | T2V, I2V, FLF2V | NONE | Method-specific domains/couplings pending |
| `black-forest-labs/flux-video-edit` | NONE | NONE | Method-specific domains/couplings pending |
| `black-forest-labs/flux-video-upscale` | NONE | NONE | Method-specific domains/couplings pending |
| `bytedance/seedance-1-5-pro` | I2V, FLF2V | NONE | Method-specific domains/couplings pending |
| `bytedance/seedance-2.0` | T2V, I2V, FLF2V, IR2V, MI2V, VR2V, AR2V, MMR2V | AR2V | Method-specific domains/couplings pending |
| `bytedance/seedance-2.0-fast` | T2V, I2V, FLF2V, IR2V, MI2V, VR2V, MMR2V | NONE | Method-specific domains/couplings pending |
| `bytedance/seedance-2.0-mini` | T2V, I2V, FLF2V, IR2V, MI2V, VR2V, MMR2V | NONE | Method-specific domains/couplings pending |
| `bytedance/seedance-2.5` | T2V, I2V, FLF2V, IR2V, MI2V, VR2V, AR2V, MMR2V, V2V_EDIT, V2V_EXTEND | AR2V, V2V_EDIT, V2V_EXTEND | Method-specific domains/couplings pending |
| `google/veo-3.1` | T2V, I2V, FLF2V | NONE | Method-specific domains/couplings pending |
| `google/veo-3.1-fast` | T2V, I2V, FLF2V | NONE | Method-specific domains/couplings pending |
| `google/veo-3.1-lite` | T2V, I2V, FLF2V | T2V, I2V, FLF2V | Method-specific domains/couplings pending |
| `heygen/avatar-iv` | NONE | NONE | Method-specific domains/couplings pending |
| `heygen/heygen-video-1` | T2V, I2V, IR2V, MI2V, VR2V, AR2V, MMR2V | T2V, I2V, IR2V, MI2V, VR2V, AR2V, MMR2V | Method-specific domains/couplings pending |
| `kwaivgi/kling-v3.0-pro` | T2V, I2V, FLF2V | T2V, I2V, FLF2V | Method-specific domains/couplings pending |
| `kwaivgi/kling-v3.0-std` | T2V, I2V, FLF2V | T2V, I2V, FLF2V | Method-specific domains/couplings pending |
| `kwaivgi/kling-video-o1` | T2V, I2V, FLF2V | T2V, I2V, FLF2V | Method-specific domains/couplings pending |
| `minimax/hailuo-2.3` | T2V, I2V | NONE | Method-specific domains/couplings pending |
| `minimax/hailuo-3` | I2V, FLF2V | NONE | Method-specific domains/couplings pending |
| `minimax/hailuo-3-max` | T2V, I2V, FLF2V | NONE | Method-specific domains/couplings pending |
| `runway/aleph-2` | NONE | NONE | Method-specific domains/couplings pending |
| `runway/gen-4.5` | T2V, I2V | NONE | Method-specific domains/couplings pending |
| `x-ai/grok-imagine-video` | T2V, I2V, IR2V, MI2V | NONE | Method-specific domains/couplings pending |
| `x-ai/grok-imagine-video-1.5` | T2V, I2V | NONE | Method-specific domains/couplings pending |
| `x-ai/grok-imagine-video-1.5-lite` | T2V, I2V | NONE | Method-specific domains/couplings pending |

## Systemic projection defects

1. Method availability is derived from independent primitive flags. AUDIO reference support is used as evidence for AUDIO-only AR2V; mixed support is not a list of accepted kind sets. EDIT/EXTEND is not justified merely by a VIDEO reference and a feature flag.
2. `configureInferenceMethod` appends the saved invalid method to the current selector instead of preserving it only as recoverable internal intent and selecting a supported fallback.
3. Reference sockets use a universal IMAGE/VIDEO/AUDIO union regardless of IR2V, MI2V, VR2V or AR2V semantics. Method-conditioned counts, per-kind limits and media-presence conditions are not projected.
4. Most parameters are flat model domains. A supported resolution and a supported duration do not prove their combination; frame/reference topology may impose another domain.
5. Hiding is not omission. `GenerationRequest.to_payload` emits `generate_audio` unconditionally. Adapter execution parses hidden seed/media before any method-scoped sanitization, and invalid explicit methods can fall back to legacy inference. Hidden state may therefore affect validation, estimator or staging before submit.

These findings are source-observed, not paid experiments. The artifact records positive read-only defect checks; they are failing readiness properties, not passing product tests.

## Specific evidence requiring reconciliation

- **AR_AUDIO_ONLY** — Native Seedance 2.0 requires IMAGE or VIDEO with AUDIO; AUDIO primitive does not establish AUDIO-only shape. Affected: bytedance/seedance-2.0.

- **AR_UNPROVEN_INTEGRATION** — Native/audio modality or marketing description is insufficient for an OpenRouter standalone AUDIO-only request. Affected: bytedance/seedance-2.5, heygen/heygen-video-1.

- **V2V_UNPROVEN_WIRE** — Generic VIDEO reference is not proof of edit/extend source role or previous-job request shape. Affected: bytedance/seedance-2.5.

- **HAILUO_DURATION_COUPLING** — Native 1080P supports duration 6 only; 10-second 1080p/exact 1920x1080 combinations must not be projected. Affected: minimax/hailuo-2.3.

- **GROK_REFERENCE_DOMAIN** — Native reference domain is 720p/max 10 seconds, while exact accepted MI2V 480p/1s/2 images succeeded. Preserve that live tuple; do not infer the full 480p x 1..15 domain. Affected: x-ai/grok-imagine-video.

- **GROK_I2V_ASPECT** — Native source image determines aspect; arbitrary independent OpenRouter aspect override is not proven. Affected: x-ai/grok-imagine-video, x-ai/grok-imagine-video-1.5, x-ai/grok-imagine-video-1.5-lite.

- **SEEDANCE_REFERENCE_COUNTS** — Current projection lacks method/per-kind limits and valid kind-set constraints. 2.0 has image<=9/video<=3/audio<=3; 2.5 native limits differ. Aggregate integration limit requires separate evidence. Affected: bytedance/seedance-2.0, bytedance/seedance-2.0-fast, bytedance/seedance-2.0-mini, bytedance/seedance-2.5.

- **SEEDANCE_RESOLUTION_SHAPES** — Native 4K/1080p availability differs by variant and reference shape; flat global domains cannot certify all combinations. Affected: bytedance/seedance-2.0, bytedance/seedance-2.0-fast, bytedance/seedance-2.0-mini, bytedance/seedance-2.5.

- **VEO_DURATION_RESOLUTION_SHAPES** — Resolution, frames, references and duration need exact served-variant native+OpenRouter coupling. Global 4/6/8 and tier arrays are not tuples. Affected: google/veo-3.1, google/veo-3.1-fast, google/veo-3.1-lite.

- **KLING_PROVIDER_SIZE_CONFLICT** — Actual AtlasCloud Pro route documents 1080P; OpenRouter endpoint metadata exposes 720-sized outputs. Unproven wrapper/downscale is not exact-size proof. Affected: kwaivgi/kling-v3.0-pro.

- **HEYGEN_REFERENCE_WIRE** — Exact native served model and OpenRouter handling of each reference shape remain unverified; image/video/audio modalities do not prove combinations. Affected: heygen/heygen-video-1.

- **SAVED_METHOD_REEXPOSURE** — configureInferenceMethod appends stale selected value outside supported list. Affected: ALL.

- **UNIVERSAL_REFERENCE_SOCKET** — configureReferenceTopology resets reference type to universal media union. Affected: REFERENCE_METHODS.

- **HIDDEN_AUDIO_WIRE** — GenerationRequest.to_payload always emits generate_audio, even when control is hidden/unavailable. Affected: TOGGLE_UNKNOWN_OR_FALSE.

- **HIDDEN_STATE_PREVALIDATION** — Adapter parses seed and media before method-scoped omission. Invalid explicit method falls back to legacy inference. Affected: ALL.

## Accepted live proof remains exact-scope

Preserve existing T2V retrospective, native IMAGE→VIDEO→AUDIO MMR2V receipt, current I2V and MI2V successful jobs, billing shields, and native staging evidence. Preserve the exact FLF2V and VR2V geometry conflicts. Mini/Fast AUDIO-only rejections do not invalidate AUDIO transport or supported MMR shapes. Neither a success nor a rejection establishes all durations, sizes, kind combinations or served provider variants.

The prior campaign did not capture raw outbound bodies or complete upstream error payloads. Fingerprint reconciliation establishes recorded semantic inputs, not a retroactive raw request/error transcript. The native Seedance prohibition explains the class of AUDIO-only failure; it does not identify the exact rejected field in the missing upstream response.

## Required repair design

Extend the existing reviewed evidence manifest and normalized capability profile with method-scoped request-shape constraints. Keep the global ontology and provider-independent recipes. The public method/domain/topology view must be derived once, then shared by UI, raw adapter sanitization, validation and estimator.

The reviewed profile must represent four states, native/OpenRouter provenance and served-version scope; fixed role topology; ordered kind-set combinations; total/per-kind bounds; required IMAGE-or-VIDEO alongside AUDIO where applicable; finite control domains; method-conditioned geometry/duration relations; explicit SERIALIZED/OMITTED fields. Missing relation remains UNKNOWN. Exact accepted live tuples remain separately versioned observations.

For transitions: preserve compatible intent, reproject it, then use deterministic supported fallback. Invalid saved methods/options must not be added back to selector arrays. Recoverable incompatible linked/value intent must remain internal; hidden state is sanitized **before** media encoding, staging, seed parsing, validation and cost estimate. Serialization must omit unsupported booleans without changing the accepted explicit supported-false wire representation. No provider IDs or model branches belong in frontend code.

A complete contract delta must authorize only those projection/omission paths, retain accepted visual tokens/functions, billing/lifecycle/transport/pricing formula protections, and preserve the previous repair. Source pins and guards must be updated only for the exact reviewed new patch; accepted goldens must not be refreshed to bypass failures.

## Readiness and unperformed gates

The current product source is unchanged. Therefore no defect in this report is claimed repaired. Full Python/frontend/Builder reruns, new shape/omission negative tests, semantic delta export, current Classic/Nodes 2.0 model/method transitions, save/reload and screenshots for the reconciled candidate are **NOT VERIFIED**. Historical repair passes and screenshots prove `ab34768` only; they do not prove this requested reconciliation.

Machine artifact: `contracts/product/evidence/capability-truth-audit-v1.json`. Claims count model-method-domain/topology rows, not hypothetical Cartesian tuple counts. UNKNOWN control rows deliberately mean missing method-conditioned certification, even when the global primitive domain is present.

**NEXT_GATE: BLOCKED_CAPABILITY_PROJECTION_RECONCILIATION_NOT_IMPLEMENTED.**

## Reusable primary source pointers

Native input-shape prohibition and variant differences: [BytePlus API](https://docs.byteplus.com/en/docs/Byteplus_LAS/video_gen_enhanced). Duration/tier combinations: [MiniMax I2V](https://platform.minimax.io/docs/api-reference/video-generation-i2v.md), [MiniMax T2V](https://platform.minimax.io/docs/api-reference/video-generation-t2v.md). Grok method distinctions: [xAI video generation](https://docs.x.ai/developers/model-capabilities/video/generation). Actual Kling Pro route: [AtlasCloud technical schema](https://www.atlascloud.ai/models/kwaivgi/kling-v3.0-pro/text-to-video/llms.txt). These sources do not grant broader OpenRouter capabilities.

## Final observed gate fields

Claims are model × method × domain/topology rows; individual selector values and hypothetical Cartesian products are not separately counted. SUPPORTED method rows establish method shape only, never every associated parameter tuple. Failures below refer to the requested readiness gate; unperformed browser checks are not alleged renderer defects.

```text
CAPABILITY_AUDIT: PARTIAL
CURRENT_MODEL_COUNT: 30
MODEL_COVERAGE: 100% current-model inventory; complete intersection certification NOT ESTABLISHED
PUBLIC_CAPABILITY_CLAIMS_AUDITED: 1132
SUPPORTED_CLAIMS: 69
UNSUPPORTED_CLAIMS: 1
UNKNOWN_CLAIMS: 1002
CONFLICT_CLAIMS: 60
METHOD_PROJECTION: FAIL — requested reconciliation unimplemented
MEDIA_PROJECTION: FAIL — requested reconciliation unimplemented
GEOMETRY_PROJECTION: FAIL — requested reconciliation unimplemented
DURATION_PROJECTION: FAIL — requested reconciliation unimplemented
GENERATE_AUDIO_PROJECTION: FAIL — requested reconciliation unimplemented
SEED_PROJECTION: FAIL — requested reconciliation unimplemented
AR2V_INVALID_PROJECTION_REMOVED: NO
OTHER_INVALID_PROJECTIONS_FOUND: 7 defect/contradiction classes, excluding AR2V; 15 findings total include unresolved evidence categories, not 15 confirmed invalid values
OTHER_INVALID_PROJECTIONS_REMOVED: 0
CARTESIAN_INFERENCE: REMAINS
PROVIDER_SPECIFIC_FRONTEND_HARDCODE: 0 new branches added; exhaustive existing-branch certification NOT VERIFIED
HIDDEN_INVALID_SERIALIZATION: FAIL
MODEL_SWITCH_REPROJECTION: FAIL — stale invalid method may be re-added
METHOD_SWITCH_REPROJECTION: FAIL — no shared method-scoped domains
SAVE_RELOAD_REPROJECTION: FAIL — repaired persistence not verified
CLASSIC_PARITY: FAIL — requested repair not verified
NODES2_PARITY: FAIL — requested repair not verified
VISUAL_REGRESSION: NONE introduced; src/web unchanged; fresh candidate screenshots NOT VERIFIED
PYTHON_TESTS: 395 passed, 3 optional media-fixture skips (unchanged ab34768)
FRONTEND_TESTS: 85 passed (unchanged ab34768)
BUILDER_TESTS: 75 passed, 62 subtests passed
UNAUTHORIZED_SEMANTIC_DELTA: 0
PAID_POST_COUNT: 0
PRODUCT_CODE_CHANGED: NO
REPAIR_HEAD: ab34768cdfdf977bafe217ad09d2ddd11b7f998e
CAPABILITY_AUDIT_REPORT: E:\_ARENAS_lab\Bizdev\AI\OPENROUTER\rc-live-repair\docs\capability-truth-audit.md
CAPABILITY_EVIDENCE_ARTIFACT: E:\_ARENAS_lab\Bizdev\AI\OPENROUTER\rc-live-repair\contracts\product\evidence\capability-truth-audit-v1.json
RC_CAPABILITY_TRUTH_GATE: FAIL
NEXT_GATE: BLOCKED_CAPABILITY_PROJECTION_RECONCILIATION_NOT_IMPLEMENTED
```

Local Control After Generate, Advanced ordering, outputs, accepted UI tokens, responsive Prompt, serializer protocol carriers, lifecycle, billing, media encoding/staging, attribution and credential code were not edited. Existing native/live evidence and PR #28 remain untouched. No push/merge/tag/publish.
