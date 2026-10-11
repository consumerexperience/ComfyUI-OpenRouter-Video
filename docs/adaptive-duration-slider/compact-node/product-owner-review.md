# Compact node: Product Owner visual review

Status: READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW.
Implementation head: 408fb6de18e935c566c850252c3c93b9ce0b8e6e.
Pre-iteration head: a86df3bb825a04bc2852966b69ce65848b22de3b.
Accepted parent: 8ec71ba94575f8b02105a0cd0e5feba7d7083b87.
Branch: feature/adaptive-duration-slider. Final evidence commit follows this report; no source changes follow the verified implementation head.

Implemented compact whole-node presentation and explicitly authorized primary defaults. Width400, native rectangular Duration row20, standard gap4, section gap8, rendered Prompt42. Reference measured from installed ByteDance Seedance2.5 Reference to Video at100%: width403.015625, native row20, Prompt42. Width difference -3.015625 meets +/-8. See measurement-and-spec.md and reference-object-info.json.

Resolution prefers supported720p, otherwise the lowest canonical confirmed option. Aspect chooses the supported numeric ratio closest to16:9. Duration chooses the lowest supported value. Valid selections survive model/method switches; invalid selections resolve supported defaults. Legacy AUTO resolves explicit primary values. Current OpenRouter projection exposes no confirmed upstream-default fields; reference default5 is not borrowed. Unknown capabilities remain fail-closed. Size stays visible, optional and blank; control after generate stays visible. Advanced has no visible disclosure. Native duration interaction maps slider positions to real seconds; workflow persistence stores seconds and primary values, never slider indexes.

DEFAULT_SELECTION_WIRE_SEMANTICS_CHANGED=YES
CAPABILITY_DOMAINS_CHANGED=NO
UNAUTHORIZED_DELTA_COUNT=0
OPENROUTER_PAID_POST_COUNT=0

Verification: Python379 passed/3 skipped (existing unmaterialized Golden Pack media); frontend56 passed; Ruff check and format PASS; Mypy src+tests96 files PASS; isolated wheel/sdist build PASS. Initial no-isolation build lacked setuptools backend in the working venv; retained failure log and successful isolated-build log. The Python regression used the accepted parent contract-delta selector. No accepted goldens were rewritten. Old presentation-only AUTO assertions were replaced for the authorized explicit-default policy; capability, ordering, coupling, migration and protected-source checks remain covered.

Semantic diff PASS: six authorized default-policy replacements, zero unauthorized changes, no unknown surfaces. The existing exporter does not represent defaults; the verification helper adds an explicit before/after policy surface bound to source presence, with behavioral frontend tests. Raw contracts, diff, logs and released regression/build-browser lease receipts are in verification/. Final exact-head browser capture has before/after ACTIVE lease checks. An earlier browser-marker timeout was recovered only after its owner process ended; final controlled run completed and released.

Live DEV8189 revalidation: RUNNING_HEALTHY, PID20896, UI contract4, authenticated catalogue FRESH30 models; source fingerprint d76e64b0b0c7b6809fc68d3e5beb59771e3745a7879878535783ab0b44f0c737. Paid generation was not invoked; this is local/contract/UI proof, not paid provider-generation proof. Live dense domain4..30;1..30 is a fixture only.

Visual evidence:01 fresh node;02 same-zoom side-by-side;03 Resolution default;04 Aspect default;05/05b sparse two values;06/06b sparse three values;07 dense default;08 model switch;09 Size;10 control after generate;11 legacy migration;12 save/reload. Final verification/verified-head-browser.png shows verified head and restored Veo8s,720p,16:9,blank Size. Earlier migration capture predates final Prompt-height correction; final capture establishes current layout. explicit-saved-workflow.json and fresh-saved-workflow.json come from actual native Save; legacy-auto-review.json is a prepared input loaded through the native file chooser.

REQUEST_STATUS=DONE
PRODUCT_STATE=READY_FOR_PRODUCT_OWNER_VISUAL_REVIEW
ACCEPTANCE_STATE=CONTRACT_DELTA_REQUIRED; candidate explicit-default delta supplied, exact-head Owner acceptance pending
DELIVERY_STATE=LOCAL_FEATURE_COMMITTED
CANONICAL_STATE=UNCHANGED
SEMANTIC_DIFF=PASS
UNAUTHORIZED_DELTA=NONE
CONTRACT_DRIFT=NONE_DETECTED_IN_BOUNDED_CHECKS
UPSTREAM_EXPANSION=NONE
VERIFICATION_STATE=TECHNICAL_PASS; VISUAL_OWNER_PENDING
SIDE_EFFECTS=frontend deployed to canonical DEV source through existing junction; controlled DEV restarts; local review workflows and evidence; local commits
OPEN_GATES=Product Owner visual and explicit-default contract acceptance; protected delivery remains separate
NEXT_ACTION=Review the retained side-by-side browser scene and this candidate

No merge, tag, release, push or paid submit. Production code changes are confined to web/openrouter_video.js; capability domains, Python production source, credentials, attribution, Generate/Resume and paid retry invariants are preserved. DEV8188 was not touched.

Короткий лог для трекера: выполнена компактная компоновка OpenRouter Video Generate по установленному ByteDance-референсу; штатный Duration slider, явные поддерживаемые defaults, миграция AUTO, видимые Size/control after generate. Проверки379 Python+56 frontend, Ruff/Mypy/build PASS; semantic unauthorized0, paid POST0. Код408fb6d. Готово к визуальной проверке владельцем продукта; merge/release не выполнялись. Исходный пользовательский промт не изменён.
