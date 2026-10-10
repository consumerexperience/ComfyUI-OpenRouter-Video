# Full capability catalogue audit — Product Owner review

Observed: 2026-10-10T16:37:05.412933+00:00. All 30 exact official pages retrieved. Public catalogue GET returned 200 without credentials; canonical DEV model ID set matches exactly. No paid calls.

## Baseline
Accepted tag phase10-native-media-v1 remains fd460f99bddc500b9b663162587c8cfda5c61c0e. Audit branch audit/full-capability-catalog starts from canonical origin/main 9e6969415379dbaf344dabd86ade9fb4146a06f8. Owner dirty checkout and DEV 08838ab remain untouched. Product exposure is observed DEV, not a claim DEV equals canonical main.

## Conclusions
Existing inference_method_matrix already derives recipes generically from primitive facts. The systemic gap is evidence enrichment plus incomplete operation ontology; replacing the entire matcher would be unnecessary redesign.
Exactly one manual overlay exists: bytedance/seedance-2.5. New structured models can acquire existing methods without code changes; nonstructured facts cannot. All models currently get T2V READY, including source-only models.

## Counts and limits
{
  "CATALOG_MODEL_COUNT": 30,
  "MODELS_FULLY_EXPOSED": 0,
  "MODELS_UNDEREXPOSED": 26,
  "MODELS_OVEREXPOSED_OR_INCORRECT": 4,
  "UNMAPPED_UPSTREAM_CAPABILITIES": 6,
  "MANUAL_OVERLAY_DEPENDENT_MODELS": 1,
  "DYNAMIC_MODEL_DISCOVERY": "PASS",
  "DYNAMIC_CAPABILITY_DISCOVERY": "FAIL",
  "DYNAMIC_PRESET_DERIVATION": "PASS_FOR_EXISTING_ONTOLOGY",
  "NEW_MODEL_WITHOUT_CODE_CHANGE": "FAIL_FOR_NONSTRUCTURED_OR_NEW_OPERATIONS",
  "AUDIT_RESULT": "CAPABILITY_CATALOG_REBASE_REQUIRED",
  "PAID_POST_COUNT": 0,
  "counts": {
    "CORRECT": 183,
    "UNKNOWN_UPSTREAM": 362,
    "UNDEREXPOSED": 30,
    "MISSING": 35,
    "UNMAPPED_CAPABILITY": 5,
    "OVEREXPOSED": 4
  },
  "underexposed_models": [
    "alibaba/happyhorse-1.0",
    "alibaba/happyhorse-1.1",
    "alibaba/wan-2.6",
    "alibaba/wan-2.7",
    "black-forest-labs/flux-3-video",
    "black-forest-labs/flux-video-edit",
    "black-forest-labs/flux-video-upscale",
    "bytedance/seedance-1-5-pro",
    "bytedance/seedance-2.0",
    "bytedance/seedance-2.0-fast",
    "bytedance/seedance-2.0-mini",
    "bytedance/seedance-2.5",
    "google/veo-3.1",
    "google/veo-3.1-fast",
    "google/veo-3.1-lite",
    "heygen/avatar-iv",
    "heygen/heygen-video-1",
    "kwaivgi/kling-v3.0-pro",
    "kwaivgi/kling-v3.0-std",
    "kwaivgi/kling-video-o1",
    "minimax/hailuo-2.3",
    "minimax/hailuo-3",
    "minimax/hailuo-3-max",
    "runway/aleph-2",
    "runway/gen-4.5",
    "x-ai/grok-imagine-video"
  ],
  "overexposed_models": [
    "black-forest-labs/flux-video-edit",
    "black-forest-labs/flux-video-upscale",
    "runway/aleph-2",
    "heygen/avatar-iv"
  ],
  "fully_exposed_definition": "Fully proven across complete requested ontology; unknown facts prevent certification. Counts are confirmed findings, not proof other models have no gaps."
}

Counts overlap. Fully exposed=0 means no complete certification: unknowns remain, not all models are broken. Per-model missing controls and operation evidence appear in semantic-comparison.json. Pricing underexposure affects all 30 models in this catalogue: existing estimator rejects video/audio references and does not understand the current observed token/input/minimum/mode SKU vocabulary. Model/provider availability cannot be inferred from description or page retrieval.

## Evidence conflicts
Wan 2.6 exact page description advertises video/audio inputs while its featureList lists text/image only. Preserve both; do not infer exact wire mode. Empty or null API signals are UNKNOWN, not unsupported. Model modality alone does not prove ordered reference support. Reference limits, ordering, duplicates and operation-specific wire contracts remain unknown unless explicitly documented.

## Dynamic update design
Layer 1 imports structured exact-model facts and detects unknown keys. Layer 2 uses generated versioned JSON evidence from exact OpenRouter model page structured data/provider metadata and official documentation. Normal execution performs no scraping. Offline/CI ingestion produces candidate diffs; explicit review promotes supported facts. Each fact stores exact ID, value, source, observed_at, authority, scope and freshness. Layer 3 returns UNKNOWN/conflict when support remains unproven.
Precedence: explicit structured signal > exact official page > exact-model-inclusive documentation > controlled evidence. Record conflicts even when higher authority selects effective value. Null is absence, never denial. Unknown upstream operation emits UNMAPPED_UPSTREAM_CAPABILITY.
Independent registry updates are feasible only through validated schema/version/hash, trusted distribution, rollback and review. No autonomous remote executable code or silent capability promotion. Initially ship reviewed JSON with product; separate-data update design needs Product Owner/security acceptance.

## Bounded implementation packages (not executed)
1. Extend normalized capability ontology and provenance/conflicts, tolerant-reader unmapped facts and negative tests.
2. Generate reviewed exact-model evidence manifest; replace handwritten overlay data while preserving effective accepted facts.
3. Extract current matcher requirements into declarative recipes; add source-required operation prerequisites. Preserve existing order/socket contracts.
4. Add reviewed upscale/avatar/motion-transfer wire contracts and controls only when exact endpoint support is established. Provider-native claims alone are insufficient.
5. Implement typed, validated provider controls and dimension-aware pricing with fail-closed bounds; no arbitrary header/body passthrough.
6. Add reproducible ingestion/diff CI and new-model contract tests; validate all 30 models, save/reload, native sockets, source semantics and one-submit/Resume invariants.

## Protected regression surfaces
Native IMAGE/VIDEO/AUDIO normalization, private staging, signed URL transience, exact-owned deletion, ambiguity preservation, Resume no submit/upload, duplicates/order, capability-driven geometry, AppIdentity/credential isolation and protected 8188 remain unchanged. No runtime restart or canonical delivery.

## Review gate
Audit complete at evidence/coverage assessment level; unresolved upstream facts and exact new-operation wire details are explicitly UNKNOWN. Production implementation has not begun. Product Owner review required by attached task.