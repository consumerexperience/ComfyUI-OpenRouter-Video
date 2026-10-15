# RC live failure reconciliation, repair and revalidation

Baseline: adaptive-duration-slider-v1 / f9c19c669735d08fc12b5460eaf2198cdde2d714. Branch: repair/rc-live-conformance. Canonical main/tag remain unchanged. Candidate is not merged, tagged or released. Exact final repair SHA is bound in workspace delivery-receipts/rc-live-repair-result.json, outside this commit.

**RC_LIVE_VALIDATION_GATE: FAIL. NEXT_GATE: BLOCKED_AR2V_UPSTREAM_PARAMETER_REJECTION.**

## Root causes

- FLF2V_GEOMETRY: UPSTREAM_CONTRACT_CONFLICT + LOCAL_CAPABILITY_OVEREXPOSURE. Persisted structural fingerprint proves EXACT 480x480, normalized fields omitted; unchanged serializer conforms to OpenAPI. Catalogue advertises 480x480; actual MP4 864x496. Raw historical outbound capture absent; provider internal normalization cause unknown.
- VR2V_GEOMETRY: UPSTREAM_CONTRACT_CONFLICT + LOCAL_CAPABILITY_OVEREXPOSURE. Same structural proof; requested EXACT 480x480, observed MP4 640x640. No local serialization conflict found; advertised exact conformance contradicted. Provider internal cause unknown.
- AR2V: CAPABILITY_OVEREXPOSURE + UPSTREAM_CONTRACT_CONFLICT. Primitive AUDIO/mixed reference documentation was projected as standalone AR2V READY. Schema-compliant audio_url object under input_references is definitively rejected on Mini EXACT and Fast NORMALIZED. Exact rejected parameter is UNKNOWN: complete safe error body was never retained. This does not prove AUDIO unsupported and does not invalidate accepted MMR2V.

Evidence strength: all three historical structural fingerprints match independent reconstruction, including size and geometry omissions. The canonical serializer/client/request policy are unchanged and schema-compliant. Historical raw outbound bytes and full upstream error body were not captured; this limitation is not retroactively filled by guessed snapshots. Error status maps to definite parameter rejection, but precise field and provider internal cause remain unknown.

