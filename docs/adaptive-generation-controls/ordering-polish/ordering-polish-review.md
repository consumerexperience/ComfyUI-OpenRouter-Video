# Canonical option ordering — bounded UI polish

PRE_PATCH_HEAD: dbdd47507f2811e8dca34fcacf6fad1c575334bb
BRANCH: feature/adaptive-generation-controls
RESOLUTION_ORDER: PASS
ASPECT_RATIO_ORDER: PASS
DURATION_ORDER: PASS
EXACT_SIZE_ORDER: PASS
OPTION_SET_CHANGED: NO
WIRE_VALUES_CHANGED: NO
CAPABILITY_EVIDENCE_CHANGED: NO
SAVE_RELOAD: PASS
BASELINE_REGRESSION: PASS
REAL_8189_VISUAL: PASS
PAID_POST_COUNT: 0
PRODUCT_OWNER_VISUAL_DIRECTION: ACCEPTED
FINAL_PRODUCT_OWNER_ACCEPTANCE: PENDING
MERGE / TAG / RELEASE: NOT AUTHORIZED; NOT PERFORMED
RESULT: READY_FOR_FINAL_PRODUCT_OWNER_ACCEPTANCE

## Change and scope

Only production files comfy/projection.py and web/openrouter_video.js changed. Comparator sorts
copies of four UI domains: nominal resolution class; numeric width/height; seconds; pixel area,
then numeric ratio, width, height. Unknown labels are retained after known values in deterministic
codepoint order. No preset-to-pixel conversion exists. Model and Inference Method ordering remains
unchanged. Core capability facts and raw evidence retain upstream order; no raw evidence was rewritten.
The numeric duration sentinel remains 0 on the wire and displays AUTO / MODEL DEFAULT, including
Comfy's string/null formatter inputs. Workflow values are preserved, not converted to selected indexes.

Python route/inspection and inventory use the same canonical_options helper. Frontend uses a matching
comparator, proven against shared exact cases and every current model. New inventory tool takes a
production UI projection and writes presentation artifacts only. Prior evidence/visual captures remain
historical; the current canonical inventory and screenshots are in this folder.

## Verification

379 Python tests passed; 3 existing external-media tests skipped. 28 frontend tests passed.
Ruff lint and format PASS; mypy PASS (96 files). Isolated sdist/wheel build PASS.
Accepted regression shield, scoped Contract Delta and negative-space tests PASS. No accepted snapshot
was changed. Existing adapter assertion was updated only for explicitly approved ratio display order.
Source comparison against dbdd475 confirms all product code outside the two presentation files remains
identical; existing frontend function bodies outside enum/duration/configuration projection are unchanged.
Stored raw evidence corpus is byte-identical to dbdd475. Packaged capability evidence is byte-identical
to the checked pre-patch working-byte receipt; its normalized Git content is unchanged.

Real canonical DEV is RUNNING_HEALTHY after governed supervisor restart with only the two changed
files materialized; backups are in ../output/ordering-polish-dev-backup. 8188 and C: ComfyUI untouched.
Browser used production catalogue, 30/30 exact model projections, no fixture catalogue, zero queues.
Seedance 2.0 Resolution: AUTO, 480p, 720p, 1080p, 4K.
Hailuo 3 Max Resolution: AUTO, 480p, 768p (raw evidence was 768p, 480p).
Veo 3.1 Lite Duration: AUTO, 4, 6, 8 (raw evidence was 8, 4, 6).
Aspect Ratio narrow portrait→wide landscape; Exact Size ascending area with deterministic ties.
Save/reload preserves Veo Lite / T2V / 1080p / 9:16 / 6s regardless of reordered index.
Mini attempted 2K retains the same Generate blocked warning; no generation was submitted.

Controlled verification used an exclusive dedicated worktree and fresh checked acceptance lease
ordering-polish-final-20261011. Exact source/receipt provenance is in patch-provenance.json.
This record is technical evidence; final Product Owner acceptance remains pending.

## Canonical inventory and proof

[Full canonical unions](configuration-union.md)

[All 30 models](model-configuration-matrix.md)

[Live browser proof](browser-proof.json)

## Screenshots

### 01-seedance-resolution

![01-seedance-resolution](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/01-seedance-resolution.png)

### 02-aspect-ratio

![02-aspect-ratio](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/02-aspect-ratio.png)

### 03-exact-size

![03-exact-size](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/03-exact-size.png)

### 04-hailuo-resolution

![04-hailuo-resolution](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/04-hailuo-resolution.png)

### 05-veo-lite-duration

![05-veo-lite-duration](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/05-veo-lite-duration.png)

### invalid-2k

![invalid-2k](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/invalid-2k.png)

### save-after-reload

![save-after-reload](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/save-after-reload.png)

### save-before

![save-before](E:/_ARENAS_lab/Bizdev/AI/OPENROUTER/adaptive-generation-controls/docs/adaptive-generation-controls/ordering-polish/save-before.png)

