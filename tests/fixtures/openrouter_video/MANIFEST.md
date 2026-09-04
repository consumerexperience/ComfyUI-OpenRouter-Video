# OpenRouter Video contract fixture manifest

Evidence date: **2026-09-05**. These fixtures are a reviewed executable contract snapshot, not
eternal OpenRouter truth and not proof of current live-service behavior. No API request was made.

| Fixture family | Endpoint / operation | Purpose and represented fields | Authority | Class | Intentionally ignored / uncertainty |
| --- | --- | --- | --- | --- | --- |
| `discovery/catalog.json` | `GET /api/v1/videos/models` | `data`, id, slug, name, durations, resolutions, ratios, sizes, frame support, audio, seed | OpenRouter Video API reference and guide | CONFIRMED | description, pricing, passthrough and future fields; synthetic capability values do not describe vendors |
| `discovery/empty.json` | discovery | valid empty catalog | response schema | CONFIRMED | availability meaning is runtime-dependent |
| `discovery/malformed_*.json` | discovery | missing required id and wrong envelope type | required response shape | CONFIRMED | exact upstream malformed behavior is UNKNOWN |
| `submit/accepted.json` | `POST /api/v1/videos` | id, status, polling_url, generation_id, unsigned_urls | OpenRouter create-video reference and guide | CONFIRMED | returned URLs are represented but non-authoritative in this product |
| `poll/pending.json`, `in_progress.json`, `completed_*.json` | `GET /api/v1/videos/{job_id}` | active/completed status, generation_id, usage.cost, additive metadata | OpenRouter poll reference and guide | CONFIRMED | cost may be absent; absence is not zero |
| `poll/failed.json` | poll | remote failed terminal | OpenRouter guide | CONFIRMED | error text is synthetic |
| `poll/cancelled.json`, `expired.json` | poll | conservative remote terminal states | OpenRouter first-party webhook/cookbook docs | OBSERVED | main status table currently omits these rows; webhook corpus names them |
| `poll/future_unknown.json` | poll | future status tolerant-reader behavior | architecture fitness requirement | INFERRED | spelling is intentionally synthetic |
| `errors/response_cases.json` | all operations | reviewed status matrix and evidence class | endpoint API references | mixed | 413 and 503 are conservative transport/API cases, not explicitly listed for every endpoint |
| `malformed/invalid.json.txt` | JSON operations | deterministic invalid JSON | test corpus | INFERRED | not claimed as a live response sample |

Content uses deterministic in-test MP4/WebM signature bytes because the Core validates containers,
not playability. The authoritative content contract is raw proxied bytes with provider media type;
`index=0` is canonical for frozen v0.1.

## Reviewed first-party sources

- https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-models
- https://openrouter.ai/docs/api/api-reference/video-generation/create-videos
- https://openrouter.ai/docs/api/api-reference/video-generation/get-videos
- https://openrouter.ai/docs/api/api-reference/video-generation/list-videos-content
- https://openrouter.ai/docs/guides/overview/multimodal/video-generation
- https://openrouter.ai/docs/app-attribution

## Update flow

First-party evidence change → contract review → fixture delta → tests reveal implementation impact
→ architecture/product review only when semantics conflict. Additive upstream features such as
`input_references`, `provider`, `callback_url`, webhooks, and additional attribution headers are
UPSTREAM_EXPANSION and do not expand frozen v0.1.
