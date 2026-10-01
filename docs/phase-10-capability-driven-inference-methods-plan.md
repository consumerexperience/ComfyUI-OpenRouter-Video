# Phase 10 — Capability-Driven Inference Methods & Multimodal Expansion

- Status: `LOCAL IMPLEMENTATION PRESENT — DESIGN QA PARTIAL; DELIVERY OPEN`
- Canonical baseline: `main@b492184f41492d37677a2dde9afdbe88666717a2`
- Feature branch: `phase-10/capability-driven-inference-methods`
- Product direction: `Direction 3 — APPROVED`
- Paid generation authority: `NONE`
- Merge authority: `HUMAN ONLY`

## Objective

Add an explicit local Inference Method to the approved Direction 3 Generate experience while keeping
primitive evidence-backed capabilities as the only capability truth. Expand exact Seedance 2.5 input
support to IMAGE, VIDEO, and AUDIO references; preserve Edit and Extend as distinct local intents; and
retain the existing durable Core lifecycle, billing safety, recovery, and security boundaries.

This is a new phase from canonical main. It is not a continuation of the completed Phase 9 branch.

## Product taxonomy

For exact model `bytedance/seedance-2.5`:

| Method | Meaning | Required topology |
| --- | --- | --- |
| `T2V` | Text → Video | no media |
| `I2V` | First Frame → Video | exactly one First Frame IMAGE |
| `FLF2V` | First + Last Frame → Video | both frame IMAGE inputs |
| `IR2V` | Single Image Reference → Video | exactly one IMAGE reference |
| `MI2V` | Multiple Image References → Video | at least two IMAGE references |
| `VR2V` | Video Reference → Video | at least one VIDEO reference |
| `AR2V` | Audio Reference → Video | at least one AUDIO reference |
| `MMR2V` | Mixed Multimodal References → Video | at least two refs and two distinct kinds |
| `V2V_EDIT` | Source Video → Edited Video | required Source Video; local EDIT intent |
| `V2V_EXTEND` | Source Video → Extended Video | required Source Video; local EXTEND intent |

`IR2V` is not `I2V`. A single IMAGE reference is guidance; First Frame pins a frame. AUDIO input and
generated output audio are independent capabilities.

## Architecture contract

```text
UPSTREAM / EVIDENCE PRIMITIVES
frame types · reference kinds · reference limit · mixed-kind support
edit · extend · audio reference · seed · generated audio · geometry · duration
                         ↓ deterministic derivation
PRODUCT INFERENCE METHODS
T2V · I2V · FLF2V · IR2V · MI2V · VR2V · AR2V · MMR2V · V2V_EDIT · V2V_EXTEND
                         ↓ product UX policy
PREFERRED METHOD
bytedance/seedance-2.5 → MI2V
```

There is no independently maintained `supported_inference_methods` truth. The derivation registry is
pure, deterministic, and covered by tests. Only READY methods appear in a normal dropdown.

The exact evidence and superseding decision are frozen in:

- [Phase 10.0 Evidence Gate](phase-10-evidence-gate.md)
- [ADR-031](adr/ADR-031-capability-driven-inference-methods-and-multimodal-references.md)

## Request and serialization contract

`GenerationRequest.inference_method` is local intent used for validation, persistence, migration,
fingerprint v3, frontend projection, and Core capability validation. It is never sent upstream.

The serializer emits only confirmed OpenRouter fields. It must not emit `method`, `inference_method`,
`source_role`, or `source_video`.

For V2V, Source Video is first in ordered `input_references`; optional references follow. Source Video
is required, consumes one reference slot, and is never automatically removed. The serializer uses the
ordinary confirmed `video_url` object.

The exact AUDIO object is:

```json
{
  "type": "audio_url",
  "audio_url": {"url": "https://example.com/reference.mp3"}
}
```

## Dynamic inputs

Autogrow always maintains exactly one free trailing socket until the exact-model limit is reached.
Connecting N creates N+1. Reaching the limit removes only the free socket. It never removes, compacts,
reorders, or deduplicates connected links.

For MMR2V, valid kinds are IMAGE, VIDEO, and AUDIO. Valid topology requires `reference_count >= 2`
and `distinct_kind_count >= 2`. Duplicate occurrences remain meaningful and ordered.

## Method and model switching

- With no model, Inference Method is disabled: `Select model first`.
- First model selection on a new node applies the model's product preference.
- An explicit method, any connected media, or a loaded workflow suppresses automatic preference.
- Incompatible model switch preserves method and links, shows blocked state, and blocks Generate.
- A method switch that would orphan media is rejected without changing state.

## Persistence, migration, and fingerprint

Legacy workflows derive the initial method from actual topology:

```text
no media                  → T2V
First Frame               → I2V
First + Last              → FLF2V
one IMAGE reference       → IR2V
2+ IMAGE references       → MI2V
VIDEO references          → VR2V
AUDIO references          → AR2V only if historical topology exists
mixed references          → MMR2V
```

