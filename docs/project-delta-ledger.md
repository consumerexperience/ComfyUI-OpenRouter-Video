# Project Delta Ledger

## Phase 9

| Delta | Evidence | Classification | Product treatment |
| --- | --- | --- | --- |
| `comfy_api.v0_0_2` delegates into mutable latest implementation | Frozen Comfy matrix source/runtime probes | `COMPATIBILITY_RISK` | Capability-first host probes; no exact-version allowlist. Contract drift is not confirmed. |
| Catalogue contains option and pricing values beyond static documentation, including observed `768p` | Read-only snapshot at `2026-09-26T19:54:44.1434713Z` | `UPSTREAM_EXPANSION` | Generic normalized projection; documented vocabulary is not a whitelist. |
| Pricing has 37 keys and 20 distinct shapes in the planning snapshot | Same read-only snapshot | `PRICING_VARIABILITY` | Typed Core evidence; estimate only explicitly supported generic semantics, otherwise unavailable. |
| New prompt-optional/passthrough/product modes remain visible upstream | Current upstream evidence | `PRODUCT_DELTA` | Record only; Phase-9 v0.1 scope remains frozen. |
| Native V3 schema alone does not reliably refresh the complete model-dependent option surface on both release-blocking hosts | Isolated real-browser probes on ComfyUI `v0.34.3` / frontend `1.49.6` and ComfyUI `v0.37.0` / frontend `1.52.7` | `EVIDENCE-REQUIRED COMPATIBILITY ADAPTATION` | Retain the minimal presentation-only helper; Core remains capability and submit authority. |
| Remote combo refresh could reset a serialized model, reference-link changes could leave an old estimate visible, and successive invalidations could hide an earlier paid-intent disclosure | Real save/reload, model-switch and reference-link browser scenarios | `PHASE-9 BUG FIX` | Preserve the saved model after refresh, invalidate estimates on link changes, and accumulate visible reset disclosures. |

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
