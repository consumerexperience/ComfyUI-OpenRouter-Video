# Final size semantics patch

RESULT: READY_FOR_FINAL_PRODUCT_OWNER_ACCEPTANCE
BASELINE_HEAD: c86accb3837c2916f45c536f856ff99c372777f4
BRANCH: feature/adaptive-duration-slider

SIZE_SEMANTICS: ALTERNATIVE_GEOMETRY_REPRESENTATION
SIMULTANEOUS_RESOLUTION_ASPECT_SIZE_SERIALIZATION: 0
PRESET_PIXEL_MAPPING_INVENTED: 0
LEGACY_SIZE_PRESERVED: PASS
CLASSIC_UI: PASS
NODES2_BETA_UI: PASS
UNAUTHORIZED_SEMANTIC_DELTA: 0
PAID_POST_COUNT: 0
MERGE: NONE
TAG: NONE
RELEASE: NONE

Normalized geometry keeps only resolution/aspect_ratio; Exact Size is available via the existing nonserialized Advanced button, now labeled Exact Size…. Selecting an explicit size clears the inactive normalized values and hides their controls. Clearing size returns to confirmed normalized defaults, not pixel-derived presets. Legacy explicit size wins on workflow load, as authorized by the owner. A raw ambiguous GenerationRequest is rejected by the new serialization guard and unchanged pre-submit RequestValidator. No provider-specific branches, preset mapping, new schema input, dependency, catalogue/evidence rewrite, paid submit or protected runtime access.

Verification: 385 Python tests passed, 3 existing Golden Pack missing-media skips; 73 frontend tests passed; Ruff check/format and mypy 97 source files passed; isolated wheel and sdist build passed. Semantic source comparison against explicit c86accb baseline: exactly two authorized source files (web/openrouter_video.js and src/openrouter_video/models.py), zero unauthorized differences. Duration, media topology, request policy, Generate/Resume, pricing, evidence and credentials remain covered by existing negative-space and regression tests. Accepted snapshots were not modified.

Live canonical DEV8189 was restarted through its governed supervisor and freshly verified RUNNING_HEALTHY. Screenshots cover normalized/exact in both renderers; actual native Save As and file-chooser reload cover Beta→Classic and Classic→Beta. All three saved readbacks preserve size=1280x720, resolution='', aspect_ratio='', duration=8, inference_method=FLF2V. The legacy input intentionally contains the pre-patch simultaneous saved controls and migrates to exact intent without mapping. No Run/Generate/Resume clicked.

Reproduce Python gate from feature checkout: set PYTHONPATH to its src, OPENROUTER_VIDEO_CONTRACT_BASELINE=docs/alternative-geometry/verification/baseline-contract.json, OPENROUTER_VIDEO_CONTRACT_DELTA=contracts/product/deltas/alternative-geometry-representation.contract-delta.json; run canonical repository .venv/Scripts/python.exe -m pytest -q. The baseline is a new source checkpoint derived from c86accb, not a rewrite of an accepted golden artifact.

Source: https://openrouter.ai/docs/guides/overview/multimodal/video-generation read 2026-10-11: exact dimensions and interchangeable representations. Mutual exclusion is the explicit owner-approved product policy; upstream coexistence precedence and model-specific preset/pixel mappings are not newly asserted.
