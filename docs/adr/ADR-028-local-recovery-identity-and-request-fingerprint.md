# ADR-028 — Local Recovery Identity and Request Fingerprint

- Status: `ACCEPTED`
- Scope: Phase 5 — Headless Core II
- Decision owner: Product Owner

## Context

The validated Architecture includes `operation_id`, `request_fingerprint`, and `job_id` in durable
job state, but did not define their authority relationship, the fingerprint preimage, or the
database concurrency rule. Persisting prompts, request bodies, frame URLs, credentials, or raw
responses is prohibited. Billing safety also requires concurrent calls for one logical operation
to acquire at most one paid-submit right.

## Decision

Identity authority is strictly hierarchical:

1. `job_id` is the authoritative remote paid-generation identity after accepted submission.
2. `operation_id` is the authoritative local logical-operation identity before and through
   recovery.
3. `request_fingerprint` is an advisory consistency checksum only.

`request_fingerprint` is not an identity, idempotency key, authorization to resume, submit,
regenerate, or deduplicate, and is never a recovery lookup key. A match alone grants no authority.

### `operation_id`

`operation_id` is required at the `GenerateService` boundary, opaque, local-only, persisted, and
never transmitted to OpenRouter. It must not be derived from prompt, media URL, credential,
`AppIdentity`, or any user, device, installation, workflow, node, or session identity.
`node_instance_id` remains nullable and reserved in Phase 5.

Reusing an `operation_id` means "this is the same logical Generate operation." A new paid logical
operation requires a new `operation_id`. Existing durable state is reconciled; it never silently
grants another POST.

### Request fingerprint v1

The exact payload uses already validated domain values and this fixed field set:

```json
{
  "schema": 1,
  "model": "<canonical validated model id>",
  "duration": null,
  "resolution": null,
  "aspect_ratio": null,
  "size": null,
  "seed": null,
  "generate_audio": false,
  "first_frame_present": false,
  "last_frame_present": false
}
```

Canonical bytes are UTF-8 JSON with sorted keys, explicit nulls, no insignificant whitespace,
deterministic separators, and locale-independent values:

```python
json.dumps(
    payload,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
).encode("utf-8")
```

The stored value is `"v1:" + sha256(canonical_bytes).hexdigest()`. Canonical bytes are not stored.

The preimage excludes prompt values, frame URLs and all media URLs, credential and Authorization
data, `AppIdentity` and headers, `operation_id`, `node_instance_id`, `job_id`, timestamps, remote
status, cost/usage, output paths, transport metadata, random IDs, and any machine, installation,
user, workflow, or session identity.

This exclusion is a privacy property: SHA-256 is not encryption, and hashing sensitive user
content would create a persistent derived representation of content that must not be persisted.

Because prompt and frame URLs are excluded, distinct requests may have the same fingerprint. This
is intentional. Equality does not prove request equality; a mismatch proves that the persisted
non-sensitive request shape changed.

For an existing `operation_id`:

- equal fingerprint: the advisory consistency check passes and durable state is reconciled;
- unequal fingerprint: do not resume blindly and do not submit; preserve evidence and map through
  the conservative local-state corruption/recovery-conflict taxonomy.

The Core must not persist sensitive request content merely to detect caller misuse. Consequently,
the same `operation_id` with a different prompt or frame URL but the same advisory fingerprint
still reconciles the existing logical operation.

### Persistence and concurrency enforcement

`operation_id` is mechanically authoritative in `JobStore`:

- `operation_id` is `NOT NULL` and `UNIQUE`; it is the jobs-table primary key in schema v1.
- non-null `job_id` is unique within local durable state.
- `request_fingerprint` is never unique and is never indexed or queried as an authority-bearing
  recovery key.

`GenerateService` atomically claims `operation_id` before network submission:

```text
BEGIN
→ create operation_id in SUBMITTING state
→ COMMIT
→ only then POST
```

With two concurrent Generate calls using the same `operation_id`, exactly one may acquire the
submit right. The loser reloads and reconciles durable state and must never issue another POST. A
uniqueness conflict is a recovery signal, not permission to retry submission.

## Fitness criteria

- Equivalent normalized non-sensitive shapes produce the same fingerprint regardless of mapping
  order or omitted-vs-null raw input normalized to the same domain value.
- Model, generation option, or frame-presence changes produce a different fingerprint.
- Prompt-only and frame-URL-only changes produce the same fingerprint by design.
- Credential, identity, header, and `operation_id` changes do not change the fingerprint.
- Fingerprint alone never authorizes resume or submit.
- Two concurrent compatible Generate calls with the same `operation_id` issue exactly one total
  `POST /api/v1/videos`.

## Consequences

Recovery authority is explicit without persisting sensitive request content. The Core can detect
non-sensitive shape drift but intentionally cannot detect every caller misuse of `operation_id`.
