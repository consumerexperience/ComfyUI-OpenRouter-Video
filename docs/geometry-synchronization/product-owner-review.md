# Synchronized geometry: product owner review

PRE_HEAD: 7af8197bea0bc9f7b1fb3e1776f653ded41ab0c7
POST_HEAD: final delivery identifies the commit containing this report (avoids a self-referential commit hash).
GEOMETRY_MODEL: BIDIRECTIONAL_SYNCHRONIZED

| Check | Result |
|---|---|
| RESOLUTION_ALWAYS_VISIBLE_WHEN_SUPPORTED | PASS |
| ASPECT_ALWAYS_VISIBLE_WHEN_SUPPORTED | PASS |
| DURATION_ALWAYS_VISIBLE | PASS |
| EXACT_SIZE_ADAPTIVE | PASS |
| RESOLUTION_TO_SIZE | PARTIAL |
| ASPECT_TO_SIZE | PARTIAL |
| SIZE_TO_ASPECT | PARTIAL |
| SIZE_TO_RESOLUTION | PARTIAL |
| UNKNOWN_RELATIONS_FABRICATED | 0 |
| NORMALIZED_WIRE | PASS |
| EXACT_WIRE | PASS |
| TRIPLE_GEOMETRY_SERIALIZATION | 0 |
| LEGACY_MIGRATION | PASS |
| MODEL_SWITCH_REPROJECTION | PASS |
| CLASSIC | PASS |
| NODES2_BETA | PASS |
| PYTHON_TESTS | 391 passed; 3 existing local Golden Pack media skips |
| FRONTEND_TESTS | 80 passed |
| RUFF | PASS (check and format) |
| MYPY | PASS (100 source files) |
| BUILD | PASS (isolated wheel and sdist) |
| UNAUTHORIZED_SEMANTIC_DELTA | 0 |
| OPENROUTER_PAID_POST_COUNT | 0 |

RESULT: READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW

## Evidence limits

Current catalogue: 30 models, 168 supported sizes, 165 uniquely safe aspect projections and 3 UNKNOWN aspect projections. Zero confirmed full resolution/aspect/size tuples. SAFE_DERIVED establishes aspect only, never resolution tier. Consequently resolution/size synchronization remains PARTIAL on current models: normalized edits unset Size rather than invent it; explicit Size updates proven aspect while retaining Resolution without claiming a relation. All supported domain values are preserved in the matrix. Generic confirmed full-tuple projection is exercised by focused frontend/backend tests, not claimed as live provider evidence.

All supported primary controls remain visible. Duration stays 8 during the demonstrated geometry edits and reloads. Local hidden geometry_authority is persisted in ComfyUI workflow only. NORMALIZED sends resolution/aspect; EXACT sends size; ambiguous legacy fails before runtime acquisition. No provider POST, merge, tag, release or protected 8188 operation was performed.

## Actual DEV 8189 checks

Beta resolution and aspect edits clear unconfirmed Size. Selecting 1112x834 derives 4:3 and retains 480p. Classic edits independently verify resolution, aspect and size; selecting 720x1280 derives 9:16 and retains 720p. Native saved workflow JSON verifies exact geometry, authority, duration, seed, audio and method in both renderer directions. Normalized cross-renderer saves retain 480p/4:3/blank Size/NORMALIZED. Legacy size-only retains 1112x834, derives 4:3 and leaves unproven Resolution blank. Ambiguous legacy retains all values with visible Generate-blocked state; adapter unit test proves rejection before runtime acquisition.

Seedance Mini, 2.0 and 2.5 demonstrated in Beta, model switching also demonstrated in Classic. Switching Seedance 2.0 size 1920x1080 to 2.5 repairs to valid canonical 640x640/1:1 without stale-size warning. Seedance 2.5 resolution dropdown contains only 480p and 720p. Direct ByteDance comparison node is outside this product and contributes no capability facts.

## Screenshots and native saves

See [evidence](evidence/). Key files: Final-Beta-review.png, Classic-size-720x1280.png, Classic-legacy-size-only.png, Beta-legacy-ambiguous.png, Seedance-25-resolution-domain.png, Seedance-25-model-repair.png. Native-save readback: [verification JSON](verification/native-save-readback.json). All stage screenshots are retained.

## Validation provenance

Tests ran against feature src using PYTHONPATH and the task-specific baseline-contract.json / geometry-synchronization.contract-delta.json. The semantic guard authorizes exactly five production file deltas; focused AST regression protects all other adapter/projection logic against PRE_HEAD. Existing billing, credentials, media, duration, Generate/Resume and application logic were not redesigned. Current runtime capability domains equal the audited catalogue. Backend and frontend candidate source installed in canonical DEV match the feature files. Acceptance lease seals source and controlled evidence writes; released receipt accompanies verification.

The geometry-relations.json reviewed full-tuple store is deliberately empty: current accepted evidence does not authorize tier mappings. Model IDs reside in versioned audit evidence only; synchronization engine contains no model branches. The compatibility matrix and catalogue audit contain per-model provenance and UNKNOWN relations.
