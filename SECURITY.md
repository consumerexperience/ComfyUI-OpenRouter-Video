# Security Policy

## Current posture

This project is pre-alpha. Phase 4 implements the headless request-policy and HTTP transport
boundary, but no endpoint client, paid submission, lifecycle, persistence, media handling, or
ComfyUI product nodes exist yet. Default tests use only synthetic credentials, MockTransport, and
loopback infrastructure.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when it is available for the repository. Do not put
secrets, private workflows, generated media, complete headers, or exploit details in a public
issue. If private reporting is unavailable, open a non-sensitive issue asking the maintainer for
a private disclosure channel.

## Secret handling

- Never place an OpenRouter key in a workflow, node input, image/video metadata, fixture, log,
  exception, environment dump, source file, or bug report.
- Use a dedicated low-limit key only in a future explicitly approved live test.
- Never disable TLS verification or introduce a user-configurable production base URL.
- Never print complete request headers or enumerate the process environment.

## Network and attribution boundary

Authorization and OpenRouter attribution are composed only after the destination has been proven
to be HTTPS `openrouter.ai` under `/api/v1`. The production transport verifies TLS, does not follow
redirects, does not inherit ambient proxies, and performs zero automatic connection retries.
Transport defensively revalidates policy-prepared requests before sending. Neither header class is
forwarded to external media hosts.

The official canonical Referer is the immutable source-level value
`https://github.com/consumerexperience/ComfyUI-OpenRouter-Video`. Phase 4 retains an unmistakable
`.invalid` identity only for synthetic tests. Production identity has no workflow, environment,
runtime, user, device, installation, or session override.

## Supply chain

Dependencies are reviewed, CI actions are pinned to immutable commit SHAs, Dependabot monitors
Python and GitHub Actions dependencies, and CodeQL plus dependency auditing are part of the
security baseline. Runtime package installation, downloaded executables, obfuscation, hidden
telemetry, and `eval`/`exec` configuration are prohibited.
