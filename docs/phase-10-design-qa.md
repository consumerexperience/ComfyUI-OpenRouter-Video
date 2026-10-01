# Phase 10 Direction 3 — Design QA (2026-09-30)

Status: **PARTIAL — not visual acceptance or release readiness**.

Target: the Product Owner-accepted Direction 3 specification and images in
`phase-10-direction-3-visual-spec.md`. Observed surface: real, unmocked canonical ComfyUI
v0.34.3 on `127.0.0.1:8189`, UI contract 4, 29 live catalogue models. No workflow was queued and
no paid Video POST was authorized or sent.

## Observed on the real canvas

- A fresh node without a model has no media sockets. The method is disabled and reads
  `Select model first`.
- Selecting `bytedance/seedance-2.5` on a genuinely new node selects `MI2V`. The method menu
  presents all ten approved method labels.
- The primary widget order is Model → Inference Method → Prompt → Resolution / Aspect Ratio →
  Duration → Seed / Generate Audio → Advanced. Cost is presented in the header. The native seed
  behavior control is hidden until Advanced is opened.
- Connecting a Public Image URL to `image_1` creates `image_2`; connecting the same helper again
  creates `image_3` while preserving two links. The compact connected/remaining summary is visible.
- MMR2V accepted an IMAGE then an AUDIO helper as `image_1`, `audio_2`, plus one free
  `reference_3`. The two distinct kinds and order remained visible.
- V2V_EDIT retained connected references and displayed `source_video` first after a reload;
  graph link target slots were remapped with the visual input order.
- Switching a linked IMAGE topology to AR2V was rejected without deleting links. Switching the
  model to one without MI2V support preserved both method and links and displayed INCOMPATIBLE.
- Choosing a supported duration removed the stale duration warning. Structurally ambiguous
  pricing remained `ESTIMATE UNAVAILABLE` rather than inventing a price.

## Open design/acceptance gaps

1. The reference summary remains below the main controls, not directly below the sockets.
   Moving its widget before Model caused positional save/reload corruption in the browser and was
   rolled back immediately; the safe layout is retained pending a non-positional solution.
2. Expanded Advanced controls are native Comfy widgets that appear above their disclosure row,
   rather than nested below it as in the accepted target. This is a visible layout mismatch.
3. Exact maximum-reached presentation at 50 references and exported workflow save/reload were
   not exercised through the browser; a restored browser workspace is weaker evidence.
4. VALIDATING → SUBMITTING → GENERATING → DOWNLOADING → DONE / ERROR and Resume were not
   exercised on the real runtime. Paid Video POST authority remains zero, and synthetic UI states
   cannot be promoted to unmocked acceptance evidence.
5. The required real-mouse browser pass on ComfyUI v0.37.0 has not run. The governed DEV session
   is pinned to v0.34.3; creating a second runtime or changing that pin is outside this pass.

The positional experiment affected the temporary in-app browser autosession for
`02_OPENROUTER_Video_Test`. On explicit Owner approval, the changed named tab and the agent-created
`Unsaved Workflow (2)` QA tab were closed with **Close anyway**; their unsaved values were discarded.
`02_OPENROUTER_Video_Test` was then reopened from ComfyUI's Workflows list at its saved workflow
URL. The exact on-disk file remained unchanged (23,786 bytes, last modified
2026-09-27T14:39:36.9427345Z; 17 nodes and 5 links). ComfyUI marks the reopened legacy workflow
dirty as its current UI projects it, so it must not be saved over the file without a separate
save/reload migration check. The unrelated `Unsaved Workflow` tab was left untouched. The trial
widget-order code is absent from the feature branch; the external Yandex Browser session was not
touched or verified.

A subsequent isolated QA pass tried non-positional summary placement and Advanced display proxies
on a new temporary node. Real-canvas inspection showed an unacceptable blank-height regression
after model selection, so both trial changes were reverted. The temporary QA workflow was closed
without saving. The canonical DEV supervisor reloaded the original source fingerprint
`4e500183b3ca5f16bb1b6e7432b68659b37c5e521e19c61d754cdda5c9f7d2f5` and returned
`RUNNING_HEALTHY`. Design gaps 1–2 therefore remain open; no experimental UI code is in HEAD.

A later draw-only summary trial was also reverted without commit. During its validation, the
scheduled DEV supervisor was observed in `Ready` rather than `Running`; two governed `Ensure`
attempts timed out at `RUNNING_STALE` because no supervisor processed their restart requests.
Restoring the original source returned the existing PID 20520 to `RUNNING_HEALTHY` with the same
original fingerprint. At that point the listener was not stopped, adopted, or replaced, and the
supervisor/orphan-child condition blocked further live browser QA.

