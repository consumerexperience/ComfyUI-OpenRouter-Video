# Repository Engineering Rules

## Architecture

- Core must never import ComfyUI; the Comfy adapter remains thin.
- Raw HTTP stays behind the OpenRouterVideoClient / RequestPolicy / Transport boundary.
- Provider-specific core behavior requires architecture review.

## Billing

- Never automatically retry the paid video submit POST.
- Resume never receives submit capability.
- Poll/download retries operate only on an existing job ID.
- Poll failure is not generation failure.
- Corrupt or contradictory durable state never grants submit permission.
- A uniqueness conflict is a recovery signal, never permission to retry submit.
- `request_fingerprint` is advisory and never an idempotency or recovery authority.

## Secrets and network

- The API key never becomes workflow/node input and is never logged.
- Never dump environment variables, disable TLS, or accept an arbitrary production base URL.
- Authorization and attribution are sent only to the validated canonical OpenRouter origin.

## Attribution

- Official attribution is static release identity, not runtime configuration.
- Use `X-OpenRouter-Title`; never add user/install/device/session/workflow identity.
- Never forward authentication or attribution to external hosts.
- Preserve the exact official identity: Referer
  `https://github.com/consumerexperience/ComfyUI-OpenRouter-Video`, title
  `OpenRouter Video for ComfyUI`, and category `video-gen`.
- Any canonical identity change requires explicit Product Owner and architecture/release review.

## Testing and dependencies

- Default tests cost zero; live tests are excluded and require immediate human approval.
- Contract fixtures are reviewed evidence snapshots, not live or permanent API truth.
- Harness execution may use only MockTransport or explicit loopback with synthetic credentials.
- Testability never authorizes production destination, header, credential, or identity overrides.
- No telemetry/analytics SDK, runtime pip installation, or unreviewed runtime dependency.

## Agent permissions

- Never access production ComfyUI or production credentials.
- Never run paid inference, publish a release, or change canonical project identity.
- Preserve user work; no hard reset, force push, destructive clean, or deletion of unknown files.

## Verification commands

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m build
python -m pip_audit
```
