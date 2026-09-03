# OpenRouter Video for ComfyUI

Open-source BYOK model-agnostic OpenRouter Video gateway for ComfyUI.

## Status

**PRE-ALPHA — Phase 3: Scaffold / Bootstrap. Product implementation has not started.**

This repository currently provides the engineering construction site: package layout,
development tooling, local mock/fault infrastructure, CI, security policy, and an isolated DEV
ComfyUI contract. It does not generate video and does not call OpenRouter.

## Product principles

- The user owns the OpenRouter account, API key, and wallet.
- The product is model-agnostic and preserves a billing-safe asynchronous lifecycle.
- The API key never enters a workflow or node input.
- The project owns no telemetry or analytics service.
- Official attribution is static project-level release metadata, never a user/install identifier.
- Polling, downloading, ambiguity, or attribution failure never authorizes another paid submit.

## Attribution state

The official title is **OpenRouter Video for ComfyUI** and the approved category is
`video-gen`. The canonical public Referer is intentionally unresolved during Scaffold. No
production value is present in source, workflow, environment configuration, or test fixtures.

The public repository URL,
`https://github.com/consumerexperience/ComfyUI-OpenRouter-Video`, is a documented candidate for
future Product Owner review. Repository creation does not promote it to production AppIdentity.

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