With explicit Owner authorization, PID 20520 was revalidated as the sole listener on `8189`
with full restart identity proof and an empty queue, then stopped. The canonical scheduled task
`\OpenRouterVideoBuilder\ComfyUI-DEV-8189` was started and remains `Running`; its new listener
PID 30060 passed governed `Ensure` as `RUNNING_HEALTHY` with the same original source fingerprint,
29 fresh catalogue models, UI capabilities route 200, and zero queued jobs. The saved
`02_OPENROUTER_Video_Test` file remains unchanged at 23,786 bytes and the same modification time.
The browser tab is still marked dirty and displays an invalid duration/resolution warning and an
unavailable cost estimate. Those values belong to the browser autosession and are not evidence of
the unchanged saved file's migration result. Restart alone did not resolve the layout gaps above.
No paid generation or workflow save occurred. Port `8188` and the personal ComfyUI on `C:\` were
not operated.

A focused migration check then reopened the unchanged saved workflow in a fresh browser tab.
It exposed a separate Phase-8 positional restore defect: its saved Prompt was projected as the
numeric Duration. The frontend now restores that legacy remote-options shape by named fields,
including the seed behavior control, while leaving a numeric legacy model selection unresolved
rather than guessing an exact model ID. Two focused Node regression tests pass. On the real
v0.34.3 canvas, reopening the exact saved file after the fix shows its original Prompt text
instead of `5`, and `SELECT MODEL` blocks generation until the user makes an explicit model choice.
The saved file was not overwritten; the temporary migration diagnostic logging was removed.
This improves migration evidence but does not close design gaps 1–5.

Verdict: **Design QA not passed**. Continue the approved Direction 3 implementation; do not
claim RC UX freeze or open a protected-delivery PR as a verified feature yet. Core and deterministic
test passes are separate from this visual verdict.

## Focused continuation — 2026-10-01

This section supersedes the status of gaps 1–3 above without erasing the prior observations.
On canonical v0.34.3 DEV at `127.0.0.1:8189`, the current source fingerprint
`29041798a5da9cf1795986a682b60a8635aaef83056e9ed8b1819bfbd44a735c`
was confirmed `RUNNING_HEALTHY` with a fresh 30-model catalogue and the real
`/openrouter-video/v1/ui-capabilities` route returning 200. No Run/queue action or paid
Video POST occurred.

- Gap 1 is closed in the real canvas: the compact reference summary is directly below the
  sockets, before Model. Named and old positional widget-value migration keep saved intent
  stable after the in-place presentation reorder.
- Gap 2 is closed in the real canvas: Advanced appears after Generate Audio, and its
  advanced-only widgets are below the disclosure when expanded. The primary control rows
  have deliberate spacing; the Prompt has its own dark field treatment. A thin green border
  and a rounded, fail-closed cost badge now match the accepted visual hierarchy.
- The reference socket hit-test defect is closed: a drag from visible `image_1` now offers
  `OPENROUTER_VIDEO_INPUT_REFERENCE`, not a hidden `STRING` widget. Three Public Image URL
  helpers were placed and connected through the real mouse path. The node autogrew to
  `image_4` and showed `3 connected · 47 remaining`. The separate agent-owned
  `ORV_Phase10_QA_20261001` workflow saved and reloaded those three links; the original
  `02_OPENROUTER_Video_Test` file was not overwritten.
- Exact 50-reference browser saturation remains untested. The max-capacity rule has
  deterministic coverage, but that is not a substitute for the specified visual state.
- Live lifecycle/Resume remains blocked by the zero-paid-POST boundary. v0.37.0 browser
  verification remains unrun because the governed DEV runtime is pinned to v0.34.3.

The approved target uses an illustrative price. The real Seedance topology still displays
`ESTIMATE UNAVAILABLE`, correctly following the pricing contract rather than fabricating
the target's example number. The target's decorative `READY` idle footer is omitted per
the semantic visual specification, which explicitly hides idle lifecycle.

Current verdict: **PARTIAL / BLOCKED for full Design QA**. The primary MI2V presentation
and save/reload of three connected references were visually verified; max-reached, real
lifecycle/Resume, second-version browser matrix, and Product Owner implementation acceptance
remain open. This is not RC UX freeze or release readiness.
