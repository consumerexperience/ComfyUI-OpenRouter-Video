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
`02_OPENROUTER_Video_Test`; its original unsaved browser values cannot be reconstructed with
confidence. The exact on-disk saved workflow was not written (last modified 2026-09-27). The
trial code is absent from the feature branch. Do not save the altered in-app autosession over
the saved file; the external Yandex Browser session was not touched or verified.

Verdict: **Design QA not passed**. Continue the approved Direction 3 implementation; do not
claim RC UX freeze or open a protected-delivery PR as a verified feature yet. Core and deterministic
test passes are separate from this visual verdict.
