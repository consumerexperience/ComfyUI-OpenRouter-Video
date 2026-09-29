# OpenRouter Video for ComfyUI

Open-source BYOK model-agnostic OpenRouter Video gateway for ComfyUI.

## Status

**PRE-ALPHA — Phase 10 pre-implementation visual acceptance gate; paid validation is not authorized.**

The headless core now contains typed Video API contracts, capability discovery and bounded cache,
pre-submit validation, a durable SQLite lifecycle, one-attempt Generate, submit-incapable Resume,
bounded polling, and durable MP4/WebM download. The Phase-4 origin-bound request policy still owns
all authentication, attribution, destination, redirect, TLS, and zero-transport-retry controls.

The canonical Phase-9 baseline exposes Generate, submit-incapable Resume, public-HTTPS image/video
reference nodes, direct ordered Autogrow reference inputs, and a legacy Phase-8 collection node.
T2V and model-proven first/last-frame modes remain available. The exact-ID evidence overlay accepted
in ADR-030 enables multi-image, video, and mixed image/video reference modes for
`bytedance/seedance-2.5`; unresolved models still fail with `CAPABILITY_SIGNAL_GAP` before submit
authority. Prompt remains required for every Generate call.

Phase 10 is approved for capability-driven local inference methods and Seedance 2.5 AUDIO/Edit/Extend
expansion, but product implementation is stopped pending Product Owner acceptance of the refined
Direction 3 visual specification. See the [canonical Phase-10 plan](docs/phase-10-capability-driven-inference-methods-plan.md),
[ADR-031](docs/adr/ADR-031-capability-driven-inference-methods-and-multimodal-references.md), and the
[active checkpoint](docs/active-execution-checkpoint.md).

## Product principles

- The user owns the OpenRouter account, API key, and wallet.
- The product is model-agnostic and preserves a billing-safe asynchronous lifecycle.
- The API key never enters a workflow or node input.
- The project owns no telemetry or analytics service.
- Official attribution is static project-level release metadata, never a user/install identifier.
- Polling, downloading, ambiguity, or attribution failure never authorizes another paid submit.

## Attribution state

The Product Owner has frozen the official release identity as:

- `HTTP-Referer`: `https://github.com/consumerexperience/ComfyUI-OpenRouter-Video`
- `X-OpenRouter-Title`: `OpenRouter Video for ComfyUI`
- `X-OpenRouter-Categories`: `video-gen`

This identity is immutable source-level project metadata. It cannot be changed through a workflow,
environment variable, runtime preference, user, device, installation, or session value.

## Headless recovery identity

- `job_id` is authoritative remote generation identity after acceptance.
- `operation_id` is authoritative local logical-operation identity.
- `request_fingerprint` is a versioned, privacy-preserving advisory checksum and never grants
  submit, Resume, deduplication, or idempotency authority.

See [Headless Core II](docs/headless-core-ii.md),
[ADR-028](docs/adr/ADR-028-local-recovery-identity-and-request-fingerprint.md),
[ADR-029](docs/adr/ADR-029-durable-definite-submit-rejection.md),
[ADR-030](docs/adr/ADR-030-evidence-backed-capability-overlay.md), and
[ADR-031](docs/adr/ADR-031-capability-driven-inference-methods-and-multimodal-references.md).

## ComfyUI compatibility

The product uses capability-first host compatibility. `v0.34.3` is the release-blocking historical
anchor and `v0.37.0` is the frozen release-blocking current target; `v0.35.0` and `v0.36.0` are
intermediate regression probes, not unconditional support commitments. Missing required V3 host
capabilities fail visibly. Production imports only `comfy_api.v0_0_2`; because that adapter
delegates into mutable `comfy_api.latest`, the numbered import alone is not treated as a stable
contract. See the [adapter contract](docs/comfyui-adapter.md).

## Security warning

Never place an OpenRouter API key in a workflow, node input, fixture, bug report, log, or source
file. See [SECURITY.md](SECURITY.md).

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/development.md](docs/development.md), and
[docs/testing.md](docs/testing.md). Canonical project documents remain outside this repository;
their authority and locations are indexed in [docs/canonical-sources.md](docs/canonical-sources.md).

## License

Original project code is licensed under the MIT License. ComfyUI is studied as a GPL-3.0
reference and host interface; its implementation is not copied into this project.
