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

## X2 native VIDEO contract probe — preparation only (2026-10-02)

**Historical X2 status: BLOCKED before paid authorization. No POST was made. VIDEO transport
remains unimplemented.** X2a below supersedes the preflight dependencies, not the transport
evidence gap. This is a proposed one-shot contract test, not a claim of data-URL support.

- Exact question: will dedicated `POST /api/v1/videos` accept a local MP4 encoded as
  `data:video/mp4;base64,...` in `input_references[0].video_url.url` for exact model
  `bytedance/seedance-2.5`? The [current OpenAPI](https://openrouter.ai/openapi.json) defines
  the typed VIDEO reference and a `string` URL, but neither a data-URI allowance nor a size
  bound. The [first-party Seedance 2.5 review](https://openrouter.ai/blog/insights/seedance-2-5-review/)
  shows an HTTPS VIDEO example, not a data URL.
- Existing synthetic, nonsensitive fixture: `tests/live/fixtures/phase9/motion-reference.mp4`;
  H.264/yuv420p MP4, 854x480, 24 fps, 2.000 s, no audio stream, `video/mp4`, 394,950 bytes,
  SHA-256 `e6009ff03feb01893c4dcc5a77d564e6af23066c4305dea1460d48696f8f448b`.
  Reuse the existing `prompts/video-reference.txt`; no fixture or prompt is created or changed.
- Proposed request: `model=bytedance/seedance-2.5`, local intent VR2V, one VIDEO reference,
  prompt from that fixture, `duration=4`, `resolution=480p`, `aspect_ratio=16:9`,
  `generate_audio=false`; no `frame_images`, provider passthrough, source-role field, method
  field, session/user identity, callback, or second reference.
- Proposed wire shape (bytes intentionally redacted):
  `{"model":"bytedance/seedance-2.5","prompt":"<existing synthetic prompt>","input_references":[{"type":"video_url","video_url":{"url":"data:video/mp4;base64,<REDACTED>"}}],"duration":4,"resolution":"480p","aspect_ratio":"16:9","generate_audio":false}`.
  Source 394,950 bytes -> base64 526,600 characters -> data URL 526,622 characters ->
  compact UTF-8 JSON 527,087 bytes using the existing prompt (trailing newline trimmed).
- Public unauthenticated zero-cost `GET https://openrouter.ai/api/v1/videos/models` returned
  HTTP 200 and the exact-model row on 2026-10-02: durations 4–30, 480p/720p, 16:9,
  `pricing_skus.video_tokens_with_video_input=0.0000064` USD per token. The first-party
  review calculates `(width * height * 24 * duration) / 1024`; the 4 s, 854x480 output
  component is 38,430 tokens, approximately USD 0.245952. A 2 s input at the same raster
  would add approximately USD 0.122976 **if** metered identically; this is an illustration,
  not a validated total estimate. The review states that a VIDEO-reference request is
  authorized with a flat USD 2 hold, but its final charge uses provider-reported token count
  after execution. The hold is **not** a documented hard maximum charge. No sufficiently
  defensible conservative maximum charge or independently verified hard key/campaign cap
  is available here.
- Canonical DEV `127.0.0.1:8189` probe returned `RUNNING_STALE` with
  `FRONTEND_BACKEND_MISMATCH` (backend UI contract 4, expected 3). Per X2 no restart was
  requested; no authenticated local catalogue or credit read was attempted.
- No existing paid VIDEO data-URL one-shot runner was found in the workspace. The production
  Core path still rejects native VIDEO data URLs by design, so it must not be repurposed or
  weakened for this probe. A bounded, non-product one-shot runner and its dry-run inspection
  would be required before any later paid authorization.
- If later unblocked and immediately approved for one exact paid POST: re-probe canonical
  DEV identity and current exact-model row, verify a hard campaign/key spend cap and the
  Owner-approved maximum, verify fixture hash and exact serialized size locally, then use
  one controlled submit path with automatic redirects/retries disabled. Record whether the
  one POST was attempted before any network ambiguity. HTTP 202 with `id`/`polling_url`
  means accepted; poll that *same* job by GET only. A complete explicit 4xx response without
  job ID is a definite request rejection (record sanitized code/message). Timeout,
  connection loss after dispatch, 5xx, or any uncertain response is `SUBMISSION_UNKNOWN`:
  stop, no second POST, no alternate model or payload. Local preflight failure means zero
  POST. A returned job can fail later without authorizing a resubmit.

At the original X2 checkpoint, the experiment was blocked at the cost-cap/readiness gate.
X2a below replaces that disposition. The existing HTTPS VIDEO helper path is unchanged;
native VIDEO/AUDIO remain probe-gated.

## X2a final preflight — isolated upstream experiment (2026-10-02)

- Canonical Comfy DEV `8189` is **NOT REQUIRED** for this isolated upstream contract probe.
  The earlier `RUNNING_STALE` observation is unrelated deferred runtime state. No DEV or PROD
  process was restarted, recovered, or touched for X2a.
- The [OpenRouter current-key endpoint](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)
  exposes `limit`, `limit_remaining`, `usage`, `limit_reset`, and the management-key flag to
  the ordinary inference key. The Owner's financial strategy is a *fresh dedicated X2 key*
  with USD 2.00 per-key credit limit, zero prior usage, at least USD 2.00 remaining, no reset,
  and no management/provisioning role. `GET /api/v1/key` must prove these facts immediately
  before any later paid submit. A USD 2 authorization hold is not a cost estimate; the
  per-key limit is the experiment boundary. No key was supplied or checked in X2a.
- Isolated runner: `tests/manual/x2_video_data_url_probe.py`; offline dry-run is the default.
  It pins the existing MP4 size/hash and prompt hash, serializes exactly one request body,
  redacts the data URL/key/body, and prints only sanitized evidence. `--key-preflight` uses
  masked interactive input and performs only the key GET. A later `--post-once` requires
  separate immediate Owner authorization, rechecks the key, and contains one POST call with
  redirects disabled and zero transport/application retries. 429, 5xx, timeout, and network
  ambiguity never trigger another POST. No same-job polling is included in this runner.
- Observed offline dry-run: endpoint `POST https://openrouter.ai/api/v1/videos`; model
  `bytedance/seedance-2.5`; VR2V local intent; 4 s / 480p / 16:9 / silent; one VIDEO reference;
  MIME `video/mp4`; fixture SHA-256
  `e6009ff03feb01893c4dcc5a77d564e6af23066c4305dea1460d48696f8f448b`;
  source 394,950 bytes; base64 526,600 characters; compact JSON 527,087 UTF-8 bytes;
  **POST attempts 0**. Focused offline tests cover key-limit rejection, redirect/no-retry,
  429/5xx, 202 job ID, and network ambiguity.
- Final authorization status: **BLOCKED until the Owner configures and locally checks the
  dedicated key**, then separately authorizes exactly one X2 paid POST. The current prompt
  grants no paid authority. Native VIDEO remains **EVIDENCE GAP / NOT IMPLEMENTED**.

### X2 key-check observation (2026-10-02)

Product Owner's local `--key-preflight` returned `key_get_http_400` with
`POST_ATTEMPT_COUNT=0`. This is an **OBSERVED, owner-reported** upstream rejection, not proof
of an invalid key or of a Video transport result. The [current OpenRouter key endpoint
reference](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key)
documents the GET path and 200/401/500 responses, but not this 400 case. The isolated runner
now rejects obvious hidden-input paste mistakes before network I/O and classifies only the
HTTP error's non-secret response shape; it never prints the key, body, or raw remote message.
An anonymous control GET returned 401, and a GET with an explicitly synthetic invalid token
also returned 401; neither reproduced the Owner's 400. The reason for 400 is therefore
**UNKNOWN**, not a proven invalid-key diagnosis.
X2 paid authorization remains blocked until a valid, capped key preflight is observed.
