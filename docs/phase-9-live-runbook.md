# Phase 9 controlled live-validation runbook

## Authorization boundary

This runbook does not authorize paid execution. Every paid POST requires immediate Product Owner
approval after all preconditions below are read back. The human creates, caps, injects, and launches
the key-bearing process. Codex must not request, read, print, persist, enumerate, inject, or launch
with the credential.

Campaign maximum:

```text
generation POSTs: 5
hard key/campaign cap: $2.00
automatic retry: forbidden
```

Use a fresh dedicated key with starting spend `0` or explicitly reconciled spend and a non-resetting
`$2.00` limit where supported.

## Frozen matrix

Every case uses `duration=4`, `resolution=480p`, `aspect_ratio=16:9`, and
`generate_audio=false`.

| Case | Case ID / exact reference mode | Model | Inputs |
| --- | --- | --- | --- |
| First Frame | `first_frame` / `first_frame` | `bytedance/seedance-2.0-mini` | `first-frame.png` |
| First + Last Frame | `first_plus_last` / `first_plus_last` | `bytedance/seedance-2.0-mini` | `first-frame.png`, `last-frame.png` |
| Multi Image Reference | `multi_image_reference` / `multi_image_reference` | `bytedance/seedance-2.5` | ordered `first-frame.png`, `style-marker.png` |
| Video Reference | `video_reference` / `video_reference` | `bytedance/seedance-2.5` | `motion-reference.mp4` |
| Image + Video References | `image_plus_video_reference` / `image_plus_video_reference` | `bytedance/seedance-2.5` | ordered `style-marker.png`, `motion-reference.mp4` |

The exact prompt paths and hashes live in `tests/live/fixtures/phase9/manifest.json`.

## Before each paid POST

1. Confirm the frozen RC commit and UX are unchanged.
2. Refresh `GET /api/v1/videos/models` without credentials.
3. Positively re-authorize the exact model, reference shape/count, duration, resolution, aspect
   ratio, and `generate_audio=false` from effective Core evidence.
4. Confirm no Level-A/overlay conflict.
5. Confirm every commit-addressed fixture and prompt URL passed anonymous HTTP/MIME/hash/redirect
   checks against the exact RC commit.
6. Confirm local and remote fixture hashes match the frozen manifest.
7. Confirm remaining POST count and remaining hard budget.
8. Run the side-effect-free `PreflightCostEstimate` for the exact case.
9. If the estimate is unavailable, show that state explicitly; never invent a number.
10. Obtain immediate Product Owner approval for this one POST.

If any exact planned value is unsupported, stop before POST. Do not choose `AUTO`, another value,
another model, or another reference mode.

## Runtime evidence

Record independently:

```text
REQUEST_SENT
REQUEST_ACCEPTED
REMOTE_COMPLETED
CONTENT_RETRIEVED
NATIVE_VIDEO_CREATED
OUTPUT_SURFACED_IN_COMFY
SAVEVIDEO_SUCCEEDED
```

Also record:

```text
UPSTREAM E2E LIVE VERIFIED
CONDITIONING OBSERVATION = PASS | INCONCLUSIVE | ANOMALOUS
```

Poor artistic quality is not an engineering failure. A strong contradiction to documented
conditioning semantics is `ANOMALOUS` and triggers contract-drift investigation.

Attribution uses separate states:

```text
ATTRIBUTION_SENT
ATTRIBUTION_REQUEST_ACCEPTED
ATTRIBUTION_SURFACED
```

Unobserved surfacing is `UNKNOWN / NOT OBSERVED`, not engineering failure.

## Recovery

- Ambiguous submit: `SUBMISSION_UNKNOWN`; stop campaign; no second POST.
- Terminal remote failure: preserve evidence; pause; RCA; no campaign retry.
- Poll failure after accepted `job_id`: same-job Resume/observe; zero generation POST.
- Download/native/local-write/SaveVideo failure: same-job retrieval/local recovery where safe;
  zero generation POST.
- Missing `usage.cost`: `ACTUAL_COST=UNKNOWN`; do not regenerate.
- Poor conditioning: classify; do not regenerate.

Any new generation-based diagnostic requires a new approval and budget envelope.
