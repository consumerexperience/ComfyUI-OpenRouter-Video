# Phase 5 OpenRouter Video contract evidence gate

Inspected: 2026-09-04. Sources are first-party OpenRouter documentation. No OpenRouter API request
was made.

## Result

- `CONFIRMED`: `GET /api/v1/videos/models` returns a `data` list with model IDs and typed
  capability fields including durations, resolutions, aspect ratios, sizes, frame-image support,
  audio support, and seed metadata.
- `CONFIRMED`: `POST /api/v1/videos` accepts the frozen v0.1 fields `model`, `prompt`, `duration`,
  `resolution`, `aspect_ratio`, `size`, `seed`, `generate_audio`, and `frame_images`, and returns an
  asynchronous job resource on HTTP 202.
- `CONFIRMED`: `GET /api/v1/videos/{job_id}` returns job identity, status, and, when available,
  `generation_id`, `unsigned_urls`, `usage.cost`, and error data.
- `CONFIRMED`: `GET /api/v1/videos/{job_id}/content?index=0` streams raw provider video bytes; the
  documented default index is zero.
- `CONFIRMED`: the documented ordinary statuses are `pending`, `in_progress`, `completed`, and
  `failed`.
- `OBSERVED`: the current first-party OpenRouter tutorial additionally documents `cancelled` and
  `expired` as terminal states and recommends roughly 30-second polling with a ceiling.
- `CONFIRMED`: current submit errors include 400, 401, 402, 404, 429, and 500. Content errors also
  include 502.
- `UNKNOWN`: the Video API reference does not define an endpoint-specific `Retry-After` contract.
  Phase 5 may parse a valid bounded HTTP `Retry-After` value defensively for retry-safe GETs but
  does not depend on its presence and never retries submit.

## Contract drift

`CONTRACT_DRIFT: NONE` for the frozen Phase-5 endpoint set and request surface.

## Upstream expansion

`UPSTREAM_EXPANSION: PRESENT, OUT OF V0.1 SCOPE`.

Current submit documentation also exposes `callback_url`, `input_references`, and provider-specific
passthrough configuration. These are additive upstream fields. Tolerant input readers may ignore
unknown response/catalog fields, but Phase 5 does not add these request capabilities or arbitrary
provider JSON.

## Authority boundary

Returned `polling_url` and `unsigned_urls` remain response data, not destination authority. The Core
reconstructs polling and content requests from the trusted `job_id` through the canonical
OpenRouter request policy.

## Primary sources

- [List all video generation models](https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-models)
- [Submit a video generation request](https://openrouter.ai/docs/api/api-reference/video-generation/create-videos)
- [Poll video generation status](https://openrouter.ai/docs/api/api-reference/video-generation/get-videos)
- [Download generated video content](https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-content)
- [Video Generation guide](https://openrouter.ai/docs/guides/overview/multimodal/video-generation)
- [OpenRouter Video Generation API tutorial](https://openrouter.ai/blog/tutorials/video-generation-api/)

