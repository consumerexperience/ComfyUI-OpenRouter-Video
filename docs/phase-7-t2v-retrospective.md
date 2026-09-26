# Phase 7 Text-to-Video retrospective evidence

## Evidence status

```text
RECONSTRUCTED / PRODUCT-OWNER-ATTESTED
```

The original complete evidence bundle is not present in the Phase-8 canonical repository. This
record preserves the facts that remain available without pretending that missing raw evidence was
independently reconstructed.

## Known facts

- Canonical main observed before the run:
  `e4b116a88147d19fa69e376a8b1873593fe784b8`.
- Model: `alibaba/wan-3.0`.
- Exactly one paid Generate submit occurred.
- The path completed through Generate, Core, RequestPolicy, polling, canonical content retrieval,
  durable MP4, native Comfy `VIDEO`, and `SaveVideo`.
- Engineering verdict: `UPSTREAM E2E LIVE VERIFIED` for Text-to-Video.
- Attribution: `ATTRIBUTION_SENT` and `ATTRIBUTION_REQUEST_ACCEPTED` are attested.
- `ATTRIBUTION_SURFACED`: `UNKNOWN / NOT OBSERVED`.
- Actual `usage.cost`: `UNKNOWN`.

## Evidence limits

The unavailable original bundle prevents independent reconstruction of every timestamp, raw
sanitized response, media hash, and actual-cost field. Missing cost or attribution surfacing does
not invalidate the engineering E2E result and must not trigger another inference.

## Applicability rule

This evidence remains applicable unless Phase 9 materially changes the shared submit path, request
serialization, lifecycle/state machine, content retrieval, native `VIDEO` conversion, or
`SaveVideo` handoff. Such a change requires an evidence-impact assessment. A new T2V generation is
not part of the five-case campaign and requires separate Product Owner approval and budget.
