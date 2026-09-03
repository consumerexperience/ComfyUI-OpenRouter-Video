# OpenRouter Video for ComfyUI

Open-source BYOK model-agnostic OpenRouter Video gateway for ComfyUI.

## Status

**PRE-ALPHA — Phase 4: Safe boundary implemented with frozen canonical identity.**

The headless core now contains a policy-prepared, origin-bound OpenRouter HTTP transport. It
validates the canonical destination before resolving a credential, composes static application
attribution centrally, disables redirects and ambient proxy inheritance, and performs zero
automatic transport retries. All behavior is proven with synthetic fixtures and local transports.

The extension still does not generate video, expose product nodes, call OpenRouter endpoints, or
implement lifecycle, persistence, model discovery, polling, Resume, or media download behavior.

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
environment variable, runtime preference, user, device, installation, or session value. Phase 4
engineering is complete; canonical delivery still requires the feature PR, required CI and CodeQL,
human protected merge, and a final `main` read-back.

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
