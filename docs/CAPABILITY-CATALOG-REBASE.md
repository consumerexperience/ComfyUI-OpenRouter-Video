# Capability catalogue rebase

The approved P1–P8 implementation uses the current 30-model catalogue and exact
official model evidence. Runtime consumes the packaged reviewed JSON; it does
not scrape pages, download a remote manifest, or infer support from a family ID.
`capability_overlays.py` remains an import compatibility shim without model data.

Facts distinguish SUPPORTED, UNSUPPORTED, UNKNOWN and CONFLICT. Each reviewed
fact retains exact model ID, source, authority, observation time, scope and
artifact version. Structured fields take precedence, while contradictory
evidence remains visible and blocks affected recipes. Null is absence, not denial.

Ten existing wire recipes are declarative. T2V requires positive text-only
evidence and no confirmed source prerequisite. The four source-only models no
longer obtain implicit T2V. Model ordering and accepted Seedance 2.5 modes and
preference remain intact. Unknown reference limits are retained as unknown;
confirmed limits are enforced. Existing ordering and duplicate semantics remain.

Geometry combos are created with the correct Comfy renderer before callback
binding. Changing a String widget's `type` did not replace its text editor.
Resolution, aspect ratio and size now use actual combos, with compatible saved
values and their serialization positions preserved. Backend input contracts and
provider serialization remain unchanged. Duration/seed/audio use the normalized
capability projection. Unsupported saved intent remains visible and blocked.

Public numeric controls have validated numeric range descriptors. Passthrough
parameter names are evidence only: they never authorize arbitrary provider JSON.
Upscale/avatar/editing/motion/continuation evidence without established wire
remains CAPABILITY_ONLY_CONFIRMED. This is represented support, not executable
provider certification; see the scope of each AFTER row.

Pricing normalizes output seconds/tokens, image input, reference seconds,
megapixel seconds and minimum charges, including cent-to-dollar conversion.
Continuation rates do not price T2V. Output/input/minimum estimates use a
conservative bound where quantities are proven. Native VIDEO/AUDIO charges and
token/pixel quantities remain UNAVAILABLE when a safe bound is unproven. No
zero-price assumption or paid request is used to discover these semantics.

SQLite v6 adds capability evidence cache storage. The v5 upgrade preserves job
submit claims and exact-owned staging records. The canonical restart exposed a
missing v5 entry in the migration allow-list; the fix has an explicit regression
test. No generation/staging schema or credential storage was redesigned.

## Reviewed data updates

1. Retain first-party receipts and exact-ID page/endpoint evidence offline.
2. Run `scripts/build_reviewed_manifest.py`; its default destination is a candidate
   under `docs/capability-audit`, never the active package manifest.
3. Run `scripts/review_capability_manifest.py CANDIDATE BASELINE --report REPORT`.
   It validates schema/types/provenance/freshness/hash and emits the semantic diff.
4. After reviewing the concrete diff, promotion requires `--promote-reviewed`,
   `--expected-hash EXACT_REVIEWED_HASH`, and `--rollback-file UNUSED_PATH`.
   The previous manifest bytes are preserved. Report paths cannot overwrite the
   candidate, baseline or rollback. A wrong hash causes no promotion.
5. For data rollback, validate the preserved manifest with `load_manifest`, then
   restore those exact bytes through the same reviewed deployment process.

CI's full pytest suite validates the packaged registry, future structured and
reviewed-data models, conflicts, privacy, migration and the real promotion CLI.
New known-ontology model data does not require a model-specific code branch.
Unknown ontology or wire remains explicit and requires separate implementation.

## Acceptance and delivery state

`docs/capability-audit/after-semantic-comparison.json` retains every BEFORE fact
and its AFTER status/scope. `after-audit-summary.json` reports counts;
`canonical-after-product.json` is the real :8189 projection, not a fixture.
Browser proof is under `output/capability-rebase-proof`.

The candidate is running in canonical DEV :8189. The integration repository has
uncommitted candidate runtime files; prior source files are preserved under
`output/capability-rebase-dev-backup`. This is a source backup, not a database
downgrade plan: the healthy DEV database is schema v6. The implementation and
tests remain reviewable in the existing `audit/full-capability-catalog` worktree.
No commit, push, merge, tag movement or publication occurred. Protected :8188,
credentials, AppIdentity and infrastructure were not changed. Paid POST count: 0.
