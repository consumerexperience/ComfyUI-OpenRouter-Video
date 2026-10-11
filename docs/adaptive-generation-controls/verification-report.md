# Adaptive generation controls — review candidate

Status: implementation and technical verification PASS; Product Owner acceptance pending.
Branch: feature/adaptive-generation-controls. Base/main/tag: 72998e931e5e9e59a277b63c2f2b0cd4cb513164.
No merge, tag, release, paid generation or live attribution smoke was performed.

## Product decision

Confirmed independent domains allow their constrained cross-product. Missing tuple documentation
is not UNKNOWN. Explicit dependencies use complete/partial/forbidden relations. Confirmed invalid
configurations are unavailable and rejected; unknown tuples within known coupling fail closed only
for those combinations. Existing accepted Generate remains available.

## Implementation

Six product files add one generic configuration ontology, evidence ingestion, persistence through
existing CapabilityFacts, backend validation and adaptive geometry/duration projection. Duration is
an actual combo. Saved invalid values remain visible for repair; no silent substitution or serialization
rewrite occurs. New model IDs need no product branches. Reviewed coupling data uses the existing
versioned/hashed evidence manifest. Unknown schema stays unmapped and fails closed when applicable.
No separate Mode control exists in the accepted product; contextual Mode support is tested synthetically.

## Current evidence

30 exact current models audited; 674 individual geometry/duration/size values retained, zero missing.
Resolution union: 480p, 720p, 768p, 1080p, 2K, 4K. Aspect ratios: 16:9, 9:16, 1:1,
4:3, 3:4, 3:2, 2:3, 21:9, 9:21. Duration union: integer seconds 1–30, model-specific domains.
No coupled configuration relations are published in this inspected catalogue/endpoint corpus.
Provider-family constraints without an exact OpenRouter route/version mapping remain research only.
Mini 9:21 catalogue/provider-page discrepancy is recorded; canonical catalogue precedence is preserved.
See configuration-audit.json and evidence/ receipts for exact per-model domains, unknowns and source hashes.

## Verification

- Full Python suite: 368 passed, 3 skipped (existing third-party media not materialized).
- Frontend contracts: 18 passed; includes 10 existing migration/native controls tests.
- Ruff lint and format: PASS (167 files); mypy: PASS (95 files).
- Isolated sdist/wheel build: PASS, new configuration module included.
- Dependency audit: no known vulnerabilities; local unpublished package is not indexed on PyPI.
- Existing Product Contract Guard and six-file scoped semantic delta: PASS through full regression.
- Negative-space assertions preserve existing native transport, pricing, credentials, lifecycle,
  Generate/Resume authority, request wire models, packaged evidence and accepted snapshots.
- Canonical real 8189 browser: all 30 models, exact live options/methods, no catalogue overrides;
  incompatible saved intent, immediate projection, native Image/Video/Audio order and duplicate Video,
  rejected incompatible method switch, exact workflow save/readback/reload: PASS.
- Actual invalid Mini 2K Generate execution: UNSUPPORTED_PARAMETER before submit; restored workflow.
- Paid OpenRouter POSTs: 0. Positive paid generation deliberately not run.
- Coupled/method/mode relation projection is proven by generic synthetic tests, not claimed as a
  currently published real upstream coupled model. No separate Mode browser control is invented.

## Controlled verification and runtime

Dedicated worktree is exclusively owned by this run; no delegated writers. Cooperative acceptance
lease adaptive-controls-20261011 checked content before/after browser and after tests: PASS.
Full immutable receipts are outside the monitored tree in output/verification; the final receipt
is hashed in verification-provenance.json. This is technical review evidence, not Owner approval.
Canonical DEV was restarted through the governed supervisor and runs candidate source. Six modified
files were materialized after baseline comparison with backups in ../output/adaptive-controls-dev-backup.
All 40 runtime source files match the candidate; original unrelated work was preserved. Protected 8188
was not touched. Workflow browser proof and screenshot are attached locally.
