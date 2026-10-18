# Local callback outcome inspection

Owner-authorized passive diagnostics from `9a41c5f`. The buffer contains only
predefined category strings: the last 32 events in this process. It stores no
keys, codes, state, verifier, URLs, request data, exception text, timestamps or
identifiers. There is no file, log, database, workflow, browser-storage or remote
telemetry write. Restarting the process clears the buffer.

Read-only local inspection: `GET /openrouter-video/v1/auth/diagnostics`, returning
`{"outcomes": [...]}` with `Cache-Control: no-store`. Nothing is added to the
connection payload, Settings UI or callback result HTML. Existing ComfyUI
middleware still governs access to this route.

Categories distinguish success, duplicate/consumed receiver, receiver closing
without a previous callback, deadline, provider
error, invalid callback shape, state mismatch, environment-managed completion,
exchange failure, catalogue validation failure, credential-store failure,
generic unsuccessful completion and unexpected callback failure. Completion
stage failures are followed by generic COMPLETION_FAILED at the receiver.
Events are ordered observations, not transaction identifiers; concurrent requests
can interleave, and several stage/deadline observations may refer to one attempt.
The buffer intentionally cannot attribute an event to a user or browser.

This cannot recover the previous Yandex transaction. It starts collecting only
in a process running this candidate. No new real authorization is needed to
install or inspect it. Protected auth, credential, generation and UI behavior
remains unchanged; focused tests retain the original HTTP results and cleanup.
