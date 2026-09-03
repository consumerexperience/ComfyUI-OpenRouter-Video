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

## Future product fitness functions

| Contract | Current status |
| --- | --- |
| Generate paid POST count at most one | `PENDING_IMPLEMENTATION` |
| Ambiguous submit never creates another POST | `PENDING_IMPLEMENTATION` |
| Resume POST count zero | `PENDING_IMPLEMENTATION` |
| Poll/download failure observes the same job | `PENDING_IMPLEMENTATION` |
| External host receives no Authorization | `PASS — Phase-4 prepared-request/transport boundary` |
| External host receives no attribution | `PASS — Phase-4 prepared-request/transport boundary` |
| Redirect is not followed | `PASS — observable 302/307/308 tests` |
| Canonical title and category stability | `PASS` |
| Canonical Referer exact-value stability | `PASS — frozen release fixture` |
| Capability cache avoids synthetic network calls | `PENDING_IMPLEMENTATION` |

Phase-4 tests additionally cover origin spoofing, validation-before-secret ordering, exact
operation paths and timeout classes, zero transport retry, safe error/log content, no tracking
identity, and headless core isolation. Harness self-tests remain evidence for harness mechanics
only and do not prove Phase-5 lifecycle behavior.
