# Testing contract

## Default zero-cost suite

The default pytest expression excludes `live`. CI and local verification must not contact
OpenRouter or read an OpenRouter credential.

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests
python -m build
python -m pip_audit
```

The harness binds to `127.0.0.1` on an ephemeral port and supports scripted responses, malformed
payloads, redirects, delayed responses, sanitized request recording, and connection drop after a
request is received.

## Product fitness functions

| Contract | Current status |
| --- | --- |
| Generate paid POST count at most one | `PASS — MockTransport/service ledger` |
| Ambiguous submit never creates another POST | `PASS — durable SUBMISSION_UNKNOWN` |
| Resume POST count zero | `PASS — submit-incapable typed dependency` |
| Poll/download failure observes the same job | `PASS — same durable job_id` |
| External host receives no Authorization | `PASS — Phase-4 prepared-request/transport boundary` |
| External host receives no attribution | `PASS — Phase-4 prepared-request/transport boundary` |
| Redirect is not followed | `PASS — observable 302/307/308 tests` |
| Canonical title and category stability | `PASS` |
| Canonical Referer exact-value stability | `PASS — frozen release fixture` |
| Capability cache avoids synthetic network calls | `PASS — 15 min fresh / 24 h LKG` |
| Definite submit rejection survives restart | `PASS — durable SUBMIT_REJECTED` |
| Concurrent same-operation Generate | `PASS — one atomic submit-right claim` |
| Prompt/frame URL absent from fingerprint and SQLite | `PASS — privacy canary` |
| Reference URLs absent from fingerprint, SQLite, and sanitized errors | `PASS — privacy canary` |
| Typed frame/reference payload shapes | `PASS — exact contract fixtures` |
| Reference order and repeated occurrence preservation | `PASS — unit + pinned Autogrow` |
| Unknown-model reference capability gaps block before submit | `PASS — zero POST` |
| Exact-ID overlay reference modes | `PASS — multi-image/video/mixed mock lifecycle, one POST each` |
| Overlay precedence and conflict | `PASS — Level A retained; disagreement fails closed` |
| Overlay freshness | `PASS — stale LKG cannot activate reference intent` |
| Prompt required for every Phase-8 Generate | `PASS — omission rejected before discovery/submit` |
| Database v2-to-v3 semantic equality and cache invalidation | `PASS` |
| New Generate fingerprint v2 and historical v1 conflict | `PASS` |
| Actual cost comes only from `usage.cost` | `PASS — Decimal or None` |
| Durable content is MP4/WebM only | `PASS — QuickTime disabled` |
| Two Comfy Queue actions execute twice | `PASS — pinned PromptExecutor + JSON-safe token` |
| One Comfy execution creates one Core Generate call | `PASS — adapter/runtime spy` |
| Caller cancellation preserves runtime disposition | `PASS — cross-loop cooperative control` |
| SQLite v1-to-v2-to-v3 migration | `PASS — semantic equality; exact sentinel rule` |
| Native VIDEO bridge | `PASS — pinned VideoFromFile + GetVideoComponents MP4/WebM` |

Tests additionally cover origin spoofing, validation-before-secret ordering, exact operation paths
and timeout classes, zero transport retry, safe error/log content, no tracking identity, local
lifecycle transitions, tolerant response parsing, discovery cache authority, SQLite recovery,
one-POST billing semantics, Resume, bounded content download, and headless core isolation. Harness
self-tests remain evidence for harness mechanics only and do not prove live-service behavior.

The pinned host gate is intentionally separate because the repository `.venv` does not install
ComfyUI. Run `tests/comfy_dev_probe.py --cpu` with the exact DEV Comfy interpreter. It uses injected
mock runtime behavior, creates only temporary 16x16 video files, and never creates a Core runtime or
network client. Its Phase-8 coverage includes typed custom links and Autogrow zero/one/many,
ordering, duplicate occurrences, workflow validation, and repeated PromptExecutor queues.

`tests/manual/phase8_catalog_probe.py` is a separate human-run, read-only harness. It performs one
credential-free GET, disables ambient proxies and redirects, emits only approved sanitized
capability observations, and is never collected by pytest or run by CI.
