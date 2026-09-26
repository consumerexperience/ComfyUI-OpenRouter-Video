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

## Field-level evidence map

| Field or relationship | Provenance | Evidence class | Runtime enforcement eligibility | Conclusion |
| --- | --- | --- | --- | --- |
| `supported_frame_images` | Level A live catalog | `OBSERVED` | frame modes only | Per-model `first_frame` and `last_frame` checks are eligible. |
| Typed `frame_images` request shape | Level B1 video-generation guide | `CONFIRMED` | generic Core serialization | Use `type=image_url`, nested `image_url.url`, and `frame_type`. |
| Typed image `input_references` shape | Level B1 video-generation guide | `CONFIRMED` | protocol serialization only | Does not prove any selected model accepts it. |
| Typed video and mixed references | Level B2 Seedance documentation | `CONFIRMED` | none for model selection | Confirms upstream expansion, not a runtime signal. |
| `input_modalities` | Level A live catalog | `UNKNOWN` | none | Field was absent; no bridge to `input_references` exists. |
| Reference media kinds | Level A live catalog | `UNKNOWN` | none | `CAPABILITY_SIGNAL_GAP`. |
| Reference count >= 2 | Level A live catalog | `UNKNOWN` | none | `CAPABILITY_SIGNAL_GAP`; image support cannot imply multi-image support. |
| Heterogeneous image+video collection | Level A live catalog | `UNKNOWN` | none | `CAPABILITY_SIGNAL_GAP`. |
| Prompt required for T2V | Level B1 video-generation guide | `CONFIRMED` | generic T2V validation | Non-empty prompt remains required for T2V. |
| Prompt optional for reference generation | conflicting first-party prose; no Level A flag | `CONFLICT` | none | Omission fails closed before submit. |

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
| `MULTI_IMAGE_REFERENCE` | `CAPABILITY_SIGNAL_GAP` | No direct kind or count>=2 signal. |
| `VIDEO_REFERENCE` | `CAPABILITY_SIGNAL_GAP` | No direct video-reference signal. |
| `IMAGE_PLUS_VIDEO_REFERENCE` | `CAPABILITY_SIGNAL_GAP` | No direct kind and heterogeneous-collection signal. |
| `PROMPT_OPTIONAL_REFERENCE_GENERATION` | `CONFLICT` | First-party prose conflicts and Level A exposes no positive flag. |

`InputReferenceKind.VIDEO` is only a typed transport reference. It never selects Edit, Continue,
or Extend behavior; Generate remains the sole lifecycle.

## Controlled delta

- `CONTRACT_DRIFT: PRESENT`: the previous flat frame objects were replaced with the current typed
  media representation.
- `UPSTREAM_EXPANSION: PRESENT`: image/video reference protocol objects exist, including documented
  mixed-reference examples.
- Core and Comfy can assemble the approved typed reference contract, preserving order and duplicate
  occurrences, but Core returns sanitized `CAPABILITY_SIGNAL_GAP` before submit authority for every
  reference mode until Level A exposes the required model-specific signals.
- The reusable probe is `tests/manual/phase8_catalog_probe.py`. It never reads credentials, follows
  redirects, or emits a raw body, and it is excluded from pytest and CI.

## Phase result

`PARTIAL`: T2V and model-proven frame modes are zero-cost verified. Mandatory reference modes are
structurally implemented and tested but are not runtime-enabled because current authoritative
machine-readable evidence cannot resolve model kind/count/mix support. The one next action is for
OpenRouter to expose a direct runtime capability signal, or for the Product Owner to approve a
different explicit runtime policy after reviewing new authoritative evidence.
