# Phase 9 Local Zero-Cost RC Evidence

## Current verdict

```text
LOCAL ZERO-COST RC GATE = REOPENED
CORRECTED DETERMINISTIC UX VERIFICATION = PASS
REAL KEYED WINDOWS PORTABLE ACCEPTANCE = PENDING HUMAN RESTART
RC UX = NOT FROZEN
LOCAL FIXTURE CORPUS = UNCHANGED
PAID GENERATION POSTS = 0
PRE-LIVE REMOTE GATE = NOT STARTED FOR THE CORRECTED COMMIT
```

The Product Owner rejected the UX represented by
`432f0bcd0f1df0bc4cffadfef11cfb638cd22b51`. Its earlier Gate-A/freeze declaration is historical and
does not authorize push, remote validation or paid work.

## Corrected scope

The correction is limited to:

- readable catalogue model labels while serializing canonical IDs;
- complete selected-model dependent option presentation;
- effective reference kinds/count/mixed-support projection;
- direct, ordered, model-limited reference sockets on Generate;
- explicit public-HTTPS reference transport and legacy Phase-8 compatibility;
- visible preservation/invalidation when a model change lowers the reference limit;
- actual browser interaction evidence.

No AppIdentity, billing, recovery, persistence, exact paid case, fixture, prompt or generation-mode
contract changed.

## Corrected interaction evidence

Actual Comfy browser interactions passed on isolated keyless runtimes for both release-blocking
hosts:

| Host | Frontend | Evidence |
| --- | --- | --- |
| ComfyUI `v0.34.3` / `87465b8f...` | `1.49.6` | readable model selection; typed image/video node chooser; `1 → 2 → 3` reference autogrow; model-limit invalidation; save/reload preservation |
| ComfyUI `v0.37.0` / `73c9bad4...` | `1.52.7` | readable model selection; complete projected enum values including `768p` and `5:4`; direct reference socket and native host compatibility |

The v0.34.3 interaction created an ordered image/video/image set through the actual node chooser.
At the effective maximum of three there was no fourth trailing input. Changing to a model with
`max_reference_count = 0` preserved all three links, displayed an explicit `3/0` invalid state and
did not silently alter intent. Graph serialization/reload retained the canonical model ID and all
three links.

The browser capability and estimate routes were synthetic loopback data. That is sufficient for
deterministic frontend/host compatibility, but not for final real-catalogue acceptance.

## Local media transport result

Current authoritative OpenRouter Video documentation describes frame and input references as
publicly retrievable URL objects. It does not establish data-URL/base64 or direct local Comfy
IMAGE/VIDEO transport for the Video API. Phase 9 therefore exposes honest Public Image URL and
Public Video URL nodes. Native local media transport remains `UNPROVEN`, not silently inferred from
other OpenRouter APIs. See `docs/phase-9-local-media-transport-contract.md`.

## Verification ledger

```text
pytest                                      222 passed
focused adapter/frontend contract tests      22 passed
ruff check                                  PASS
ruff format --check                         PASS after formatting fix
mypy --strict src                           PASS
node syntax                                 PASS
diff whitespace                             PASS
Comfy runtime probe v0.34.3                 PASS
Comfy runtime probe v0.37.0                 PASS
actual browser interaction v0.34.3          PASS (isolated keyless 8190)
actual browser interaction v0.37.0          PASS (isolated keyless 8191)
```

No paid POST was issued and no OpenRouter key was requested, read, enumerated, injected, logged or
persisted. Production port `8188` was not touched. The human-keyed process on `8189` was not
restarted by Codex.

## Remaining Gate-A acceptance

After the corrected local commit exists, the Product Owner must restart keyed Windows Portable
ComfyUI on `8189`. The final local acceptance must use the real `/models` and `/ui-capabilities`
routes, with no route mocks, and must confirm:

- real catalogue display names;
- real selected-model resolutions/aspect ratios/durations;
- reference kinds and effective limit behavior;
- seed/audio/frame controls;
- estimate presentation;
- truthful progress;
- workflow save/reload and Phase-8 migration;
- native VIDEO + SaveVideo.

Only after that acceptance passes may the RC UX be frozen and the corrected commit become eligible
for push/draft-PR update and the Pre-Live Remote Gate. Paid execution remains unauthorized.
