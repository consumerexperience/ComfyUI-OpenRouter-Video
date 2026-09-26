# Phase 8 capability evidence and enforcement matrix

## Observation

- `OBSERVED_AT_UTC`: `2026-09-26T09:52:56.128152+00:00`
- `ENDPOINT`: `GET https://openrouter.ai/api/v1/videos/models`
- Authentication: none; no credential or environment inspection
- Result: `200`, 29 models
- Provenance: live read-only catalog observation produced by the sanitized manual harness
- Evidence class: `OBSERVED`

The observed model objects exposed these fields:

```text
allowed_passthrough_parameters, canonical_slug, created, creativity, description,
generate_audio, hugging_face_id, id, name, pricing_skus, seed,
supported_aspect_ratios, supported_durations, supported_frame_images,
supported_resolutions, supported_sizes, upscale_factor
```

The observation contained no `input_modalities`, direct `input_references` capability,
reference-kind, reference-count, heterogeneous-collection, `prompt_required`, or `prompt_optional`
field. Unknown future fields remain tolerated but are not interpreted.

## Product decision and reviewed overlay

On 2026-09-26 the Product Owner accepted
[ADR-030](adr/ADR-030-evidence-backed-capability-overlay.md). A reviewed first-party B2 entry may
fill only Level-A fields that are absent, only after a fresh catalog observation confirms an exact
model ID. It cannot override Level A, use a provider/family/name pattern, or authorize another model.

The initial entry is `bytedance/seedance-2.5`: `{IMAGE, VIDEO}`, maximum 50 references, and mixed
image/video collections supported. The evidence source was rechecked on 2026-09-26:
<https://openrouter.ai/blog/insights/seedance-2-5-review/>. It explicitly identifies the model,
documents image/video/audio references, reports the model-page limit of 50, and shows one mixed
`video_url + image_url` request. Audio remains outside the product.

## Field-level evidence map

| Field or relationship | Provenance | Evidence class | Runtime enforcement eligibility | Conclusion |
| --- | --- | --- | --- | --- |
| `supported_frame_images` | Level A live catalog | `OBSERVED` | frame modes only | Per-model `first_frame` and `last_frame` checks are eligible. |
| Typed `frame_images` request shape | Level B1 video-generation guide | `CONFIRMED` | generic Core serialization | Use `type=image_url`, nested `image_url.url`, and `frame_type`. |
| Typed image `input_references` shape | Level B1 video-generation guide | `CONFIRMED` | protocol serialization only | Does not prove any selected model accepts it. |
| Typed video and mixed references | Level B2 Seedance documentation | `CONFIRMED` | exact-ID ADR-030 overlay only | Enables only the reviewed Seedance 2.5 data entry. |
| `input_modalities` | Level A live catalog | `UNKNOWN` | none | Field was absent; no bridge to `input_references` exists. |
| Reference media kinds | Level A absent; ADR-030 Seedance entry | `CONFIRMED` for exact ID | fill absent field only | `{IMAGE, VIDEO}` only for `bytedance/seedance-2.5`; otherwise `CAPABILITY_SIGNAL_GAP`. |
| Reference count >= 2 | Level A absent; ADR-030 Seedance entry | `CONFIRMED` for exact ID | fill absent field only | Maximum 50 only for the approved exact model. |
| Heterogeneous image+video collection | Level A absent; ADR-030 Seedance entry | `CONFIRMED` for exact ID | fill absent field only | Mixed collection supported only for the approved exact model. |
| Prompt required | Product v0.1 contract plus first-party required-prompt evidence | `CONFIRMED` | generic Core validation | Non-empty prompt remains required for every Generate operation. |
| Prompt optional for reference generation | conflicting first-party prose; no Level A flag | `CONFLICT` upstream | none | `DEFERRED`; not a Phase-8 completion gate. |

Primary first-party sources:

- <https://openrouter.ai/docs/guides/overview/multimodal/video-generation>
- <https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-models>
- <https://openrouter.ai/blog/announcements/video-generation/>
- <https://openrouter.ai/blog/insights/seedance-2-5-review/>

## Mode-level enforcement matrix

The matrix is evaluated independently for the selected model. One blocked intent does not disable
another proven intent.

| Mode | Status | Runtime rule |
| --- | --- | --- |
| `T2V` | `READY` | Catalog membership plus the generic required-prompt contract. |
| `FIRST_FRAME` | `READY` or `UNSUPPORTED` | `READY` only when Level A includes `first_frame`. |
| `FIRST_PLUS_LAST` | `READY` or `UNSUPPORTED` | `READY` only when the same Level-A record includes both values. |
| `MULTI_IMAGE_REFERENCE` | `READY` for approved exact IDs; otherwise scoped result | Seedance 2.5 accepts 2–50 image references. Unknown evidence remains `CAPABILITY_SIGNAL_GAP`. |
| `VIDEO_REFERENCE` | `READY` for approved exact IDs; otherwise scoped result | Seedance 2.5 has a proven video kind. Unknown evidence remains `CAPABILITY_SIGNAL_GAP`. |
| `IMAGE_PLUS_VIDEO_REFERENCE` | `READY` for approved exact IDs; otherwise scoped result | Seedance 2.5 has proven kinds, mix, and total count <=50. |
| `PROMPT_OPTIONAL_REFERENCE_GENERATION` | `DEFERRED` | Prompt remains required by the narrower v0.1 product contract. |

`InputReferenceKind.VIDEO` is only a typed transport reference. It never selects Edit, Continue,
or Extend behavior; Generate remains the sole lifecycle.

## Controlled delta

- `CONTRACT_DRIFT: PRESENT`: the previous flat frame objects were replaced with the current typed
  media representation.
- `UPSTREAM_EXPANSION: PRESENT`: image/video reference protocol objects exist, including documented
  mixed-reference examples.
- Core and Comfy assemble the typed reference contract while preserving order and duplicate
  occurrences. Core enables a reference mode only from Level A or reviewed exact-ID overlay data;
  every unresolved model remains fail-closed before submit authority.
- Level A wins over the overlay. An explicit disagreement is `CONFLICT`, retains the Level-A value,
  and blocks reference intent pending review.
- Overlay-backed reference modes require a fresh catalog observation. A stale LKG cannot activate
  them.
- The reusable probe is `tests/manual/phase8_catalog_probe.py`. It never reads credentials, follows
  redirects, or emits a raw body, and it is excluded from pytest and CI.

## Phase result

`IMPLEMENTATION COMPLETE — DELIVERY PENDING`: T2V, model-proven frame modes, and all required
reference modes for `bytedance/seedance-2.5` are zero-cost verified through contract fixtures and
the mock Generate lifecycle. Unknown models remain fail-closed. Phase 8 still requires human review,
merge, and canonical `origin/main` read-back before project-level `DONE`.
