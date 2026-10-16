# Security Policy

## Current posture

This release candidate contains Generate/Resume, capability projection, native media,
private S3-compatible staging and durable SQLite recovery. Default tests use synthetic
credentials, MockTransport and loopback infrastructure. Generate makes at most one
intentional paid submit; Resume never submits another Video generation. Ambiguity
never authorizes automatic resubmission. No telemetry service is included.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when it is available for the repository. Do not put
secrets, private workflows, generated media, complete headers, or exploit details in a public
issue. If private reporting is unavailable, open a non-sensitive issue asking the maintainer for
a private disclosure channel.

## Secret handling

- Never place an OpenRouter key in a workflow, node input, image/video metadata, fixture, log,
  exception, environment dump, source file, or bug report.
- Use a dedicated low-limit key for any separately approved live test.
- Never disable TLS verification or introduce a user-configurable production base URL.
- Never print complete request headers or enumerate the process environment.
- The interactive Settings connection uses OpenRouter's documented PKCE flow or a masked
  manual key field. Both persist the resulting access credential through explicitly selected
  keyring 25.7.0 OS backends only: Windows Credential Manager (`WinVaultKeyring`), macOS
  Keychain, or Linux Secret Service. No backend discovery, user-configured keyring plugin,
  plaintext file, runtime installation, or ordinary ComfyUI settings persistence is used.
  When the OS vault is unavailable, the UI explicitly reports session-only authentication.
  Resolution is environment > secure persistent interactive > session interactive > none.
  Settings, workflows, queue/history, browser storage, logs and receipts receive status only.
  OS account security is the trust boundary: other code running as the same OS account may
  access its vault. This does not provide isolation from malicious custom nodes or OS users
  sharing the same ComfyUI process. Use environment credentials for managed/headless installs.
  PKCE verifier, code and callback query are never persisted. Proposed credentials are
  catalogue-validated in request-local memory before replacing a stored credential.
- Connection validation performs only the authenticated model-catalogue GET. It never calls
  `/videos`, never retries a paid submit, and Disconnect removes persistent and session interactive
  values while leaving an environment credential active.

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
