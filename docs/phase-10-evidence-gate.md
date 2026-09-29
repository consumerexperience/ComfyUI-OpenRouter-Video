# Phase 10.0 Evidence Gate

- Status: `COMPLETE — ZERO COST`
- Observed: `2026-09-29T23:52:19.908440+03:00`
- Canonical baseline: `b492184f41492d37677a2dde9afdbe88666717a2`
- Paid Video submits: `0`
- Workflow queue executions: `0`

## Questions

This gate answers only the contract questions needed before Phase 10 implementation:

1. Does the current Video API accept image, video, and audio references?
2. What is the exact AUDIO reference wire shape?
3. What is proven for the exact model `bytedance/seedance-2.5`?
4. What reference limit, mixed-kind, edit, extend, and pricing semantics are proven?
5. Which current product projections are stale or incomplete?

## Evidence classification

| Evidence | Provenance | Result | Status |
| --- | --- | --- | --- |
| Canonical DEV session | live runtime proof | `RUNNING_HEALTHY`; source fingerprint current; credential present but undisclosed | `OBSERVED` |
| `GET localhost:8189/openrouter-video/v1/models` | zero-cost authenticated live proof routed through canonical DEV | HTTP 200; 29 selectable models; exact Seedance 2.5 ID present | `OBSERVED` |
| `GET localhost:8189/openrouter-video/v1/ui-capabilities` | current product runtime projection | HTTP 200; UI contract 3; Seedance 2.5 currently projects IMAGE/VIDEO, limit 50, mixed image/video | `OBSERVED — STALE FOR AUDIO` |
| OpenRouter Go SDK `a9684280824e2b3cfb1ffc1dfee9f56f53ee3109` | current official SDK generated from the OpenRouter schema | `InputReference` is the discriminated union `image_url | video_url | audio_url` | `CONFIRMED` |
| OpenRouter Seedance 2.5 model page | current exact-model first-party evidence | image/video/audio input, up to 50 references, editing, extension, first/last frames, optional generated audio | `CONFIRMED` |
| OpenRouter Seedance 2.5 review | current exact-model first-party evidence | video reference is used for edit or extend; mixed video+image example; video-input pricing differs from base generation | `CONFIRMED` |

## Exact protocol findings

### AUDIO reference wire shape

The official generated SDK defines `ContentPartAudio` as:

```json
{
  "type": "audio_url",
  "audio_url": {
    "url": "https://example.com/reference.mp3"
  }
}
```

The exact wire shape is therefore `CONFIRMED`. Phase 10 does not need to guess it, and AUDIO may be
added to `InputReferenceKind` without a `CONTRACT_SIGNAL_GAP` for this protocol question.

### Ordered heterogeneous references

`input_references` is an ordered array whose item schema is the three-way discriminated union.
OpenRouter's exact Seedance 2.5 documentation describes multimodal reference generation with image,
video, and audio assets; its first-party request example mixes video and image entries in one array.
Phase 10 may therefore preserve ordered heterogeneous entries and duplicate occurrences locally.
The product rule `minimum references = 2` and `minimum distinct media kinds = 2` is a local MMR2V
validation policy, not an upstream field.

### Seedance 2.5 exact-model capability record

| Primitive | Phase-10 value | Evidence status |
| --- | --- | --- |
| frame types | `FIRST_FRAME`, `LAST_FRAME` | `CONFIRMED` |
| reference kinds | `IMAGE`, `VIDEO`, `AUDIO` | `CONFIRMED` |
| maximum total references | `50` | `CONFIRMED — exact-model reported limit` |
| mixed reference kinds | `true` | `CONFIRMED` |
| edit intent | `true` | `CONFIRMED` |
| extend intent | `true` | `CONFIRMED` |
| seed | `true` | `CONFIRMED` |
| generated audio | `true` | `CONFIRMED`; independent of AUDIO input |
| duration | `4…30` seconds | `OBSERVED + CONFIRMED` |
| resolution | `480p`, `720p` | `OBSERVED + CONFIRMED` |
| aspect ratios | `16:9`, `4:3`, `1:1`, `3:4`, `9:16`, `21:9` | `OBSERVED + CONFIRMED` |

The count limit is exact-model documentation, not a structured count field returned by the generic
catalog contract. It remains a reviewed exact-ID overlay value and must not spread to another slug.

### Edit and extend

Exact-model documentation says a video reference can provide footage to edit or extend. The request
schema does not provide separate `edit`, `extend`, `source_role`, or `source_video` discriminators for
this route. Phase 10 therefore preserves `V2V_EDIT` and `V2V_EXTEND` as distinct local intents while
serializing Source Video as the first ordinary `video_url` entry in `input_references`.

The current generic schema also exposes optional `previous_job_id` continuation. Exact Seedance 2.5
support and the requested product contract for that field are not established here. It is classified
as `UPSTREAM_EXPANSION` and is not adopted by Phase 10.

## Pricing finding

Exact-model evidence distinguishes base video-token pricing from a lower video-input token rate.
It also says authorization for a request carrying a video reference may use a flat provisional amount
because input-footage duration is not known at authorization time, while final cost comes from reported
usage. Therefore:

- a non-video topology may show an estimate only when an exact matching SKU/formula is proven;
- any topology containing VIDEO, including Source Video, must show `ESTIMATE UNAVAILABLE` unless the
  estimator can prove an exact matching input-video SKU and all required structural inputs;
- AUDIO input must not be priced by analogy to `generate_audio`;
- no branch may infer pricing from an inference-method name, provider, family, or slug pattern.

## Conflict and drift disposition

`CONTRACT_DRIFT = PRESENT` for the current product projection: ADR-030 and UI contract 3 intentionally
exclude AUDIO and edit/extend intents, while current authoritative exact-model and protocol evidence
supports them. This is the controlled reason for ADR-031 and Phase 10.

The older generic API-reference wording that names only Seedance 2.0 is narrower than the current
official generated SDK and exact Seedance 2.5 sources. Exact-model evidence plus the newest generated
schema wins for the exact ID. No provider/family/name inference is permitted.

`UPSTREAM_EXPANSION = PRESENT` for `previous_job_id`, observability fields, and other generic request
fields outside the approved surface. They are recorded but not adopted.

## Sources

- <https://openrouter.ai/docs/api/api-reference/video-generation/create-videos>
- <https://openrouter.ai/docs/guides/overview/multimodal/video-generation>
- <https://openrouter.ai/bytedance/seedance-2.5>
- <https://openrouter.ai/blog/insights/seedance-2-5-review/>
- <https://github.com/OpenRouterTeam/go-sdk/blob/a9684280824e2b3cfb1ffc1dfee9f56f53ee3109/models/components/inputreference.go>
- <https://github.com/OpenRouterTeam/go-sdk/blob/a9684280824e2b3cfb1ffc1dfee9f56f53ee3109/models/components/contentpartaudio.go>
- <https://github.com/OpenRouterTeam/go-sdk/blob/a9684280824e2b3cfb1ffc1dfee9f56f53ee3109/models/components/videogenerationrequest.go>
