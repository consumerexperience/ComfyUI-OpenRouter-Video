# OP-07 automatic input constraint reconciliation

Implementation baseline: b3a95e9c87ab973cfcaf80702b675b30d7c77f1b. Owner authority: abcc0172-40d4-424d-80d7-d83361b6d244.

The existing Core now composes method constraints and current OpenRouter transport constraints. Independent per-kind minima/maxima do not imply a total maximum. An absent confirmed total is represented by null, not a guessed constant. Required/exclusive kinds and method-scoped limits remain independent. Fixed source video consumes transport capacity only when present; previous_job_id consumes none.

Current structured evidence supersedes unscoped stale bounds only for the corresponding field. Unrelated, malformed or conflicting evidence cannot reactivate an uncertain method. Native provider documentation remains supplementary evidence and cannot establish OpenRouter executability.

Media duration, bytes and geometry are checked before encoding/submit. VIDEO and AUDIO reference duration budgets are evaluated independently from role-keyed contracts, including actual source video where applicable. Bounded external URLs without verifiable metadata fail closed. Existing network, paid POST, attribution, credential and staging safeguards remain unchanged.

The frontend projects these constraints in both renderer paths. Existing connected sockets stay on canvas even when incompatible; validation reports the mismatch instead of disconnecting links. Legacy parked workflow intent can still be restored. Unknown constraints do not show a fabricated maximum reached. Refresh recalculates controls without installing code.

## Seedance finding and unresolved contract

The baseline registry had MI2V image/total=3 and MMR2V image/video/audio/total=3 for Seedance 2.0, Fast and Mini. No field-level OpenRouter evidence establishes those totals. The old composer intersected live limits with historical max; the frontend treated that max as total capacity.

The historical numbers and sources remain in the registry, annotated STALE_EVIDENCE. Their effective bounds are unknown. The six MI2V/MMR2V configurations are quarantined until a sufficient OpenRouter contract arrives. This is a deliberate safety consequence, not recovered mixed-mode execution. Native 9/3/3 must not be claimed as confirmed OpenRouter transport support. Seedance 2.5 remains separately supported by its reviewed exact-model profile; lack of structured upstream counts is still disclosed.

## Regression matrix

| Owner case | Automated proof |
|---|---|
| 1 independent IMAGE/VIDEO maxima | test_reference_constraint_composition: independent_limits_do_not_invent_a_total |
| 2 separate total | confirmed_total_is_independent_of_per_kind_capacity |
| 3 unknown total | independent_limits_do_not_invent_a_total; frontend independent per-kind caps |
| 4 mixed media | same generic 9 IMAGE + 3 VIDEO + 3 AUDIO fixture and wire assertions |
| 5 audio-only restriction | required_kinds_minima_and_mutual_exclusion |
| 6 method scope | method_scopes_do_not_share_reference_caps; real transport validator |
| 7 duration budgets | test_reference_media_constraints: independent role-keyed combined budgets |
| 8 stale profile | current_per_kind_expansion_and_contraction_supersede_stale_profile |
| 9 expansion | same parameterized test (4, 9 images) |
| 10 contraction | same test (2 images), transport source reservation |
| 11 conflict | contradictory_confirmed_bounds; unresolved_and_malformed_fields_never_reactivate |
| 12 new structured model | new_model_with_only_live_per_kind_contract_needs_no_registry |
| 13 autogrow | test_public_projection_frontend: independent per-kind socket test |
| 14 links survive | model/method switch preserves incompatible canvas links; unknown topology test |
| 15 save/reload/export | existing frontend migration/persistence suites and legacy parked workflow restoration |
| 16 Classic/Nodes 2.0 | existing renderer contract suites; live acceptance still pending |
| 17 NO_SUBMIT | real RequestValidator and quarantine failure tests; no network/paid probes |
| 18 authorized delta | Product Contract Guard plus protected AST/function regression shields |

Completeness drift reports flag CAPABILITY_UNDEREXPOSURE_DEFECT for unjustified effective narrowing. Missing upstream contract, stale evidence and implementation gaps remain distinct; ACCOUNTED is never execution proof. CI emits a bounded actionable report. Public live fetch failures warn without replacing offline contract regression checks.

No TEST installation or live UI acceptance is performed by this change. A new immutable package must bind the resulting exact commit and pass separate authorized installation preflight. Earlier 38 unresolved contracts remain open and unchanged; this task does not claim OP-07 PASS or Full Feature Parity.
