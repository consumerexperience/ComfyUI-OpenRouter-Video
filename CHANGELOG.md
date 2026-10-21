# Changelog

## 0.1.0-rc.2 — local RC identity reconciliation

- Assign the reviewed Naming / First-Run UX / OAuth candidate its own RC identity.
  The immutable v0.1.0-rc.1 tag and historical receipts remain unchanged.
- Package metadata and both About version labels now identify 0.1.0-rc.2
  (PEP 440: 0.1.0rc2). No new features, UI design or authentication changes.
- Includes the previously implemented connection UX, secure credential storage,
  loopback callback pages and transaction-scoped duplicate-result handling.
- Existing browser limitations remain open: Codex native popup visibility and
  the reported Yandex failure have no proven root cause. No new live OAuth or
  paid qualification is claimed. Existing model, staging and platform limitations
  listed below still apply; no public release or Registry publication is made.

## 0.1.0-rc.1 — local RC preparation

- OpenRouter asynchronous Video generation with your own API key in ComfyUI.
- Adaptive model/method controls for T2V, I2V, FLF2V, IR2V/MI2V, VR2V and MMR2V
  where the reviewed OpenRouter integration confirms support.
- Seedance 2.5 Edit and Extend through Source Video plus Prompt.
- Native IMAGE/VIDEO/AUDIO references where supported and native VIDEO output.
- Resume/recovery for known jobs without another Video submit; local durable state.
- Conservative cost estimates and actual cost from OpenRouter when available.
- Classic and Nodes 2.0, responsive Prompt, saved values and compatible media links.
- Generate node display name is OpenRouter Video; existing node identifiers and
  saved-workflow compatibility are preserved.
- First-run Settings connection with OpenRouter PKCE sign-in, masked manual-key
  fallback, live connection status and OS-vault persistence with explicit
  session-only fallback. Environment credentials retain precedence.
- Dedicated loopback OAuth receiver, readable Russian callback result pages and
  bounded in-memory safe outcome diagnostics. Exact successful duplicate callbacks
  replay the transaction result without repeating exchange, validation or storage.
- Source package now includes the ComfyUI entrypoint and frontend. Installation,
  update and security documentation reflect the accepted product.

### Known limitations

Capabilities vary by model/integration. UNKNOWN/CONFLICT features remain hidden;
provider-native capability is not proof of OpenRouter exposure. Seedance 2.5 Draft
is not exposed; its reviewed output tiers are 480p/720p. Standalone AR2V remains
hidden where unconfirmed/conflicting. Known Exact Size conflicts are constrained.
Native VIDEO/AUDIO requires user-configured private S3-compatible staging.
Estimates may be unavailable and are not charge guarantees. Real callback-page
rendering in the Codex native popup and the reported Yandex failure remain
unresolved; controlled Chromium proves synthetic transaction handling only.
Windows vault restart behavior was exercised previously; macOS/Linux vault runtime
availability remains platform-dependent. No public RC release,
Registry publication or new paid inference is part of this preparation.

## Historical engineering notes

- Added Phase-9 capability-only UI projection, unresolved initial model, complete catalogue-driven
  controls, native seed semantics, truthful adapter progress, and a presentation-only reactive
  helper with no model/provider tables.
- Added typed Core-only pricing evidence plus a conservative model-agnostic preflight estimator;
  ambiguous pricing remains explicitly unavailable.
- Advanced the database to schema v4 while preserving JobRecord schema v2 and durable jobs; v3
  external capability/pricing cache truth is invalidated.
- Added four-version Comfy capability probes, Phase-8 workflow-value migration, exact AppIdentity
  regression coverage, the synthetic five-case live fixture corpus, and controlled evidence docs.
- Added Phase-8 typed image/video input-reference contracts with structural order and duplicate
  preservation, while failing closed before submit where runtime capability evidence is absent.
- Updated `frame_images` to the current typed nested media protocol.
- Added independent mode-level capability enforcement and sanitized `CAPABILITY_SIGNAL_GAP`.
- Split database schema v3 from JobRecord schema v2; v2-to-v3 invalidates external capability cache
  without changing durable job semantics.
- Added request fingerprint v2 with prompt/reference presence, ordered kinds, and no sensitive
  values; historical v1 rows remain untouched.
- Added image reference, video reference, and Autogrow reference collection ComfyUI nodes.
- Added a credential-free sanitized manual catalog probe and Phase-8 evidence matrix.

- Repository scaffold initialized.
- Added immutable application-identity and environment secret-provider boundaries.
- Added canonical operation, path, timeout, and connection policy for OpenRouter Video requests.
- Added centralized origin-bound authentication and attribution request composition.
- Added a zero-auto-retry HTTPX transport with redirects and ambient proxies disabled.
- Added redaction, origin-spoofing, redirect-containment, and external-host leakage tests.
- Froze the canonical production Referer as
  `https://github.com/consumerexperience/ComfyUI-OpenRouter-Video` by explicit Product Owner
  decision.
- Added exact-value release-identity and attribution-header drift tests.
- Added ADR-028 local operation authority, deterministic privacy-preserving request fingerprint,
  and SQLite concurrency enforcement.
- Added ADR-029 durable `SUBMIT_REJECTED` for definite one-attempt submit rejection.
- Added typed Video API contracts, tolerant response parsing, and policy-prepared content streaming.
- Added capability discovery with 15-minute freshness, 24-hour bounded LKG, and positive capability
  validation for frame and audio intent.
- Added SQLite job recovery, one-attempt Generate, submit-incapable Resume, bounded polling, and
  unknown remote-state preservation.
- Added bounded MP4/WebM download with `.part`, validation, fsync, and atomic rename; QuickTime
  remains disabled.
- Added zero-cost billing, concurrency, restart, corruption, privacy-canary, and media fitness tests.