First-party sources: [OpenRouter OpenAPI](https://openrouter.ai/openapi.json), [Seedance Mini](https://openrouter.ai/bytedance/seedance-2.0-mini), [Seedance 1.5 Pro](https://openrouter.ai/bytedance/seedance-1-5-pro). Observed output metadata and job IDs remain in original campaign receipt.

## Minimal repair

Reviewed capability-evidence data retains CONFLICT observations; generic existing configuration constraints reject the exact two tested size/duration/method/audio combinations. Local geometry_authority is passed to that existing constraint context by Core and UI, never serialized upstream. Method-specific conformance conflicts block AR2V on Mini and now Fast without denying AUDIO modality, VR2V or MMR2V. No provider-specific frontend branch, serializer rewrite, UI layout change, migration, paid retry, postprocessing or pixel fabrication.

Historical no-change shields now admit only pinned exact reviewed patch bytes and still compare all remaining source/functions to historical baselines. Accepted snapshots were not overwritten. Fresh full-source semantic diff and node-UX diff both report unauthorized delta zero. Cooperatively isolated repair worktree verification used acquire/check/release leases; earlier released lease was archived intact before the final pass.

## Matrix A: generation surfaces

| Surface | Status | Evidence |
|---|---|---|
| T2V | LIVE_VERIFIED | Existing accepted retrospective |
| I2V | LIVE_VERIFIED | Completed canonical campaign job |
| FLF2V | LIVE_VERIFIED | First+Last coexistence, completed job, native VIDEO; geometry separate |
| MI2V | LIVE_VERIFIED | Two ordered images, completed job, native VIDEO |
| VR2V | LIVE_VERIFIED | Standalone native VIDEO reference, completed job; geometry separate |
| AR2V | FAIL | Mini and one authorized Fast submit definitely rejected |
| MMR2V | LIVE_VERIFIED | Existing accepted IMAGE+VIDEO+AUDIO mixed proof |

## Matrix B: cross-cutting contracts

| Contract | Status | Scope |
|---|---|---|
| Exact Size | CONSTRAINED | Known false 480x480/4s/audio=false combinations excluded for exact observed methods; untested combinations not newly certified |
| Normalized geometry | PASS | Authority/wire/regression proof retained; rejected Fast normalized request gives no new output conformance proof |
| Native IMAGE | PASS | Existing completed native input/output campaign |
| Native VIDEO | PASS | VR2V input, staging, completed native VIDEO |
| Native AUDIO | PASS | Accepted MMR2V transport plus rejected standalone staging/cleanup; standalone generation still FAIL |
| Generate billing safety | PASS | One new submit, definite rejection, no retry |
| Resume billing safety | PASS | Existing non-paid fault proof; no Resume or paid submit here |

## Non-paid verification

Python: 395 passed, three pre-existing optional Golden Pack materialization skips. Frontend: 85 passed. Builder: 75 passed, 62 subtests. Ruff check/format and mypy PASS (101 source files). Full source and node UX semantic diff PASS; unauthorized delta 0. Classic/Nodes 2.0 real DEV and save/reload exercised without Queue. Known incompatible Exact intent reprojects to an allowed duration; rows stay visible. Mini/Fast AR2V no longer appears in method options, while MMR2V remains. This is engineering/browser proof, not a new Owner visual acceptance.

## Minimal paid revalidation

Exactly one new AR2V POST through native LoadAudio -> OpenRouterVideoGenerate -> SaveVideo path: Seedance2Fast, 4s, NORMALIZED 480p / 1:1, size omitted, existing 2s PCM16 mono 24k WAV, generate_audio=false. Current projection was READY before POST; documented schema explicitly honors AUDIO for Seedance generation 2+. Mini known conflicting was not retried. Minimum reference output component $0.09072 was selection reference only; complete billing not certified. No pricing research reopened.

Result: definite UNSUPPORTED_PARAMETER, no job ID, no output, MIME/dimensions/duration/hash unavailable. New usage.cost unavailable; do not report zero as certified actual spend. Original observed campaign sum remains $0.2746728 plus any unavailable rejected costs. Owner-attested dedicated key lifetime cap $2.00 unchanged.

New structural fingerprint: `v3:8065eed2ec0bede76ae1f613ffcf43ef8db003567faf2e3dde6c394e6bc716db`; normalized geometry and single AUDIO role match durable state. AUDIO wire: `input_references: [{"type":"audio_url","audio_url":{"url":"<staged HTTPS URL>"}}]`. Signed URL and key omitted.

Local staging ledger has zero remaining objects after definite rejection. Ledger-before-PUT is verified in unchanged staging code; direct PUT timing and independent bucket deletion were not instrumented. No paid FLF2V/VR2V repetition was needed because their generation paths were already proven and the repair makes no replacement exact-pixel claim.

## Remaining defect and protected state

Standalone AR2V remains unresolved: schema-compliant input is rejected on two models. The exact rejected parameter is unknown because the accepted error boundary discards response bodies. Further diagnosis needs a safe redacted diagnostic evidence path or authoritative OpenRouter clarification; it does not authorize another POST. Do not silently reinterpret this as AUDIO unsupported.

Product code changed only within approved RC delta. DEV 8189 holds the final candidate; original affected runtime bytes were backed up in output/rc-repair-20261013/canonical-runtime-before. PROD 8188, C-drive ComfyUI and PR #28 untouched. No merge/tag/release.

Evidence: workspace delivery-receipts/rc-live-repair-result.json, delivery-receipts/rc-live-repair-revalidation.json and output/rc-repair-20261013/. Historical campaign remains intact.
