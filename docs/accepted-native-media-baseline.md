# Accepted Native Media baseline v1

The owner-authorized live certification tested product source
`0f05665cb302fe4bc8398f2e9e04b08a5116a313` with Seedance 2.0 Mini,
MMR2V, IMAGE → VIDEO → AUDIO, 480p, four seconds and generated audio disabled.
One generation POST completed, produced a native Comfy VIDEO consumed by SaveVideo,
cost $0.169617, and left zero owned staging objects. The receipt records local
provenance and artifact SHA-256; the generated binary is not committed.
The provider delivered 864×496 and 4.041667 seconds; 480p/four seconds describe
the submitted configuration, not an assertion of exact output dimensions.

The accepted contract freezes normalized source digests across protected surfaces.
Existing deterministic behavior tests remain required by full pytest. The existing
Builder Product Contract Guard compares the current source against this baseline
and rejects any undeclared difference, including registry and frontend changes.
This conservative guard also requires a delta for comments within protected files.
It never modifies the accepted snapshot to make a failing change pass.

Future authorized changes must supply an owner-approved Contract Delta using the
existing protocol, bound to the accepted source SHA, with exact semantic paths and
reasons. Select that file through `OPENROUTER_VIDEO_CONTRACT_DELTA` in the verification
environment/CI job. No selection means no product changes are authorized.
An explicit delta is review evidence, not permission to bypass behavior tests or
GitHub protections. Unexpected delta means FAIL / STOP.

Ordinary CI excludes paid tests. A separately authorized, capped paid certification
is required for changes to provider serialization, reference wire representation,
native/staging transport, submit authority/lifecycle, payload-affecting recipes,
or the relevant upstream Video API contract, and when the owner requests release
certification. Wallet funds are never spent automatically.

Delivery preserves two identities: LIVE_TESTED_PRODUCT_SHA is always the source
above; REGRESSION_SHIELD_CHECKPOINT_SHA is the later canonical protection merge.
Until human merge and exact-head CI/CodeQL read-back, the checkpoint remains pending.
After merge, create annotated `openrouter-video-native-media-e2e-v1` at that exact
canonical merge, explicitly binding both identities. Never move the existing
`phase10-native-media-v1` or `capability-catalog-rebase-v1` tags.

GitHub main requires PR, all five CI checks and Analyze Python, strict up-to-date
head validation, no deletion and no force push, without bypass actors. Acceptance
tags require update/deletion protection. Validate the exact PR head and merge base
immediately before the human-only merge; previous green heads are insufficient.
