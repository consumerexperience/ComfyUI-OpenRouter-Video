# Phase 9 Local Media Transport Contract Check

Observed: `2026-09-27`

## Question

Can OpenRouter Video reference inputs be populated from native local Comfy IMAGE/VIDEO values without
first exposing media through a publicly retrievable URL?

## Authoritative evidence

The current OpenRouter Video generation guide represents both `frame_images` and
`input_references` as URL-bearing objects and states that referenced resources must be accessible:

- <https://openrouter.ai/docs/guides/overview/multimodal/video-generation>
- <https://openrouter.ai/blog/insights/seedance-2-5-review/>

The Video contract reviewed here does not document data URLs, base64 payloads, multipart upload or a
first-party upload endpoint as accepted transport for these fields. Support for data URLs in another
OpenRouter API is not evidence that Video accepts them.

## Phase-9 disposition

```text
PUBLIC HTTPS URL TRANSPORT = PROVEN / IMPLEMENTED
NATIVE LOCAL IMAGE TRANSPORT = UNPROVEN
NATIVE LOCAL VIDEO TRANSPORT = UNPROVEN
PAID CONTRACT PROBE = NOT AUTHORIZED
```

Therefore the Release Candidate presents Public Image URL and Public Video URL reference nodes and
labels First/Last Frame as Public HTTPS URL inputs. It does not claim native local media transport.
The direct ordered/autogrowing Generate topology still provides clear image/video categorization and
selected-model count enforcement without inventing an upstream transport contract.

A future native-local-media implementation requires authoritative contract evidence or a separately
approved bounded live contract probe. It must not be inferred or paid-tested under the current
Phase-9 authorization.
