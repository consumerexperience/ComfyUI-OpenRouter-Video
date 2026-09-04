# ADR-029 — Durable Definite Submit Rejection

- Status: `ACCEPTED`
- Scope: Phase 5 — Headless Core II
- Decision owner: Product Owner

## Context

The Architecture requires durable `SUBMITTING` intent before the single network POST. A definite
OpenRouter rejection can then prove that no remote generation job was accepted. Leaving the record
in `SUBMITTING` would falsely imply ambiguity after restart; deleting it would restore submit
authority for the same `operation_id`; and `FAILED` is reserved for a known remote job that reaches
a remote terminal failure.

## Decision

Add one local terminal lifecycle state: `SUBMIT_REJECTED`.

```text
SUBMITTING
├── accepted + trustworthy job_id → ACCEPTED
├── ambiguous transmission/outcome → SUBMISSION_UNKNOWN
└── authoritative definite rejection → SUBMIT_REJECTED
```

`SUBMIT_REJECTED` means:

- a generation POST was attempted;
- an authoritative response established rejection;
- no accepted `job_id` exists;
- there is no known remote generation to poll;
- automatic resubmission is forbidden.

Persist:

- `local_state = SUBMIT_REJECTED`
- `job_id = NULL`
- `product_error_code =` the canonical mapped `ProductError`
- `remote_status_raw = NULL`
- normal timestamps required for forensic state

Definite examples include 401 `API_KEY_INVALID`, 402 `INSUFFICIENT_CREDITS`, documented
validation/model rejections mapped to the canonical product error, and submit 429
`RATE_LIMITED_SUBMIT`. All receive zero automatic retries.

Timeouts, resets, ambiguous 5xx responses, and malformed successful-looking responses after a
request may have reached the server must not use `SUBMIT_REJECTED`; they remain
`SUBMISSION_UNKNOWN`.

`SUBMIT_REJECTED` is local and distinct from:

- `FAILED`: a known remote generation reached remote terminal failure;
- `SUBMISSION_UNKNOWN`: a remote job may exist but its identity is unknown;
- `OBSERVATION_INTERRUPTED`: observation failed for a known job.

Recovery with the same `operation_id` returns the durable terminal rejection and issues no POST.
A new explicit generation attempt requires a new `operation_id`.

## Fitness criterion

```text
definite submit rejection
→ durable SUBMIT_REJECTED
→ restart
→ same operation_id
→ additional POST == 0
```

## Consequences

Durable pre-submit intent remains truthful after definite rejection, and local recovery cannot
convert a rejected logical operation into a second paid attempt.

