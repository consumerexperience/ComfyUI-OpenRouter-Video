# Final geometry UX polish

PRE_HEAD: 9cc3cef7ecfa85ccd8a6ef378994add864c3d9fe
POST_HEAD: reported in final delivery for the commit containing this evidence.
GEOMETRY_MODEL: BIDIRECTIONAL_SYNCHRONIZED (unchanged)

STALE_RESOLUTION_FALSE_ASSOCIATION: 0
RESOLUTION_ROW_ALWAYS_VISIBLE_WHEN_SUPPORTED: PASS
UNKNOWN_RELATION_DISPLAY: PASS
NORMALIZED_WIRE: PASS
EXACT_WIRE: PASS
TRIPLE_GEOMETRY_SERIALIZATION: 0
CLASSIC: PASS
NODES2_BETA: PASS
UNAUTHORIZED_SEMANTIC_DELTA: 0
OPENROUTER_PAID_POST_COUNT: 0
RESULT: READY_FOR_FINAL_PRODUCT_OWNER_ACCEPTANCE

Exact Size without a confirmed Resolution tuple now sets Resolution to the selectable em dash. The resolution-only sentinel normalizes to null for UI projection. Confirmed full tuples continue to set/preserve the proven Resolution normally. Selecting a real Resolution invokes the existing NORMALIZED authority callback, preserves compatible aspect and clears an unconfirmed Size. No AUTO/default relation is introduced.

Only web/openrouter_video.js production source changed: configureGeometry and resolution-specific null normalization. Backend, relation engine, reviewed evidence, wire builder, duration, pricing, media and authority model are unchanged. A focused immediate-baseline negative-space test compares every other frontend function against 9cc3cef. The task Contract Delta permits only this one frontend semantic surface; semantic guard PASS with zero unauthorized delta. All 30 live model geometry/duration domains and profiles compare equal with the prior candidate evidence.

Validation: 391 Python tests passed (3 existing unmaterialized Golden Pack media skips); 84 frontend tests passed, including all five requested behaviors. Native Beta and Classic screenshots demonstrate em dash/4:3/1112x834/Duration8. Real Resolution selection in Beta produces 720p/NORMALIZED/blank Size; Classic selection produces 480p/NORMALIZED/blank Size. Native saved workflow JSON confirms authority, aspect, size, duration and seed. EXACT native save/reload verified Beta to Classic and Classic to Beta. Confirmed tier synchronization remains fixture-proven because current live evidence contains no complete confirmed tier tuples.

DEV 8189 RUNNING_HEALTHY; installed frontend bytes equal tested branch source. Fresh browser tab was required to load updated extension code; prior tab retained a cached module. No paid generation, merge, tag or release. Canonical main was not changed. Cooperative source acceptance lease was checked before and after tests/browser/evidence and released intact before local commit.

Screenshots and native workflow files: [evidence](evidence/). Final view: [Beta](evidence/Beta-classic-exact-reload.png); [Classic](evidence/Classic-exact-reload.png). Native readback: [JSON](native-readback.json).
