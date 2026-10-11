# Adaptive generation controls: implementation audit

Authority: the identical Owner assignments attached on 11 October 2026.
Working branch: `feature/adaptive-generation-controls`.
Baseline tag: `openrouter-video-native-media-e2e-v1`.
Accepted SHA, current remote main and working base:
`72998e931e5e9e59a277b63c2f2b0cd4cb513164`.
No later main commits were observed after fetch. The original dirty checkout is preserved.

## Accepted baseline end-to-end path (before this feature)

1. `client._parse_capability` reads `supported_resolutions` into a nullable string tuple.
2. The same parser reads `supported_aspect_ratios` into a nullable string tuple.
3. `supported_durations` becomes a nullable integer tuple. A range object is currently unknown.
4. All three already belong to `ModelCapabilities`; they also have structured API provenance
   in `CapabilityFact`. No second catalogue subsystem is needed.
5. No normalized joint configuration relation exists. `RequestValidator.validate_capabilities`
   checks each field separately. Membership checks cannot prove a combination is supported.
6. The packaged exact-model evidence manifest exists. Its current recognized facts concern
   inference/reference capability and preferred inference method, not configuration tuples.
7. Frontend `configureEnum` creates real combos for Resolution, Aspect Ratio and Exact Size.
8. Backend schema retains STRING geometry and INT duration for compatibility. Frontend Duration
   alternates between combo and numeric widget when the supported values form an arithmetic
   progression. This does not satisfy the requested unconditional finite-duration combo.
9. Model callbacks call `projectSelectedModel`, which reloads the selected capability and
   independently configures each control. Saved unsupported values are retained.
10. There is **no separate Mode control in the accepted Generate node**. Mode concepts are
    represented by the inference recipes/methods. Adding a separate Mode would expand scope.
11. Inference Method changes apply the existing topology and subsequently request model
    projection through the estimate callback. Geometry is not method-filtered today.
12. Save/reload uses named values plus Phase 8/9/10 positional restoration and preserved
    widget ordering. Geometry replacements retain serialization hooks. Backend request
    `GenerationRequest.to_api_payload` keeps exact selected wire values; AUTO/zero omit fields.
13. Known-invalid saved values remain visible with an incompatibility disclosure, and backend
    membership validation rejects them. For null capability arrays, explicit values are
    currently **not rejected** by `_supported`. A warning alone is not submit enforcement.
14. Reuse `configureModelPicker`, `configureInferenceMethod`, `configureEnum`,
    `projectSelectedModel`, named-value serialization and existing restore functions.
    Preserve method semantics, reference topology and all request/media lifecycle code.

## Live evidence

See `configuration-audit.json` and `evidence/`. The public video catalogue and healthy
canonical DEV projection have identical sets of 30 exact model IDs. All 30 official model
pages were retrieved; their embedded endpoint metadata was extracted offline.

Observed at: `2026-10-11 01:29:55 Europe/Moscow`
(`2026-10-10T22:29:55.404974+00:00`).

