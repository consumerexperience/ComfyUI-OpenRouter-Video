# Duration Slider: bounded delta

Baseline: adaptive-generation-controls-v1 -> 8ec71ba94575f8b02105a0cd0e5feba7d7083b87 (PR #29 merged; remote annotated tag read back).
Branch: feature/adaptive-duration-slider. No parent rewrite, merge, tag, release.

## Accepted path
Reviewed capability-evidence.json + live catalogue -> ModelCapabilities.supported_durations (finite integer tuple or unknown) -> GenerationConfiguration relations -> frontend configurationOptions -> configureDuration -> named/positional workflow value -> nodes._duration (0 => None) -> existing request builder (duration omitted or actual seconds).

All current lists, including contiguous 1..30, remain DISCRETE. No upstream research or evidence edits. Existing incompatible saved values remain unchanged; existing projection/validation owns incompatibility and Generate blocking. Method, model, geometry and references already call configuration reprojection. New widget consumes its output only.

## UI contract
Native Comfy DOM widget in the original Duration serialization slot. Horizontal HTML range indexes finite allowed values; underlying widget.value and serializeValue are seconds. Header shows current seconds; separate AUTO button means model default/omitted field, never 0s. Small domains label all stops; dense domains label minimum/middle/maximum. Equal index spacing prioritizes exact constraints over proportional geometry. Arrow keys traverse allowed values; Home/End select boundaries. Unknown domains disable range and disclose unverified domain. Saved incompatible intent is displayed until explicitly repaired.

Future structured UI classifier accepts only explicit STEPPED_RANGE or CONTINUOUS_RANGE contracts. Current ontology/backend is integer-based and publishes finite lists only. Continuous fixtures prove the presentation adapter, not end-to-end fractional upstream support; future ontology/wire precision contract must be accepted before activation.

Production change budget: web/openrouter_video.js only, createGeometryCombos duration branch + configureDuration + Duration-only helper functions. Protected Python/evidence files unchanged, all unrelated frontend functions source-equivalent. No runtime dependencies.
