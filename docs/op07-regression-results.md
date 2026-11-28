# OP-07 implementation verification — 2026-11-09

Frozen baseline 058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9; separate
Codex/op07-discovery-remediation-20261108 worktree. No runtime installation.

PASS below means the stated offline scope, not browser/provider certification.

| Case | Result | Evidence and limit |
|---|---|---|
| R01 ten exact IDs | PASS offline | test_ten_models_remain_discovered; public catalogue snapshot reused |
| R02 Veo/Kling regression | PARTIAL / OPEN | Veo bounded shape restored; Kling exact shape/size findings OPEN |
| R03 nonpositive states | PASS offline | nonpositive methods, missing/conflicting evidence tests |
| R04 partial methods | PASS offline | partial support + real MockTransport request tests |
| R05 unknown ID | PASS offline | synthetic new ID with confirmed profile; no whitelist |
| R06 price independence | PASS offline | eligible model with pricing_evidence=None |
| R07 empty/error/disconnected | PASS unit/VM | route tests; visible empty diagnostic; temporary failure recovery |
| R08 legacy save/reload/export | PARTIAL | picker retains raw ID, JSON save/reload and existing migration tests; native Comfy workflow/API export NOT_VERIFIED |
| R09 explicit replacement | PASS existing VM contracts | explicit model switch and compatible link restoration |
| R10 refresh disappearance | PASS VM | excluded ID and inputs retained; no silent replacement |
| R11 consumers | PASS offline | /models and /ui-capabilities share project_selectable; schema remains sentinel-only |
| R12 complete shape | PASS offline | request_witness requires validator + serializer; unknown prompt and missing bounded domains fail closed |
| R13 serialization | PASS MockTransport | real OpenRouterVideoClient on synthetic transport; Google 6 model-method requests; zero real POST |
| R14 Classic/Nodes2 | PARTIAL | existing frontend/renderer contracts pass; real new-patch browser proof NOT_VERIFIED |
| R15 protected surfaces | PASS offline | Product Contract Guard, exact protected functions, unchanged other model facts |
| R16 untrusted/stale evidence | PASS existing Core gates + unit | no invented upstream request-shape parser; existing TTL unchanged |
| R17 new eligible model | PASS VM | same node/picker updates without page reload; not real browser proof |
| R18 new ineligible model | PASS VM/Core | remains backend-only, excluded options |
| R19 capability upgrade | PASS VM | same ID, method-set change reprojected |
| R20 capability downgrade | PASS VM/source | changed profile detected; missing method parks saved intent, no default substitution |
| R21 preserve selection/prompt | PASS VM | raw ID/prompt/link retained across refresh |
| R22 concurrent/reversed requests | PASS VM | one capability request; invalidated epoch cannot replace new cache |
| R23 lifecycle triggers | PASS VM | 300000ms timer, hidden/offline pause, visible/online recovery; connection presentation transition triggers refresh |
| R24 capability-only change | PASS VM | signature includes profiles, not merely IDs/count |

## Executed checks

- Full Python suite: **524 passed, 3 skipped** (46.10s), before one additional
  fixture-to-Core equality test. Latest affected eligibility suite: **14 passed**.
- Full frontend suite: **154 passed**; after adding six Google model-method
  control cases, affected public-projection suite: **56 passed**, including all six.
- Ruff check PASS; format check PASS (234 files at recorded run); mypy PASS
  (121 source files). New fixtures/tests were not added to accepted snapshots.
- Installed Builder Product Contract Guard: PASS, 5 authorized source surfaces,
  UNAUTHORIZED_DELTA=[], unchanged security/submit_resume/AppIdentity/storage.
- Existing historical pin tests now explicitly validate their original checkpoint
  plus the separate UNACCEPTED OP07 candidate pin. New OP07 scope tests check real
  current code: all pre-existing JS functions outside the four declared catalogue
  functions remain exact; registration only adds lifecycle setup; all other model
  facts, especially Seedance and Kling conflict evidence, remain unchanged.

Three skipped tests require unmaterialized third-party media packs. No downloads,
installations, paid execution or runtime changes were performed to satisfy them.

Logs and model matrix: ../output/op07-discovery-implementation-20261109 in the
workspace (outside this product worktree). Earlier failed runs remain evidence.

## Remaining qualification boundaries

1. Owner must separately authorize installation of a reviewed patch artifact into
   TEST before any new-patch browser acceptance. No new RC/tag/release is created.
2. Real Classic/Nodes2 switching, visible refresh, native save/reload/API export
   remain NOT_VERIFIED. VM tests are not reported as real ComfyUI proof.
3. Kling O1/Pro/Standard, Gemini 1.1, mischief and the specialized source operations
   remain OPEN for exact request-contract reconciliation; hiding them is protective
   behavior, not functional restoration. Google wider domains remain OPEN.
4. Current public discovery lacks a documented full request-shape schema. Generic
   selection automatically activates newly confirmed effective profiles, but cannot
   fabricate proof from flat domains or activate unsupported new API contracts.

The Owner reported a successful paid inference on existing TEST. Read-only UI
inspection saw Grok Imagine Video 1.5 / I2V / 480p / 5s, linked Load Image and Save
Video, 0 active tasks. Final job status/output was not visible. Recorded separately
as Owner-reported success, not patch execution, OAuth transaction proof or billing
certification. No agent paid requests or repeat inference were performed.
