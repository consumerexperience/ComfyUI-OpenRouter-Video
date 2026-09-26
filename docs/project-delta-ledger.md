# Project Delta Ledger

## Phase 8

| Delta | Evidence | Classification | Product treatment |
| --- | --- | --- | --- |
| `frame_images` uses typed nested media objects rather than flat `{frame_type,url}` objects | Current first-party video-generation protocol | `CONTRACT_DRIFT — CONFIRMED` | Production serializer and fixtures updated. |
| Typed image/video `input_references` and mixed collections are documented | First-party generic and model-specific documentation | `UPSTREAM_EXPANSION — CONFIRMED` | Domain and adapter support added; runtime submit remains evidence-gated. |
| `/videos/models` exposes no direct reference kind/count/mix or prompt-optional signal | Sanitized live GET on 2026-09-26 | `OBSERVED` | Reference modes return `CAPABILITY_SIGNAL_GAP` before submit. |
| `generate_audio=false` produced an AAC track in the controlled Phase-7 result | Phase-7 product observation | `UNSTABLE` | Preserve the transport control and default `false`; do not advertise generated-audio or promise silent output. |

Protocol capability is not model-specific capability. Upstream capability is not necessarily
runtime-resolvable capability. No provider/model/slug inference is authorized.
