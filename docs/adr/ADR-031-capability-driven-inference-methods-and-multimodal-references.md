# ADR-031 — Capability-Driven Inference Methods and Multimodal References

- Status: `ACCEPTED`
- Date: `2026-09-30`
- Classification: `D2 — ARCHITECTURE / PRODUCT CAPABILITY POLICY`
- Authority: explicit Product Owner decision
- Supersedes: selected scope restrictions in ADR-030; ADR-030 remains historical and otherwise valid

## Context

ADR-030 established an exact-ID evidence overlay and deliberately limited the v0.1 product to IMAGE
and VIDEO references. It also kept AUDIO, Edit, and Extend outside the product. Current official
OpenRouter schema and exact-model evidence now confirms that `bytedance/seedance-2.5` accepts IMAGE,
VIDEO, and AUDIO references, supports up to 50 reference assets, and is intended for video editing
and video extension. The exact AUDIO wire shape is confirmed in the official generated SDK.

A user-facing inference method is useful product semantics, but a manually maintained method list
would become a second capability truth and could drift from the evidence-backed primitives.

## Decision

### Evidence precedence remains unchanged

Capability resolution remains:

1. explicit machine-readable Level A exact-model data;
2. reviewed exact-ID first-party evidence overlay;
3. generic protocol evidence;
4. fail closed.

Level A wins when it explicitly answers the same question. Explicit conflict produces `CONFLICT` and
blocks only the affected method. Provider, family, prefix, regex, display-name, example, and sibling
model inference remain forbidden.

### Primitive capabilities are the only capability truth

The effective model record may contain evidence-backed primitives such as:

```text
supported_frame_types
supported_reference_kinds
max_reference_count
supports_mixed_reference_kinds
supports_edit
supports_extend
supports_seed
supports_generate_audio
supported_durations
supported_resolutions
supported_aspect_ratios
supported_sizes
```

Every primitive carries provenance and a resolution status. No independent mutable
`supported_inference_methods` capability layer is permitted.

### Product methods are deterministic derivations

The product registry derives method readiness from primitives:

| Method | READY derivation |
| --- | --- |
| `T2V` | base video generation contract is ready |
| `I2V` | `FIRST_FRAME` is ready |
| `FLF2V` | `FIRST_FRAME` and `LAST_FRAME` are ready |
| `IR2V` | IMAGE reference is ready and limit is at least 1 |
| `MI2V` | IMAGE reference is ready and limit is at least 2 |
| `VR2V` | VIDEO reference is ready and limit is at least 1 |
| `AR2V` | AUDIO reference and its wire schema are ready; limit is at least 1 |
| `MMR2V` | at least two reference kinds are ready, mixed kinds are ready, and limit is at least 2 |
| `V2V_EDIT` | VIDEO reference and explicit exact-model edit support are ready |
| `V2V_EXTEND` | VIDEO reference and explicit exact-model extend support are ready |

Any required primitive in `CAPABILITY_SIGNAL_GAP` or `CONFLICT` makes the derived method non-READY.
The UI lists only READY methods for a normal selection. A persisted method that becomes incompatible
remains visible in a blocked state so that user intent and links are not destroyed.

For the exact model `bytedance/seedance-2.5`, all ten methods above are READY. The product preference
policy is `preferred_inference_method = MI2V`. Preference is not an upstream capability and applies
only to a genuinely new node after its first model selection.

### AUDIO and generated audio are independent

`InputReferenceKind` expands to `IMAGE | VIDEO | AUDIO`. `AR2V` means AUDIO is input guidance.
`generate_audio=true` requests audio in the output. Neither implies or toggles the other.

### Local intent does not leak upstream

`GenerationRequest.inference_method` is persisted, migrated, fingerprinted, and validated locally.
It is never serialized to OpenRouter. The request builder must never emit:

```text
method
inference_method
source_role
source_video
```

Only confirmed OpenRouter fields are serialized, including `frame_images`, `input_references`,
`prompt`, `generate_audio`, geometry, duration, and seed.

### Source Video is a local role

`V2V_EDIT` and `V2V_EXTEND` have a required local `Source Video` role. It is always first in the
ordered `input_references` array, counts toward the exact-model limit, is never silently removed, and
uses the ordinary confirmed `video_url` wire object. Optional references follow it in exact user order.
`VR2V` remains distinct because its video inputs are guidance references, not a source-to-transform
intent.

### Mixed multimodal topology

`MMR2V` requires at least two total references and at least two distinct kinds from IMAGE, VIDEO, and
AUDIO. Ordered combinations and duplicate occurrences are preserved exactly up to the model limit.

### Recovery, billing, and lifecycle remain one system

There is still one Generate lifecycle and one paid-submit authority. Adding methods does not add a
second submission path, automatic retry, provider passthrough, or method-specific transport. Resume
remains submit-incapable. Ambiguous submit never grants another POST. Durable Core state and the
existing recovery architecture remain authoritative.

### Fingerprint v3

`request_fingerprint_v1` and `request_fingerprint_v2` remain immutable. New Phase-10 Generate
operations use `request_fingerprint_v3`, containing structural intent only:

```text
schema = 3
model
inference_method
duration
resolution
aspect_ratio
size
seed
generate_audio
prompt_present
first_frame_present
last_frame_present
source_video_present
input_reference_count
input_reference_kinds (ordered)
```

It never contains prompt text, media URLs, credentials, raw media, workflow identity, user identity,
or AppIdentity. Reusing an `operation_id` with different v3 intent is a conservative conflict and
never grants a second submit.

## Consequences

- ADR-030's exact-ID overlay, precedence, and fail-closed architecture remain in force.
- ADR-030's statements that AUDIO is outside the product and that video references cannot express
  Edit/Extend are superseded.
- Seedance 2.5 gains AUDIO, mixed multimodal, and two separate local V2V intents without inventing
  upstream fields.
- Public HTTPS URL helper nodes remain the proven transport. Native local IMAGE/VIDEO/AUDIO transport
  is not claimed without a separate contract.
- The current UI projection must advance from contract 3 during implementation; until then it is a
  known Phase-10 implementation gap, not permission to bypass Core.

## Evidence

- [Phase 10.0 Evidence Gate](../phase-10-evidence-gate.md)
- [ADR-030 — Evidence-Backed Capability Overlay](ADR-030-evidence-backed-capability-overlay.md)
- <https://openrouter.ai/bytedance/seedance-2.5>
- <https://openrouter.ai/blog/insights/seedance-2-5-review/>
