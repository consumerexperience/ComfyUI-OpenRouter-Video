# Project Delta Ledger

## Phase 8

| Delta | Evidence | Classification | Product treatment |
| --- | --- | --- | --- |
| `frame_images` uses typed nested media objects rather than flat `{frame_type,url}` objects | Current first-party video-generation protocol | `CONTRACT_DRIFT — CONFIRMED` | Production serializer and fixtures updated. |
| Typed image/video `input_references` and mixed collections are documented | First-party generic and model-specific documentation | `UPSTREAM_EXPANSION — CONFIRMED` | Domain and adapter support added; runtime submit remains evidence-gated. |
| `/videos/models` exposes no direct reference kind/count/mix or prompt-optional signal | Sanitized live GET on 2026-09-26 | `OBSERVED` | Unknown models return `CAPABILITY_SIGNAL_GAP`; approved exact-ID overlay data may fill only absent fields. |
| First-party Seedance 2.5 evidence proves image/video kinds, a reported limit of 50, and a mixed request while Level A remains silent | OpenRouter Seedance 2.5 review rechecked 2026-09-26 plus Product Owner decision | `ADR-030 — ACCEPTED` | Exact-ID overlay fills only absent fields; Level A wins and conflicts fail closed. |
| First-party prompt language conflicts, while prompt omission is not required by the product surface | Current first-party protocol/model documentation plus Product Owner decision | `DEFERRED` | Phase-8 v0.1 requires a non-empty prompt for every Generate operation. |
| `generate_audio=false` produced an AAC track in the controlled Phase-7 result | Phase-7 product observation | `UNSTABLE` | Preserve the transport control and default `false`; do not advertise generated-audio or promise silent output. |

Protocol capability is not model-specific capability. Upstream capability is not necessarily
runtime-resolvable capability. ADR-030 makes reviewed exact-ID capability data runtime-resolvable;
provider, family, name, pattern, and cross-model inference remain forbidden.
