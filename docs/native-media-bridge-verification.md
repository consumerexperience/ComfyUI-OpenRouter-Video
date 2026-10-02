# Native Media Bridge — implementation verification, 2026-10-02

## Implemented

Current Phase 10 branch: phase-10/capability-driven-inference-methods. Native IMAGE/VIDEO/AUDIO and legacy references share ordered sockets; Source Video accepts native VIDEO and the legacy reference. Conversion, private S3-compatible staging, 24-hour signatures, exact-object ownership, SQLite migration 5, terminal/no-submit cleanup and Resume recovery are implemented. Startup cleanup is one tracked operation on the existing loop, so slow storage does not prevent runtime readiness. There is no scheduler or additional cleanup thread. [ADR-032](adr/ADR-032-native-media-s3-staging.md) records the approved transport; [setup and live runbook](native-media-bridge.md) records user prerequisites.

## Tests

- Default pytest: **301 passed**. Focused staging/ownership suite rerun after explicit SQLite connection closure: **21 passed**.
- Actual botocore loopback HTTP transport: retryable PUT failures = **3** sends; success on attempt two = **2**; nonretryable rejection = **1**; redirect = **1** with no follow; an injected excessive SDK retry handler still cannot issue PUT four. Attempts preserve one object key.
- Conversion and socket probes against real ComfyUI **v0.34.3** and **v0.37.0** passed: components and file-backed VIDEO become H.264 MP4; mono/stereo AUDIO becomes PCM16 WAV at its original rate; invalid/empty batches and non-finite samples reject locally. Existing PromptExecutor compatibility probes passed on both hosts after including Phase 10's required inference_method.
- Mixed order/duplicates, native Source Video, capabilities before conversion/PUT, per-object/request byte limits, partial upload failure, concurrent claim, repeated cancellation, ambiguous submit, unknown status, Resume without upload/submit, terminal DELETE, pending cleanup retry, config mismatch, 48-hour orphan cleanup and v4-to-v5 migration passed.
- Credential/attribution separation and persistence/error/debug-log canaries passed. Ruff check and format, strict mypy, wheel/sdist build and dependency audit passed. Audit first identified urllib3 2.7.0 vulnerabilities; pyproject and the development lock now use corrected 2.8.0. The local project is not a PyPI audit target; installed third-party dependencies have no reported vulnerabilities.

## Browser proof

Real ComfyUI **v0.37.0**, frontend **1.52.7**, isolated existing fixture harness in Edge/Playwright. Synthetic media; no OpenRouter/storage credentials. IMAGE → VIDEO → AUDIO → the same VIDEO occurrence connected directly, stayed ordered through graph serialization/load and a full browser-page reload, and selected MMR2V remained valid. Queue exposed and verified the repaired Autogrow validate_inputs signature. The next queue reached the actual Core storage-configuration failure before any paid submit.

- [Native connections](assets/native-media-bridge/native-media-connections.png)
- [Storage configuration error](assets/native-media-bridge/native-media-storage-error.png)
- [Machine-readable evidence](assets/native-media-bridge/native-media-browser-proof.json)
- [Synthetic workflow](assets/native-media-bridge/native-media-workflow.json)

This is fixture browser proof. Canonical DEV was observed RUNNING_STALE relative to current product source and its key-bearing process was not managed. It does not establish refreshed authenticated DEV or live provider behavior.

## Remaining separately approved live smokes

1. User configures local R2 credentials and a prefix-scoped 48-hour lifecycle. Explicitly authorize and run the prepared synthetic PUT → signed HTTPS GET without auth headers → exact DELETE smoke. No OpenRouter calls.
2. Refresh canonical DEV through the owner's governed launcher and configure the user's capped OpenRouter key locally. Review supported duration/resolution and the owner cap, then explicitly authorize **one** native VIDEO/AUDIO generation immediately before Queue. Observe the same job, verify terminal object deletion; any recovery uses Resume with zero extra uploads/POSTs.

Neither live smoke was executed. Publication, push, release and merge were not performed.
