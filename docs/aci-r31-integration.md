# ACI v1.0 R3.1 engineering integration

Owner authority: ACI-04 R3.1 final engineering execution against
`15cc5aea7570fe43d2154b4e3b6f1efba8f4ac2d`. The supplied archive is authoritative;
its 34 manifest entries and seven baseline/reference source hashes were verified.
The cumulative reference patch was applied once, without stacking R1/R2/R3.

## Bounded implementation contract

The existing estimator, profile compiler, arithmetic and tariff resource remain
the only pricing path. The approved bounded planning module projects conditional
quantities through that same arithmetic. MODELLED, SCENARIO_RANGE, comparisons
and components remain separate from primary money fields and usage.cost ACTUAL.
No new model capabilities, generation validation, routing, billing authority,
calibration, job store, dependency or telemetry is introduced.

Native media costing uses the complete ordered active occurrence inventory;
duplicates count independently, parked/detached media do not contribute. Native
preview quantities are HINTs bound to occurrence and current context revision.
Missing/stale quantities remain unknown, and client effective billed duration
is not authoritative. Estimation never executes the graph or reads/uploads media.

The existing cost presentation uses the approved ARENASlab tokens: Green
`#0ACF83`, Yellow `#FFBB00`, Violet `#9E6BFF`, Black `#1A1A1A`. Neutral states,
node chrome, dimensions, widgets, graph intent and serialization remain protected.
Server catalogue freshness and request elapsed time bound presentation; delayed
timers cannot make an expired numeric price current again.

Terminal adapter UI metadata is sourced only from the existing successful
GenerationResult job/model/actual_cost_usd. The six existing positional outputs
and authoritative durable cost path remain unchanged. Resume checks its exact
requested job before exposing auxiliary metadata. Frontend receipt ownership is
execution-local and in memory, separate from current estimate/configuration.
Ambiguous, contradictory, malformed, removed or reloaded associations fail closed.
There is no new persistence or workflow field for cost receipts.

Only a passive observer of the public native queue API may associate the returned
host prompt ID with an immutable graph/node dispatch snapshot. It must call the
original exactly once with the same receiver/arguments, return the original
result/promise and preserve errors. It never initiates Queue or changes a request.
Private host stores and a mutable node-ID lookup alone are not ownership proof.

## Protected progress and evidence

The fresh canonical unauthenticated no-redirect GET on 2026-11-14 returned the
same catalogue bytes as the handoff: 32 models, 121 SKU occurrences, 55 distinct
keys and 124 executable method witnesses. Snapshot SHA256:
`bf1fca47bae64affda204db60698244f22fceaf3623b92917d914958c7d4ec12`.
These are fixed-snapshot counts, never immutable catalogue or capability limits.

Historical accepted evidence and literal mathematical goldens are retained.
Separate UNACCEPTED source pins let historical assertions inspect their original
version, while direct current-source guards and Product Contract Guard verify the
R3.1 delta. Pins are not acceptance. Primary, planning, component/comparison and
synthetic known-quantity coverage use separate denominators and classifications.

The final full regression exposed an additional financial boundary: a generic
legacy per-second rate cannot identify the applicable duration-conditioned SKU.
The existing bridge now refuses that unsupported alias when otherwise applicable
formula cases have different charge plans across duration. Documented current
short/long calculations remain available; unchanged-plan legacy callers remain
compatible. No model-name or current-rate exception is introduced. Original full
run logs are retained; only affected pricing, fixtures and source guards are rerun.

The previous embedded/external installation manifest differed only by Windows
CRLF expansion of the external text file; parsed JSON was equal. The original
bundle remains unchanged. New bundle assembly must serialize the manifest once
and write identical bytes externally and inside the ZIP; detached checksums are
generated from the final immutable bytes.

## Qualification boundary

Reference checks, offline host API inspection, mocked execution events and source
parity do not establish real browser/runtime acceptance. Prepare one final full
regression and exact reproducible private TEST artifact with verified rollback.
No TEST/DEV/PROD mutation, paid inference, OAuth, S3, push, merge, tag or publication
is authorized. Stop before installation; real Classic/Nodes 2.0 and native ACTUAL
acceptance require the separately authorized runtime step. No Public Beta PASS.

NEXUS compilation selected red-team; native kernel binding remains pending after
the official existing-worktree attach reported an unmanaged checkout. Actual
native engineering/review roles continue as HOST_NATIVE_UNBOUND, without a claim
of compiled NEXUS acceptance or a fabricated binding.
