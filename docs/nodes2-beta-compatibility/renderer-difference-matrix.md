# Renderer difference matrix — audit before patches

Baseline e89b513da94ec74640ecff15f227e675bbc75533; canonical DEV8189, installed frontend1.49.6. Classic/Nodes2 toggled through native settings; no source edits at audit. Evidence screenshots before stored in TEMP then included in review package.

|Surface|Classic current|Beta current|Target|Root cause / source owner|Fix strategy|
|---|---|---|---|---|---|
|Header|Canvas title + estimate|Vue title only|Header estimate both|Vue bypasses onDrawForeground / Comfy frontend|Scoped header-flow adapter; native pricing API is credits/price_badge only, generic badges footer|
|Cost Estimate|Header, hidden COST backing widget|COST body row|One header presentation|item.hidden not projected; useProcessedWidgets reads options.hidden|Estimate state plain non-widget; no pricing calculation edits|
|Inputs|Method-dependent sockets|Sockets + advanced URL fields|Socket only|first_frame_url/last_frame_url STRING advanced aliases; distinct native union media inputs|options.hidden for retained legacy widgets; keep backend and saved values|
|Outputs|5 native outputs|5 native outputs|Preserve|No defect|No edit|
|Model|Native combo|Native combo|Preserve domain/values|No semantic defect|Shared native widget|
|Inference Method|Native combo|Native combo|Preserve native topological engine|No semantic defect|Same callbacks|
|Prompt|DOM textarea42 minimum|Native textarea larger default|Flex/editing both|Beta native textarea/grid; Classic computeSize not used by Vue|Native Vue grid flex row plus scoped density|
|Resolution|Explicit combo|Explicit combo|Preserve|No semantic defect|No domain edit|
|Aspect Ratio|Explicit combo|Explicit combo|Preserve|No semantic defect|No domain edit|
|Duration|Native indexed visual adapter, seconds state|Native slider/store semantic seconds|Supported values only|Vue store callback/setter path needs audit|Retain shared snapping; deterministic irregular sparse tests|
|Seed|-1 + workflow control|Native numeric -1 + embedded randomize|Preserve|Vue renders linked CAG inline|Retain native semantics; deliberate discoverability|
|Generate Audio|Native toggle|Native switch|Preserve|No semantic defect|No edit|
|Size|Visible optional blank|Advanced-only optional blank|Deliberate optional Exact Size|Schema advanced flag; frontend Classic ignores widget.options.advanced|Primary options advanced=false; retain conservative unknown-relation policy|
|control after generate|Visible native combo|Seed native randomize button|Discoverable current policy|Vue owns native linked control affordance|Expose same control policy; no value change|
|Advanced inputs|No Advanced button|Advanced backing button + legacy URL forms|No backing fields|Visibility dialect mismatch|Synchronize item.hidden/options.hidden; options advanced deliberate|
|Blank before Model|REFERENCES hidden when empty|Empty REFERENCES text field|Absent when empty|name REFERENCES, type text, serialize=false, source addReadOnlyWidget + __orvSummary; INTERNAL_BACKING_STATE|options.hidden synchronization, read-only label when valid summary|
|Additional blank before COST|STATE hidden|Empty STATE text field|No empty internal state|name STATE, type text, serialize=false, __orvCapabilityStatus|options.hidden; use readonly intentional disclosure only when needed|
|Responsive Prompt|Height delta all into Prompt|Requires runtime resize audit|Equivalent behavior|Vue native grid uses auto row; body intrinsic defaults|Scope grid density and native flex sizing|
|Node width|400 graph px|400 graph px but minimum CSS|Similar native density|Native min-width + labels|Preserve400, no geometry forced per provider|
|Node height|Native content minimum + flexible delta|Intrinsic native Vue measured by ResizeObserver|Safe minimum and flex|Different native size ownership|Avoid observer resize loops; native CSS grid flex|
|Save/reload|Named migration + semantic positional slots|Same serialized LGraphNode state|Four cross-mode paths|No renderer property must be serialized|Native Save/read-back tests|

## Beta reactive metadata finding
Installed BaseWidget registers its initial options object in WidgetValueStore. Replacing widget.options detaches reactive metadata: Duration stayed 0..1, and advanced/hidden flags remained stale. Mutate the retained options object with Object.assign; do not import or write private Vue stores. Real fresh-page Beta shows Google Veo 3.1, supported Duration 8; typing 7 snaps to 6. Opening Advanced no longer exposes legacy URL form fields.

Beta numeric blur also clamped the accepted seed -1 sentinel to 0. Presentation restores native seed min -1, exactly matching backend schema and _seed(-1) => None; no wire/parser change. The first test run was stopped before acceptance and superseded by a fresh run.
