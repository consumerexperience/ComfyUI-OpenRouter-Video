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

| Contract | Phase 3 status |
| --- | --- |
| Generate paid POST count at most one | `PENDING_IMPLEMENTATION` |
| Ambiguous submit never creates another POST | `PENDING_IMPLEMENTATION` |
| Resume POST count zero | `PENDING_IMPLEMENTATION` |
| Poll/download failure observes the same job | `PENDING_IMPLEMENTATION` |
| External host receives no Authorization | `PENDING_IMPLEMENTATION` |
| External host receives no attribution | `PENDING_IMPLEMENTATION` |
| Redirect is not followed | `PENDING_IMPLEMENTATION` |
| Canonical identity exact-value stability | `NOT_APPLICABLE — APP_REFERER UNRESOLVED` |
| Capability cache avoids synthetic network calls | `PENDING_IMPLEMENTATION` |

Harness self-tests are PASS evidence for harness mechanics only. They are not product fitness
evidence.
