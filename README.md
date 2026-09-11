# OpenRouter Video for ComfyUI

Open-source BYOK model-agnostic OpenRouter Video gateway for ComfyUI.

## Status

**PRE-ALPHA — Phase 6: ComfyUI adapter implemented on the feature branch.**

The headless core now contains typed Video API contracts, capability discovery and bounded cache,
pre-submit validation, a durable SQLite lifecycle, one-attempt Generate, submit-incapable Resume,
bounded polling, and durable MP4/WebM download. The Phase-4 origin-bound request policy still owns
all authentication, attribution, destination, redirect, TLS, and zero-transport-retry controls.

The pinned ComfyUI extension exposes exactly two V3 nodes: Generate and submit-incapable Resume.
They bridge the existing Headless Core to native file-backed `VIDEO`, keep durable recovery state
in the Comfy user directory, and fetch the model combo through a local capability route. Phase 6
verification makes no live OpenRouter calls, accesses no production credential, and spends no
credits.

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

See [Headless Core II](docs/headless-core-ii.md), [ADR-028](docs/adr/ADR-028-local-recovery-identity-and-request-fingerprint.md),
and [ADR-029](docs/adr/ADR-029-durable-definite-submit-rejection.md).

## ComfyUI compatibility

Phase 6 supports exactly ComfyUI `v0.34.3` at commit
`87465b8f1f64a27a46f16f22b13b410494dca66d` through `comfy_api.v0_0_2`. Other versions are
unsupported and API mismatches fail closed; there is no fallback to `comfy_api.latest`. See the
[adapter contract](docs/comfyui-adapter.md).

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
