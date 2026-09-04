# Changelog

## Unreleased

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
