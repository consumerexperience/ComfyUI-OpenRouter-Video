# Security Policy

## Current posture

This project is pre-alpha Scaffold. Product networking, credential access, persistence, media
handling, and ComfyUI product nodes do not exist yet.

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

Future Authorization and OpenRouter attribution headers may leave the process only for the
validated canonical OpenRouter origin. Redirects are not followed by default. Neither header
class may be forwarded to external media hosts.

## Supply chain

Dependencies are reviewed, CI actions are pinned to immutable commit SHAs, Dependabot monitors
Python and GitHub Actions dependencies, and CodeQL plus dependency auditing are part of the
security baseline. Runtime package installation, downloaded executables, obfuscation, hidden
telemetry, and `eval`/`exec` configuration are prohibited.
