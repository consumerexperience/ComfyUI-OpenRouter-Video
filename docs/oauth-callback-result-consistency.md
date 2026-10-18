# Callback results are transaction-scoped

Starting candidate: `c5d44b19e73533b0ac1bc634f3582b23789edc9b`.

The reproduced inconsistency came from an unconditional 410 response whenever
the receiver was already consumed. A duplicate could therefore display failure
while the original request successfully persisted the connection. This is not
established as the cause of the owner's earlier Yandex Browser result.

The receiver now retains one terminal success result for at most five seconds,
clipped to the original authorization deadline, and then closes the listener and
clears its result. Explicit close/replacement also clears it. Retention does not
extend the original timeout. The same ephemeral loopback socket serves replay;
no extra server, durable store, browser script or callback route is introduced.

A replay must have the exact original state AND code, without provider error or
duplicate/missing fields. Matching uses a SHA-256 digest of the pair, retained
only in the receiver's memory. Raw state and the PKCE session are discarded when
the original request finishes. No digest, code, state, verifier or credential is
returned, logged or added to the diagnostic buffer. Existing safe categories
remain; RESULT_REPLAYED distinguishes a successful result replay from a new
authentication operation.

An exact duplicate arriving during completion waits for the original request.
It never calls the completion function. A successful duplicate receives the same
200 HTML; a failed original never yields success. Wrong/missing/unrelated state,
wrong code and expired requests fail independently of any Connected account.
Failed requests are not retained as successful, and do not gain a retry path.

Tests use production receiver and completion routes with synthetic exchange,
catalogue validation and persistence boundaries. Controlled Chromium screenshots
cover original success, pending and completed duplicates, wrong/missing state,
another live transaction's state, elapsed deadline and a failed validation while
the global account is Connected. Completion counters prove exchange=1,
validation=1, persistence=1 for the successful transaction; the failed validation
does not persist. The elapsed-deadline browser case advances the synthetic
receiver's deadline while its socket remains open, exercising a queued expired
request rather than waiting ten minutes.

The five-second limit intentionally means a navigation after socket cleanup
cannot replay a page. It cannot authenticate, exchange a code again or report a
cached success. Real Yandex and Codex native-popup compatibility remains a
separate unresolved gate; synthetic Chromium proof is not real-provider proof.
