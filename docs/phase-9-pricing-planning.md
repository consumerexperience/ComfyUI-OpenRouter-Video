# Phase 9 pricing planning record

The following values are planning allowances until their original source rates and unrounded
calculations are reconstructed. They are not runtime pricing authority.

| Case | Exact configuration | Planning allowance |
| --- | --- | ---: |
| First Frame | Seedance 2.0 Mini; 4 s; 480p; 16:9; audio off | about `$0.14` |
| First + Last Frame | Seedance 2.0 Mini; 4 s; 480p; 16:9; audio off | about `$0.14` |
| Multi Image Reference | Seedance 2.5; 4 s; 480p; 16:9; audio off | about `$0.42` |
| Video Reference | Seedance 2.5; 4 s; 480p; 16:9; audio off | about `$0.25` |
| Image + Video References | Seedance 2.5; 4 s; 480p; 16:9; audio off | about `$0.25` |

Planning catalogue observation: `2026-09-26T19:54:44.1434713Z`.

The snapshot observed 29 models, 37 distinct pricing keys, 20 distinct pricing shapes, and a
catalogue resolution value `768p`. The source rate/SKU evidence and unrounded calculations for the
displayed allowances are not present in the canonical baseline, so these rows are intentionally
labelled allowances rather than evidence.

Immediately before each paid POST, Core must refresh catalogue pricing evidence and return either a
prepared `AVAILABLE` estimate with provenance or `UNAVAILABLE`. The hard `$2.00` key/campaign cap
and five-POST limit remain authoritative regardless of estimate availability. Completed-job
`usage.cost`, when returned, is the sole authoritative actual cost.
