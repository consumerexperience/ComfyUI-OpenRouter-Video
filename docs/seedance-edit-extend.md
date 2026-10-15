# Seedance 2.5 Edit / Extend correction

Owner authority: attachment `3db6f7d9-11b1-4874-9ac4-1d9a063c67ab`, 2026-10-15.
Starting visually reviewed candidate: `4c460cc851c047eb941e17bc22f2d0c93a3a83df`.
Canonical baseline: `adaptive-duration-slider-v1`, peeled
`f9c19c669735d08fc12b5460eaf2198cdde2d714`.

## Control handoff

The authorized semantic delta is limited to exact `bytedance/seedance-2.5`
V2V_EDIT and V2V_EXTEND reviewed request profiles. OpenRouter first-party
documentation explicitly supports editing and continuation through VIDEO
references, with the prompt defining intent:
[OpenRouter review](https://openrouter.ai/blog/insights/seedance-2-5-review/).
[Video API](https://openrouter.ai/docs/guides/overview/multimodal/video-generation)
confirms that frame_images take precedence. These are documented contracts,
not new successful inference observations.

Both methods use the existing required source_video semantic socket. The
existing serializer prepends it to input_references as video_url. No mode,
method, inference_method, source_role or source_video wire field is introduced.
First/last frames are omitted and rejected by validation when submitted.

Additional IMAGE/VIDEO/AUDIO references follow the existing reviewed mixed
reference subset. Topology bounds describe optional references, excluding the
required source: min0/max49, image30/video9/audio10. Including the source gives
the unchanged aggregate50/image30/video10/audio10 limits. Empty optional sets
are valid; missing source remains invalid. This uses existing topology vocabulary.

Controls reuse the confirmed reference-shape profile, not the T2V profile:
finite duration 4..30, resolution480p/720p, reviewed aspects, UNKNOWN exact size
and Seed, generated audio separate from AUDIO input. Dynamic catalogue domains
still intersect the reviewed subset. No new geometry relations are inferred.

Classic and Nodes2 consume the same normalized profile, native widgets and
socket registration. Existing accepted layout tokens, dimensions, order,
responsive behavior and selector styling remain unchanged. Existing named
semantic persistence and park/reproject/restore link behavior apply. Other
models, VR2V, MMR2V, AR2V conflicts, pricing formulas, credential policy,
AppIdentity, storage, Generate/Resume and one-POST invariants are protected.

OpenRouter Draft is UNKNOWN and has no public projection. Provider-native
Draft is outside this product correction; no provider-native workflow is added.

The existing reconciliation delta remains cumulative against canonical main.
CI now uses the same baseline and delta as local verification. Historical
accepted exports and audit observations are preserved.

Verification must cover both methods, required VIDEO, optional limits, frame
exclusion, serializer omission, other-model negative space, frontend switching,
save/reload, estimator reference pricing and semantic guards. Targeted visual
review requires Edit, Extend and the method dropdown in each renderer.
Product Owner acceptance and all protected delivery remain pending.

## Observed verification

- CI-configured local Python suite: 451 passed, 3 optional third-party media skips.
- Complete frontend suite: 130 passed. Ruff, formatting and mypy passed.
- Build produced sdist and wheel; dependency audit found no known vulnerabilities.
- Full source and node-UX guards: PASS, unauthorized semantic delta0. The
  independent manifest negative-space test reconstructs the previous content
  hash after removing precisely the two authorized profiles and their scope note.
- Canonical supervised DEV restart: RUNNING_HEALTHY, 30 fresh catalogue models,
  fingerprint `1be9f7ce42594c3f5f454bae1f189f5f2ef3d14fc66da67aead60db801d584a7`.
- Both renderers displayed Edit/Extend, required source_video and optional
  references without frame sockets. Dropdowns retain VR2V/MMR2V and hide Draft.
- Both Edit and Extend survived full browser reload. A real native Load Video
  link survived reload and restored after model switch and explicit Edit reselection.
  On return, the existing supported-method fallback remains selected until the
  user reselects Edit/Extend; no new automatic method restoration is introduced.
- Estimator matches existing VR2V reference semantics, including conservative
  UNAVAILABLE when input charges cannot be bounded. No numeric estimate or SKU
  was invented. This is estimator parity, not provider billing validation.
- No Queue/Run or paid generation was executed. Read-only ledger still has the
  previous8 jobs and zero staging_objects. No push/merge/tag/release or PR28 mutation.

[Six targeted screenshots](../contracts/product/evidence/seedance-edit-extend-20261015/review.md),
[machine-readable result](../contracts/product/evidence/seedance-edit-extend-20261015/result.json),
[verification](../contracts/product/evidence/seedance-edit-extend-20261015/verification.json).

The remote CI service was not triggered because push is explicitly forbidden.
CI_CONFIGURED_CONTRACT_TESTS means the local tests used the exact baseline/delta
paths parsed from the committed CI configuration. Product Owner visual acceptance
remains pending; next gate is PRODUCT_OWNER_TARGETED_VISUAL_REVIEW.
