# Secure credential persistence: first-party audit and storage decision

Baseline: `796697ad068e4c31aa0cc8ba9d72c123c5e8b78b`.
Scope: persist existing interactive authentication. Naming, OAuth protocol,
generation/Resume, capabilities, geometry and attribution are protected.

## Official ComfyUI facility audit (2026-10-16)

CONFIRMED from official ComfyUI_frontend commit
`430ad53827f196aafc1c16c4ec14166ef6126b12`:

- [secretsApi.ts](https://github.com/Comfy-Org/ComfyUI_frontend/blob/430ad53827f196aafc1c16c4ec14166ef6126b12/src/platform/secrets/api/secretsApi.ts)
  uses GET/POST `/secrets`, GET `/secrets/providers`, PATCH/DELETE `/secrets/{id}`.
- [types.ts](https://github.com/Comfy-Org/ComfyUI_frontend/blob/430ad53827f196aafc1c16c4ec14166ef6126b12/src/platform/secrets/types.ts)
  documents metadata-only responses: stored values are not returned.
- [secrets domain](https://github.com/Comfy-Org/ComfyUI_frontend/blob/430ad53827f196aafc1c16c4ec14166ef6126b12/docs/architecture/domains/records/secrets.domain.json)
  calls this **Cloud user secrets**, with empty publicEntryPoints.
- UI wording promises encryption. The reviewed public frontend does not prove the
  Cloud backend's encryption algorithm, key ownership, at-rest storage, or a
  backend-only retrieval API usable by arbitrary local custom nodes: UNKNOWN.
- The official self-hosted [ComfyUI tree](https://github.com/Comfy-Org/ComfyUI/tree/e087d8f6cb7c6cdb11b59dc7c9bf17c79f8d877d)
  has no credential/secret-store source path. No supported equivalent integration
  for Desktop/portable custom nodes was established. A Cloud settings UI is not
  sufficient evidence of a local credential API.

Decision: COMFYUI_NATIVE_CREDENTIAL_STORE = NOT_AVAILABLE for this local custom-node
integration, not a claim that the Cloud product lacks secrets storage.

## Selected backend

`keyring==25.7.0`, with direct construction of only these implementations:

- Windows: `keyring.backends.Windows.WinVaultKeyring` (Windows Credential Manager).
- macOS: `keyring.backends.macOS.Keyring` (macOS Keychain).
- Linux: `keyring.backends.SecretService.Keyring` (desktop Secret Service).

Primary sources: [keyring](https://github.com/jaraco/keyring),
[Windows backend](https://github.com/jaraco/keyring/blob/v25.7.0/keyring/backends/Windows.py),
[macOS backend](https://github.com/jaraco/keyring/blob/v25.7.0/keyring/backends/macOS/__init__.py),
[Secret Service backend](https://github.com/jaraco/keyring/blob/v25.7.0/keyring/backends/SecretService.py).

No automatic backend selection, plugin discovery, KEYRING_PROPERTY_* overrides, file backend, ordinary settings,
plaintext fallback, CLI secret arguments or runtime pip installation. Installation
adds keyring and its small platform-specific Python dependencies; Windows uses
pywin32-ctypes. Linux requires an available unlocked OS Secret Service. Missing or
unavailable vault support falls back explicitly to process-only storage. macOS and
Linux backend runtime availability remains platform-dependent; only Windows was
available for a real vault experiment in this task.

The fixed service/account is local storage identity, not attribution or telemetry.
Protection is at rest under the signed-in OS user. It is not protection from
malicious custom nodes or programs already running as that same OS user. A shared
ComfyUI process shares one interactive connection; managed deployments use env.

## Credential lifecycle

Resolution: environment > persistent interactive > session interactive > none.
Both OAuth and manual-key handlers validate a proposed credential with catalogue
GET in request-local memory, then persist only the access credential. No PKCE
verifier, temporary code or callback query is persisted. Failed validation preserves
the previous connection. Successful replacement overwrites the same entry.

Disconnect deletes vault + session credential and verifies removal, preserving
`OPENROUTER_API_KEY`. A failed deletion is a sanitized error, never success.
Lookup/corruption faults become attention state without crashing the host.
Settings and frontend receive only connection status/source/persistence metadata.

## Evidence limits

The real Windows-vault probe uses a unique TEST-ONLY service and synthetic value,
not the product entry or provider credential. Save and restore use separate Python
processes; cleanup verifies the test entry was removed. No network or paid submit.

Canonical DEV probe returned RUNNING_STALE for the required connection route
(HTTP 404). The governed runtime points at a different, dirty checkout, not this
candidate worktree. No source overlay, junction replacement, secondary ComfyUI,
restart of unrelated code, or owner credential access is justified. Classic/Nodes2
live smoke remains NOT_RUN. Browser fixture screenshots prove connection UI states
only, not canonical runtime, real OAuth consent or live catalogue validity.

Connection validation uses an uncached runtime client GET; existing catalogue cache/LKG must never approve a proposed key. All pre-existing runtime methods remain AST-identical.

## Verification (local, 2026-10-16)

- Python: 478 passed, 3 skipped (unmaterialized third-party media only).
- Frontend: 144 passed, including unchanged node/renderer/serialization source
  outside connection UI and explicit persistent/environment/session/attention labels.
- Builder: 75 passed, 62 subtests passed; plugin files were not changed.
- Product Contract Guard: PASS, 5 authorized source deltas, 0 unauthorized deltas,
  bound to the exact 796697a predecessor and this task's narrow delta.
- Existing runtime methods: AST-identical; only validate_connection was added.
- Uncached validation regression: fresh empty cache cannot approve a candidate;
  runtime-thread request carries request-local synthetic key in exactly one GET.
- Windows Credential Manager: separate-process save/restore/delete PASS using
  a unique synthetic entry; the real product credential entry was not accessed.
- Clean wheel install, environment-only predecessor wheel upgrade and pip check:
  PASS in a separate test venv; imports/env resolution do not open the OS vault.
- Source distribution + wheel build and artifact secret/path inspection: PASS.
- Ruff lint: PASS. Changed/new production code Mypy: PASS. Full Mypy still has
  five pre-existing unused-ignore errors in native_media.py, image.py and
  native_image_bridge_probe.py. Global format check retains two pre-existing
  files (oauth.py and test_oauth.py); this pass does not redesign/reformat OAuth.
- CI baseline/delta paths are updated to this exact candidate comparison;
  local CI contract tests PASS. Remote CI and cross-OS matrix were not run.
- Six real-browser screenshots render the production connection UI in offline
  fixtures; no secret was entered. Files: output/playwright/credential-persistence.
  These are not live Classic/Nodes2 acceptance or real provider consent proof.
- Live Classic/Nodes2: NOT_RUN due canonical DEV source mismatch / missing route.
  The runtime source is a separate dirty checkout; no overlay or restart was made.
- Dependency audit: pip_audit is unavailable in the current interpreter. Direct
  PyPI advisory lookup was incomplete due network errors; no full audit PASS claimed.
- Paid provider POST count: 0. No actual provider credential was accessed.
- No remote action, production access, naming/AppIdentity/OAuth protocol change,
  accepted snapshot mutation, or modification of the two predecessor commits.

Next gate: PRODUCT_OWNER_FIRST_RUN_UX_REVIEW. Runtime UI acceptance remains pending.
