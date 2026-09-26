# ADR-030 — Evidence-Backed Capability Overlay

- Status: `ACCEPTED`
- Date: `2026-09-26`
- Classification: `D2 — ARCHITECTURE / RUNTIME POLICY`
- Authority: explicit Product Owner decision

## Context

The read-only `GET /api/v1/videos/models` catalog confirms current model membership and exposes
frame, geometry, audio, seed, and related fields, but the 2026-09-26 sanitized observation exposes
no direct reference-kind, reference-count, heterogeneous-collection, or prompt-optional signal.

Current first-party OpenRouter model documentation explicitly identifies
`bytedance/seedance-2.5`, states that `input_references` accepts image/video/audio assets, reports up
to 50 reference assets, and includes a request example containing both `video_url` and `image_url`.
That is authoritative model-specific evidence, but it is not a machine-readable runtime field.

## Decision

Core may use a reviewed evidence-backed capability overlay only to fill fields absent from Level A.
Resolution order is:

1. machine-readable Level A catalog data;
2. an approved exact-ID evidence overlay;
3. generic Level B1 protocol behavior;
4. fail closed.

Overlay entries are immutable capability data keyed by an exact canonical model ID. Provider,
family, prefix, regex, display-name, example, and cross-model inference are forbidden. Core remains
generic: it resolves catalog data and overlay data into one effective capability record, then runs
the same request validator for every model.

An overlay never overrides an explicit Level-A field. Equal Level-A data remains Level-A data. Any
explicit disagreement is `CONFLICT` and blocks the affected reference intent before submit pending
evidence review.

The initial approved entry is:

```text
model_id: bytedance/seedance-2.5
reference_kinds: IMAGE, VIDEO
max_reference_count: 50
mixed_image_video_references: true
evidence_level: B2
first_party_source: https://openrouter.ai/blog/insights/seedance-2-5-review/
evidence_checked_at: 2026-09-26
```

Audio references remain outside the product. Frame inputs and reference inputs remain mutually
exclusive. A video reference is only a typed Generate input and does not create Edit, Continue, or
Extend operations. The existing billing, recovery, and lifecycle rules remain unchanged.

The overlay is applied only after a fresh catalog observation confirms the exact model still
exists. A stale last-known-good catalog may preserve existing non-reference behavior but cannot
activate overlay-backed reference intent.

Prompt remains required for every v0.1 Generate request. Prompt-optional reference generation is
`DEFERRED` and is not a Phase-8 completion gate.

## Consequences

- Multi-image references with 2–50 entries, video references, and mixed image/video references with
  at most 50 entries become available for the exact approved Seedance 2.5 model.
- Unknown or near-matching models continue to return `CAPABILITY_SIGNAL_GAP` or `UNSUPPORTED`
  according to their proven signals.
- The overlay and its provenance are source-reviewed data, not capability-cache truth and not a
  provider branch.
- No new retry, submit, credential, passthrough, upload, audio, edit/extend, or telemetry surface is
  introduced.
- When Level A exposes sufficient reference metadata, it becomes authoritative and the redundant
  overlay entry is retired after review without changing the product request surface.

## Evidence

- <https://openrouter.ai/blog/insights/seedance-2-5-review/>
- [Phase 8 capability evidence](../phase-8-capability-evidence.md)
