# Native local media transport evidence gate — 2026-10-01

Status: **IMAGE FIRST-PARTY IMPLEMENTATION EVIDENCE ACCEPTED FOR A1 BY PRODUCT OWNER**.

Product Owner decision (2026-10-01): the official Multimedia Explorer's IMAGE data-URL
submission path is sufficient to implement a bounded native Comfy IMAGE bridge. This is an
implementation authorization for IMAGE only, including the existing IMAGE reference/frame
representations. It is not evidence of an observed provider-accepted paid job. The stricter
historical HTTPS-only transport assumption is superseded for this narrow IMAGE path only.
VIDEO and AUDIO remain probe-gated; storage is not approved and is only a potential fallback
after a separate decision if direct transport fails.

## Product request

Connect local ComfyUI `Load Image`, `Load Video`, and `Load Audio` outputs to the appropriate
Generate media inputs without asking the user to publish or paste a URL. This is a new transport
architecture request, separate from Phase 10's approved public-HTTPS helper-node path.

## Boundary before A1

ADR-031 permitted Public HTTPS URL helpers and did not claim native local IMAGE/VIDEO/AUDIO
transport without a separate contract. Before A1, Core validation rejected non-public-HTTPS
reference URLs and the Comfy adapter produced typed references from URL helpers only. No local
media bytes, prompt, URL, or credential may be persisted in a
workflow, operation record, fixture, or log. One paid Video POST maximum and zero implicit resubmit
remain unchanged.

## Current primary evidence

| Evidence | Classification | Transport implication |
| --- | --- | --- |
| [OpenRouter Video generation guide](https://openrouter.ai/docs/guides/overview/multimodal/video-generation) | CONFIRMED documentation | Shows `frame_images` and `input_references` as URL-bearing objects with HTTPS examples; does not describe local bytes/data URLs for this endpoint. |
| [OpenRouter image-to-video article](https://openrouter.ai/blog/insights/image-to-video-models-compared/) | CONFIRMED first-party guidance, published 2026-09-29 | Instructs use of stable, directly downloadable HTTPS image URLs before paid submit. |
| [OpenRouter OpenAPI schema](https://openrouter.ai/openapi.json) | OBSERVED live schema on 2026-10-01 | `FrameImage` wraps `ContentPartImage`; `InputReference` is a union of image/audio/video URL parts. Each nested `url` is merely `string`; this does not prove that a data URI is processed by the Video endpoint/provider. No file-ID variant is listed. |
| [Official Multimedia Explorer input UI](https://github.com/OpenRouterTeam/multimedia-explorer/blob/main/components/cards/references-card.tsx) and [video submit mapping](https://github.com/OpenRouterTeam/multimedia-explorer/blob/main/components/generate-form.tsx) | OBSERVED first-party source | Local IMAGE files are read as data URLs and passed into video `input_references`. This is implementation evidence for intended IMAGE behavior, but not an observed accepted job and not evidence for VIDEO/AUDIO or `frame_images`. It conflicts with the HTTPS-only guidance above. |
| [OpenRouter Files API](https://openrouter.ai/docs/client-sdks/typescript/api-reference/files) and [privacy policy](https://openrouter.ai/privacy) | CONFIRMED API/storage documentation | Files can be uploaded and retained, but no authoritative mapping from returned file ID to Video `frame_images`/`input_references` is documented. Persistent storage/retention would require a separate privacy decision. |

Generic base64 multimodal examples for Chat Completions, Responses, and Image Generation do not
establish the dedicated `POST /api/v1/videos` transport. Third-party claims of data-URL success
are corroborating at most, never a replacement for the missing exact Video contract.

## Disposition

- Local Comfy IMAGE decoding and bounded data-URL adaptation are approved for A1. The upstream
  source form for native VIDEO/AUDIO remains **UNKNOWN**.
- IMAGE data-URL support has conflicting first-party signals; the Product Owner has accepted
  the official implementation path as sufficient for A1. VIDEO and AUDIO data-URL support
  remain **UNKNOWN / PROBE-GATED**. OpenRouter Files API compatibility is **UNKNOWN**.
- A1 may transiently encode native Comfy IMAGE as a bounded PNG data URL for the existing
  IMAGE request fields. Never persist or log it. Do not relax VIDEO/AUDIO HTTPS validation.
- A bounded, explicitly authorized Video contract probe would be paid; A1 grants no paid-submit
  authority. Alternatively, Product Owner can choose a public object-storage publisher
  with explicit storage, credentials, access, retention, and failure policy. Neither route is an
  implementation detail that can be silently selected.

`CONTRACT_DRIFT`: **FIRST-PARTY IMAGE SIGNAL CONFLICT RECORDED; A1 IMPLEMENTATION DECISION ACCEPTED**.
No accepted Video job has been demonstrated; paid validation remains separately gated.
`UPSTREAM_EXPANSION`: **UNKNOWN** for VIDEO/AUDIO native
transport and Files API attachment. Affected scope is native local media only; existing HTTPS
helpers, capability-driven methods, billing, recovery, and presentation remain valid.
