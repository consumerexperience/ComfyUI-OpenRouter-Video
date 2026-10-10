# Capability catalogue rebase — BEFORE / AFTER

The audit counts representation, including the expressly permitted capability-only scope.
It does not claim executable support for an unresolved wire contract.

| Finding | BEFORE | AFTER |
|---|---:|---:|
| Current model IDs | 30 | 30 |
| Models with confirmed underexposure | 26 (excluding pricing) | 0 |
| Models with confirmed overexposure | 4 | 0 |
| Manual Python overlay dependence | 1 | 0 |
| Confirmed facts represented correctly | See retained row-level audit | 256 / 256 |
| True unknown facts | 362 | 363 |
| Explicit capability conflicts | Not consistently retained | 1 |

38 confirmed facts are evidence-only. New operation/typed provider wire remains
unconfirmed; there is no arbitrary passthrough or invented provider serialization.
One nullable catalogue control declaration is now honestly unknown, rather than
a claim of missing supported functionality. The unchanged unknown facts include
limits, formats and constraints the upstream contract does not establish.

## Implementation

P1/P2: typed facts, provenance, conflicts, cache migration and reviewed exact-ID JSON.
P3/P4: declarative established-wire recipes, no implicit T2V, native topology and
actual geometry combos with saved-state preservation. Mini now exposes MMR2V,
480p and 4s. Seedance 2.5 retains its ten accepted modes and preference.
P5/P6: typed price dimensions and safe bounds/UNAVAILABLE; new operations remain
capability-only where wire is unconfirmed.
P7: offline candidate, validated semantic diff, exact-hash promotion and byte-exact
rollback; no runtime scraping or automatic remote update.
P8: all 30 models re-audited and real canonical :8189 checked without fixture data.

## Verification

342 tests passed; 3 existing unmaterialized third-party fixture tests skipped.
Repository-wide Ruff check/format passed. Mypy passed for 92 files. Wheel/sdist
build passed and includes the reviewed manifest. Dependency audit found no known
vulnerabilities; the local product cannot be audited as a PyPI distribution.
Contract Delta passed the Builder JSON Schema.

Canonical QA caught and fixed the missing v5 migration allow-list entry and the
String-widget renderer behind geometry controls. The v5 upgrade test preserves
submit ownership and staged cleanup state. Existing Native Media/Resume/one-submit
regression tests pass. Browser proof verifies the 30-model dropdown/order, Mini
mixed media and duplicate video, compatible save/reload, preserved MI2V and
Source Video topology, and source-only incompatibility disclosure.

## Evidence and limits

Full required fields: [FINAL-REPORT.json](capability-audit/FINAL-REPORT.json).
Each BEFORE/AFTER fact: [after-semantic-comparison.json](capability-audit/after-semantic-comparison.json).
Live data: [canonical-after-product.json](capability-audit/canonical-after-product.json).
Browser checklist: [browser-acceptance.json](capability-audit/browser-acceptance.json).
Implementation/update procedure: [CAPABILITY-CATALOG-REBASE.md](CAPABILITY-CATALOG-REBASE.md).

Candidate runtime files are locally deployed and uncommitted; source backups are
retained. Git delivery and the accepted tag are unchanged. Merge remains human-only.
OPENROUTER_PAID_POST_COUNT: 0. No provider generation was submitted or certified.
Native VIDEO/AUDIO pricing remains UNAVAILABLE where quantities cannot safely be bounded.
