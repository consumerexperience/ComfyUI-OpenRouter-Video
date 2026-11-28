# OP-07 adaptive evolution implementation note

Authority: Owner directive `1d8d8e76-c6f7-40d1-b525-d1f7c37258e5`.
Implementation baseline: `721d9ebac1ee1c7cb83cd15ab9faff0262f3924e`.
This note records the authorized implementation delta; it does not amend accepted ADRs,
qualify a release, or authorize installation in TEST.

## Mechanism and control handoff

Previously normalization retained unknown field names without their values, while refresh
compared projected controls with noisy evidence clocks. Public catalogue observations now
remain bounded facts in the existing evidence profile, persisted through the existing
catalogue tables. No second model registry or provider-specific frontend branch is added.

Unknown values preserve JSON type/presence, subject to explicit privacy/size/depth markers.
Malformed known controls retain a rejection marker. Decimal values that cannot round-trip
through a JSON float retain an exact decimal representation. Existing pricing evidence
continues to parse its original decimal values. These facts never become raw request data.

The existing generic request-shape vocabulary accepts complete structured API recipes.
Current authoritative recipes take precedence over historical recipes; malformed entries,
unknown schema versions and absent methods in a supplied recipe set fail closed. Complete
reference primitives may derive existing reference recipes. Edit/extend booleans alone are
insufficient: those operations require a full operation recipe. Unknown operation primitives
remain implementation gaps. No model ID is added to production routing for Kling 4.0.

Eligibility still requires a validated request witness. The existing Core profile supplies
the method selector, controls, topology, validator and serializer. No separate UI inference
of support is allowed. Explicit false/zero remain intent; AUTO/omission stays omission.

The existing UI capabilities endpoint includes derived completeness and drift evidence.
Settings → OpenRouter Video → Capabilities displays available and unavailable models,
dispositions, explanations and sources using text nodes. It adds no serialized workflow
field, developer JSON editor, generation control or node layout change. Main node changes
are limited to refresh identity and an explicit stale-catalogue notice preserving intent.
Classic and Nodes 2.0 consume the same projection; visible browser acceptance is still pending.

## Refresh and persistence

Five-minute frontend and fifteen-minute backend freshness policies remain unchanged.
Backend discovery is serialized; frontend retains its existing single-flight/epoch guards.
Semantic revisions include complete metadata/profiles but exclude evidence clocks and
irrelevant domain/object ordering. A failed fetch retains the previous observation and
drift report, marked STALE_FALLBACK; it is not an empty/removal observation.

An additive nullable `evolution` column in `capability_catalog_meta` stores the latest
successful comparison and derived accounting. Job tables, billing claims, fingerprints,
submission, retry, OAuth, attribution and credential code are unchanged. Regression tests
compare JobStore methods outside the catalogue delta with baseline ASTs.

The report distinguishes discovered fields, executable methods, dispositions and changes.
Accounted means explained, not executable. A bounded diagnostic marker is an explained
retention limitation, never evidence of support. Structured contracts that fail normalization
remain evidence gaps, including in the product's Settings counts.

## Read-only drift check

`scripts/report_capability_completeness.py --current <snapshot.json> --previous <previous.json>
--output <report.json> [--summary <summary.md>]` reuses the production Core offline. Saved
snapshots without observation receipts are explicitly marked UNRECORDED_SNAPSHOT_TIME;
parsing time is not represented as upstream observation time.

Existing CI gains one bounded, unauthenticated public catalogue GET and a reviewable summary.
It does not follow redirects, fail product regression on upstream downtime, use credentials,
modify a package, create a PR, or publish. The full local report retains all comparison rows;
the CI summary explicitly counts changes beyond its first 100 entries.

## Live acceptance after separate authorization

1. Back up the existing TEST plugin and record its hashes; preserve user/runtime directories.
2. Build/install the reviewed exact commit only under the existing TEST update procedure;
   keep a rollback package. Do not copy environments, credentials, ACLs or mutable state.
3. In Classic and Nodes 2.0, check supported-only selection and Settings accounting for
   unavailable models. Confirm unfamiliar fields have explanations, not fake controls.
4. Check method-specific controls and native image/video/audio sockets, model switching,
   and save/reload/export. Preserve excluded legacy model IDs and incompatible linked intent.
5. Observe bounded refresh and offline recovery without reload or silent substitutions.
   Synthetic future contracts are offline tests, not production catalogue modifications.
6. Verify optional Omni task AUTO omits the field and explicit task uses the direct
   `provider.options["google-ai-studio"].task` route. Do not invent MMR2V support.
7. Stop without Queue/Generate/Resume, OAuth consent, S3 or paid calls. Roll back only the
   plugin package if acceptance fails; never restore or remove user files.

No TEST update or runtime acceptance is performed by this implementation task.
