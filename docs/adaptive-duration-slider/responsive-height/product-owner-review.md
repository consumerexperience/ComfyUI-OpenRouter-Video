# Responsive node height — visual review

PRE_ITERATION_HEAD:25451ff91905cb0d6aa972cfdf46167bafcde10a
POST_ITERATION_HEAD:01e2c33b670f80e141e9c8821488268957e3b4b3 (verified implementation; following commit contains evidence only)
BRANCH:feature/adaptive-duration-slider
LAYOUT_MODEL:TOP_FIXED / PROMPT_FLEX / BOTTOM_ANCHORED
RESULT:READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW

The existing native widget layout remains authoritative. Prompt's measured height is its accepted minimum allocation58 plus max(0,nodeHeight-nativeContentMinimum). Native computeSize measures current sockets, reference summary and fixed rows with Prompt at minimum; onResize clamps to that content minimum. Presentation refresh preserves user height. No per-model coordinates, widget Y persistence, new DOM wrapper, prompt value writes or Duration renderer changes. Default width400 and rendered Prompt minimum42 are the actually measured preceding accepted-density target.

|Measurement (graph px)|Compact|Tall|
|---|---:|---:|
|NODE_HEIGHT|400|700|
|PROMPT_HEIGHT (actual textarea)|42|342|
|BOTTOM_STACK_HEIGHT (painted rows)|approximately168|approximately168|
|BOTTOM_PADDING (painted last row to inner bottom)|approximately12|approximately12|
|PROMPT_TO_BOTTOM_STACK_GAP (painted textarea to Resolution)|approximately12|approximately12|

HEIGHT_DELTA:300
PROMPT_HEIGHT_DELTA:300
BOTTOM_STACK_HEIGHT_COMPACT:168 approximate; native allocated stack172 including trailing row gap
BOTTOM_STACK_HEIGHT_TALL:168 approximate; same allocated172
BOTTOM_PADDING_COMPACT:12 approximate
BOTTOM_PADDING_TALL:12 approximate
PROMPT_TO_BOTTOM_GAP_COMPACT:12 approximate
PROMPT_TO_BOTTOM_GAP_TALL:12 approximate

Actual DOM bounds are retained in responsive-measurements.json; normalize screen pixels by textarea width/380. Four heights400/550/700/1000 yield42/192/342/642 Prompt pixels. Side-by-side screenshot has identical zoom and top-relative structure. Painted stack/padding/gap measurements have about1px screenshot tolerance; native row20, gap4 and Duration section gap8 are unchanged in source. All extra node height belongs to Prompt.

PROMPT_FLEX:PASS
BOTTOM_ANCHOR:PASS
FIXED_INTERNAL_GRID:PASS
DYNAMIC_SOCKET_REFLOW:PASS
MIN_HEIGHT_CLAMP:PASS
SAVE_RELOAD_SIZE:PASS
DURATION_REGRESSION:PASS
RESOLUTION_REGRESSION:PASS
ASPECT_REGRESSION:PASS
SIZE_VISIBLE:PASS
CONTROL_AFTER_GENERATE_VISIBLE:PASS
CAPABILITY_DOMAINS_CHANGED:NO
WIRE_SEMANTICS_CHANGED:NO
UNAUTHORIZED_SEMANTIC_DELTA:0

Real UI resize:73 screen-pixel downward drag added73 to textarea height and moved the complete bottom stack; multiline value remained intact. Native Save As produced Responsive_Height_Review; responsive-saved.json is copied from that actual save, with node sizes400x400 and400x757.8446909667194. Loading through native file chooser reconstructed both sizes/Prompt heights and preserved text. Subsequent upward drag clamped the right node to compact height; changing Veo T2V to FLF2V exposed first/last-frame sockets, changing model to Seedance2.5 retained layout, MMR2V added reference socket/summary and grew minimum safely. Screenshot responsive-topology.png proves current top reflow. Cursor remains normal native textarea editing; no replacement or text truncation. Extreme reduction, multiline editing and continuous drag endpoints were observed; no frame-by-frame latency profiler was run.

PYTHON_TESTS:379 passed,3 skipped (existing Golden Pack unmaterialized media)
FRONTEND_TESTS:60 passed (previous56 retained plus4 grouped layout/negative-space tests)
RUFF:check+format PASS
MYPY:PASS,96 source files
BUILD:isolated wheel+sdist PASS
REAL_8189:PASS; canonical RUNNING_HEALTHY, PID44296, authenticated catalogue30 models
OPENROUTER_PAID_POST_COUNT:0 agent-issued generation POSTs

Contract delta responsive-node-height declares no allowed semantic changes. Existing deterministic exporter compares immediate current baseline25451ff with source01e2c33 using identical evidence: semantic PASS, authorized delta0, unauthorized0. Negative-space tests compare every non-layout frontend function and shared constants exactly to25451ff, including default resolver, slider interaction/serialization, domains, Native Media, pricing, Generate/Resume. Python production files were not edited. The historical Python accepted-contract gate uses its existing adaptive-generation-controls delta selector; no accepted goldens rewritten. Runtime catalogue revision refreshed naturally after controlled restart; that does not establish an immutable upstream catalogue. Capability evidence/source remain unchanged and existing all-model regressions pass.

Controlled verification lease responsive-height-20261011 checked before/after test/build and live browser operations. Logs/contracts/diff written through prepared expected hashes; final released receipt is in verification/lease-receipt.json. Browser screenshots were captured to TEMP during the intact lease and copied into this evidence-only slice after release. Prepared JSON height inputs are fixtures, not native save outputs; responsive-saved.json is the native save output. Source code was unchanged throughout the verification run.

SCREENSHOTS:
- responsive-400.png
- responsive-550.png
- responsive-700.png
- responsive-1000.png
- responsive-side-by-side.png
- responsive-save-reload.png
- responsive-method.png
- responsive-model.png
- responsive-topology.png
- responsive-clamp.png

REQUEST_STATUS:DONE
PRODUCT_STATE:READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW
ACCEPTANCE_STATE:CONTRACT_DELTA_REQUIRED (candidate layout delta provided; exact-head Owner acceptance pending)
DELIVERY_STATE:LOCAL_FEATURE_COMMITTED; no push/PR
CANONICAL_STATE:UNCHANGED
BASELINE_USED:25451ff91905cb0d6aa972cfdf46167bafcde10a
BASELINE_CHECKPOINT:compact-node-25451ff; feature checkpoint, not a newly accepted canonical-main checkpoint
SEMANTIC_DIFF:PASS
UNAUTHORIZED_DELTA:NONE
UNKNOWN_DYNAMIC_SURFACES:NONE in deterministic diff
CONTRACT_DRIFT:NONE detected in bounded checks; no external contract research required
UPSTREAM_EXPANSION:NONE
VERIFICATION:technical PASS; Owner visual acceptance pending
SIDE_EFFECTS:filesystem source/tests/delta/evidence writes; frontend copied to existing DEV junction target; controlled canonical DEV restart; local review workflow saved; local commits. Fetch:none. Push:none. PR:none. Merge:none. Tag/release:none.
OPEN_GATES:Product Owner visual acceptance; protected delivery separate
NEXT_EXACT_ACTION:Review responsive-save-reload.png and retained browser scene

Короткий лог: выполнена трёхзонная responsive layout ноды. Δвысоты300px полностью передаётся Prompt; нижний блок сохраняет сетку/отступ. Проверены четыре высоты, реальный drag/clamp, смена модели/метода и save/reload.379 Python+60 frontend, Ruff/Mypy/build PASS; семантика без изменений, paid POST0. Исходный пользовательский промт не изменён.