- Resolution union: `480p`, `720p`, `768p`, `1080p`, `2K`, `4K`.
- Aspect ratio union: `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `3:2`, `2:3`, `21:9`, `9:21`.
- Duration union: integer seconds 1 through 30; each model retains its own discrete list.
- Exact dimensions are retained separately in the JSON vocabulary. No named preset/pixel
  conversion has been inferred, including `2K` and rounded dimensions such as `854x480`.
- 674 individual catalogue configuration values are represented in the existing projection;
  zero individual values are missing. This is **axis coverage**, not tuple coverage.
- 28 models have at least one populated configuration axis. Twelve have at least one null
  axis. All 30 lack an explicit complete joint relation in the inspected structured metadata.
- Seedance 2.0 Mini has a source discrepancy: catalogue includes `9:21`, whereas embedded
  exact official endpoint metadata omits it. Higher-precedence catalogue evidence is retained;
  absence from that endpoint list is recorded for review, not silently reconciled.

The [OpenRouter API reference](https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-models)
documents independent arrays, not a tuple/rule schema. Its
[code-first guide](https://openrouter.ai/blog/tutorials/video-generation-api/)
explicitly describes `720p / 16:9 / 4s` for Seedance 2.0, Veo 3.1 and Wan 2.7,
but does not enumerate every valid configuration or every input/method context.
The [comparison article](https://openrouter.ai/blog/insights/image-to-video-models-compared/)
adds exact-model axis facts but likewise does not establish complete independence.

Provider evidence needs exact route/version binding. Google's
[Gemini Veo documentation](https://ai.google.dev/gemini-api/docs/veo?hl=en)
describes duration/input coupling, including eight-second restrictions. However,
OpenRouter exposes Google Vertex, whose
[current model reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate?hl=en)
has different version/feature distinctions. Importing Gemini-specific restrictions into
every OpenRouter Veo route solely by the family name would violate the assignment.

## Configuration design ready for policy resolution

Extend the existing capability profile and evidence pipeline, with three distinct layers:

1. Nullable **axis domains**, retaining exact wire values and source provenance.
2. Explicit reviewed **configuration clauses/tuples**, scoped to exact model, accepted
   inference method, audio/input conditions and optional future context. Clauses may contain
   finite domains and integer `min/max/step`; expansion must be bounded and validated.
3. **Coverage state**: complete relation, partial relation, axis-only, unknown, conflict,
   or unmapped vocabulary. Missing keys never become wildcards or confirmed independence.

A clause permits a Cartesian product only when independence within that clause is explicitly
confirmed. Project each control by filtering the relation against the other compatible
selections, excluding its own value so the user can repair an incompatible selection.
Never silently substitute saved values. Backend validation and UI projection consume the
same relation and coverage state; a UI warning alone cannot enforce tuple validity.

Exact Size remains a separate conditional control. Derive ratios from dimensions only with
an explicit reversible mapping; do not rewrite request body semantics or infer preset pixels.
Do not create a Mode widget. Bind contexts to the existing methods/recipes.

New models using a documented known schema should be normalized generically, without IDs in
product code. A synthetic future-model test proves the ontology, not a claim that today's
OpenRouter publishes an invented `supported_configurations` field. Unknown fields must be
retained as unmapped evidence. Reviewed nonstructured tuples are data-only promotions through
the current hashed/versioned manifest, with candidate semantic diff and explicit review.

## Resolved product decision

The Owner explicitly selected strategy 1 with the following refinement on 11 October:
confirmed independent parameter domains allow their constrained cross-product. Absence of
tuple documentation is not UNKNOWN. Explicit dependencies use tuple/constraint projection.
Confirmed-invalid tuples are unavailable/blocked; a specific unknown tuple within known
coupling fails closed. Existing accepted Generate is not globally blocked.

The current structured catalogue and OpenRouter request contract describe independent
parameter domains. No explicit complete coupling relation was published in the inspected
catalogue or embedded endpoint metadata. Provider-specific candidates remain research
evidence until an exact OpenRouter route/version mapping is confirmed; they are not silently
promoted into packaged constraints. Seedance Mini's axis discrepancy remains visible in the
audit; the highest-precedence live catalogue axis is retained.

Implementation extends `CapabilityFact` with the generic reviewed `configuration_constraints`
ontology. The existing cache persists those facts without schema or migration changes.
`configuration.py` implements complete/partial/forbidden relations and context projection.
Frontend projection consumes the normalized relations. Duration is always a real combo.
Backend validation rejects invalid/constraint-unknown requests before the existing submit
lifecycle. Geometry and request wire values remain unchanged; no preset conversion is added.

The contract guard remains bound to its accepted source snapshot `0f05665…`; the working
base/main/tag is `72998e9…`. Baseline tests establish source equivalence, not a new acceptance
of a rewritten snapshot. The delta permits only six exact configuration/control files.
Packaged evidence, accepted snapshots, Specification, ADRs and migrations remain unchanged.

## Final verification

See [verification-report.md](verification-report.md) for completed gates, current evidence and limitations.