A historical VIDEO reference is never promoted to Edit or Extend because its original intent is
unknown. Preferred MI2V applies only to a genuinely new node without persisted intent.

Fingerprint v1 and v2 remain immutable. New Phase-10 Generate operations use the structural,
non-sensitive v3 contract in ADR-031. Different intent under an existing operation ID is a conservative
conflict and cannot grant a second submit.

## UI contract

The canonical visual target is [Direction 3 Visual Specification](phase-10-direction-3-visual-spec.md).
The node order is Model → Inference Method → Prompt → geometry → duration → seed/audio → Advanced.
Transport-specific helper nodes are `Public Image URL`, `Public Video URL`, and `Public Audio URL`.
Native local IMAGE/VIDEO/AUDIO transport is not claimed in this phase without separate evidence.

## Lifecycle and pricing

The durable lifecycle is unchanged. UI `GENERATING` is only the presentation mapping for durable
`ACCEPTED/POLLING`.

The estimator receives method, ordered reference kinds, reference count, Source Video presence,
duration, resolution, and other proven price determinants. It may show a value only for an exact
matching SKU/formula. Ambiguity produces `ESTIMATE UNAVAILABLE`. No method-name, provider, family, or
slug-pattern pricing branch is allowed.

## Stable invariants

- at most one paid POST per Generate operation;
- Resume has zero submit capability;
- poll failure is not generation failure;
- no implicit or ambiguous resubmit;
- Core is final capability, validation, billing, and submit authority;
- credentials remain outside workflow, persistence, source, logs, and reports;
- prompt text and media URLs do not enter request fingerprints;
- no provider passthrough, product telemetry, or identity expansion;
- AppIdentity remains frozen;
- paid POST count remains zero without immediate explicit Product Owner authorization;
- merge remains human-only.

## Execution order and current gate

| # | Step | State |
| ---: | --- | --- |
| 1 | Read canonical main `b492184f…` | `COMPLETE` |
| 2 | Create new Phase-10 feature branch | `COMPLETE` |
| 3 | Phase 10.0 Evidence Gate | `COMPLETE` |
| 4 | Add superseding ADR | `COMPLETE` |
| 5 | Define primitive capability model | `COMPLETE — ARCHITECTURE CONTRACT` |
| 6 | Define deterministic method derivation registry | `COMPLETE — ARCHITECTURE CONTRACT` |
| 7 | Define Seedance 2.5 preference `MI2V` | `COMPLETE — PRODUCT POLICY` |
| 8 | Consolidate canonical Phase-10 plan | `COMPLETE` |
| 9 | Refine Direction 3 visual specification | `COMPLETE` |
| 10 | Product Owner visual acceptance | `COMPLETE — "Direction 3 Phase 10 visual accepted"` |
| 11 | Implement Core domain, validation, AUDIO, V2V roles, fingerprint v3, migration | `COMPLETE` |
| 12 | Update Comfy adapter | `COMPLETE` |
| 13 | Update frontend projection and dynamic sockets | `COMPLETE` |
| 14 | Update pricing estimator | `COMPLETE` |
| 15 | Product Design QA | `PARTIAL — primary MI2V, 1→2→3 autogrow, and 50-link max/save/reload now visually checked; lifecycle, v0.37.0, and Owner acceptance open` |
| 16 | Technical verifier | `PARTIAL — 229 Python tests previously passed after the backend delta; 9 current frontend regression tests, JS syntax, and diff hygiene pass; delivery not verified` |
| 17 | Browser matrix on ComfyUI v0.34.3 and v0.37.0 | `PARTIAL — v0.34.3 exercised on real canvas; v0.37.0 not run` |
| 18 | Canonical 8189 zero-cost acceptance, no mocks/queue/POST | `PARTIAL — 30 real models and UI contract 4; no Run/paid POST; full lifecycle state matrix open` |
| 19 | Open new Phase-10 draft PR | `NOT STARTED` |
| 20 | Human-only review and merge | `NOT STARTED` |

Local implementation exists. Step 15 Product Design QA remains the first unfinished gate; later
technical and delivery evidence does not replace it.

## Acceptance matrix

Implementation must prove:

- every method maps to its exact local topology and exact upstream payload;
- local intent/source roles are absent upstream;
- AUDIO uses the confirmed typed wire object;
- methods derive only from primitive exact-model capability truth;
- unsupported and signal-gap methods are hidden, while persisted incompatibility remains visible;
- one trailing socket, exact limit stop, ordered duplicates, and no automatic link deletion;
- every topology minimum and Source Video requirement blocks before submit;
- legacy migration never promotes VR2V to Edit or Extend;
- v3 fingerprint is stable and non-sensitive;
- save/reload preserves explicit intent and topology;
- real mouse acceptance passes on both blocking ComfyUI hosts;
- canonical 8189 acceptance uses real catalogue and capabilities with no mocks, workflow queue, or paid POST.
