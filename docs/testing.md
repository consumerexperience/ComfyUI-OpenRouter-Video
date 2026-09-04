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
| Actual cost comes only from `usage.cost` | `PASS — Decimal or None` |
| Durable content is MP4/WebM only | `PASS — QuickTime disabled` |

Tests additionally cover origin spoofing, validation-before-secret ordering, exact operation paths
and timeout classes, zero transport retry, safe error/log content, no tracking identity, local
lifecycle transitions, tolerant response parsing, discovery cache authority, SQLite recovery,
one-POST billing semantics, Resume, bounded content download, and headless core isolation. Harness
self-tests remain evidence for harness mechanics only and do not prove live-service behavior.
