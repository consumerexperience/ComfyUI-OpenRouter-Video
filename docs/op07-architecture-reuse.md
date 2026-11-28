# OP-07 Architecture Reuse & Duplication Assessment

Owner authority: architectural correction 8fad0a0c, 2026-11-09.
Baseline: 058f5bcdd462a2a71f4f85151d9bbba3bc09bcf9.
Prior implementation: cddf3318d7ac7cd81f341362243db7d850f2834e.

## Implemented architectural correction

The selectable-method feasibility calculation now belongs to existing
`capabilities.py`. `eligibility.py` is a compatibility import facade, with no
implementation, data store, cache, or provider table. The Comfy projection imports
Core directly. Existing request validation, serialization, projection profiles,
legacy recipe compatibility, and all effective model values remain unchanged.
This is service ownership consolidation, not a claim that the former module was
an independent registry. No new supported capability is promoted by this change.

| Existing component | Treatment | Reason | Compatibility | Duplicate risk |
|---|---|---|---|---|
| Video catalogue / CapabilityService | Reused | Model membership and fresh/LKG observations | Unchanged | No second discovery source |
| evidence_registry.py / capability-evidence.json | Reused | Reviewed exact-ID enrichment and provenance | Data unchanged in this correction | One runtime evidence manifest |
| configuration.py | Reused | Method shapes, scalar domains, topology, relations | Unchanged | No new shape validator |
| capabilities.py / RequestValidator | Extended | Own derived serializable-method feasibility | Old validation remains identical | No separate feasibility service implementation |
| eligibility.py | Replaced with compatibility facade | Preserve imports without a second implementation | Same function objects | None; regression assertion checks identity |
| Comfy projection / routes | Reused | Presentation derives from Core | Existing selectable behavior preserved | No UI registry |
| frontend | Reused | One backend projection for both renderer paths | No JS change in correction | No provider-specific frontend truth added |
| historical audits / matrices / fixtures | Preserved | Verification and chronology only | Accepted files not regenerated | Not runtime inputs |
| Product Contract Guard | Extended declared delta | Source relocation touches existing Core service | Frozen baseline unchanged | No accepted golden rewrite |

The conceptual legacy method matrix and reviewed public request-shape projection
have distinct contracts. An attempted wholesale replacement exposed five
regressions (including activation of unreviewed models). It was not retained.
The corrected implementation preserves both existing contracts and uses the
same validator/serializer for feasibility; 526 Python tests subsequently pass.

## Functional completeness remains open

This architectural correction does not expand the two narrow Google profiles.
It does not restore the eight hidden models. The previous broad DONE statement
is superseded: full model parity is NOT achieved. A passing relocation test does
not constitute coverage, real-browser qualification, or Owner acceptance.

Current public API references confirm existing-schema extension points:
- https://openrouter.ai/docs/api/api-reference/video-generation/submit-a-video-generation-request
- https://openrouter.ai/docs/cookbook/video-generation/provider-specific-video-options
- https://openrouter.ai/google/gemini-omni-1.2-flash

The API documents continuation, upscaling controls and provider options. These
are integration work still to implement, not evidence that the existing
adapter already represents them. Exact model operation selection, provider
passthrough domains and method-specific restrictions require further contract
reconciliation. The currently unresolved Kling size conflict is retained.
No unsupported capability is promoted to close those gaps.

## NEXUS execution evidence and limitation

Task compiled; one native investigator requested with gpt-6-luna / medium.
Model selection is requested, not runtime-confirmed. Model policy also selects
Sol / low for red-team and arena. No evaluator verdict is claimed.
Run: op07-reuse-20261109. Native bind returned
NATIVE_THREAD_EVIDENCE_MISMATCH. Parent thread cwd is the OPENROUTER workspace;
run project is its product worktree. The error and checkpoint are retained;
no fabricated bind, reply acceptance or successful kernel run is asserted.
The source correction was performed by the controlling host under Owner's
implementation authority, not by a NEXUS PROJECT_WRITE grant.

## Verification and boundaries

- Full Python: 526 passed, 3 skipped (unmaterialized third-party media).
- Focused refresh / scope frontend: 8 passed; frontend source unchanged.
- Ruff, formatting and mypy src: PASS.
- Product Contract Guard: PASS; unauthorized delta zero.
- TEST, DEV, PROD, RC, credentials, ACL, paid calls and publishing: untouched.
- Classic/Nodes2 live, native workflow roundtrip: NOT VERIFIED for this patch.

Status: architecture consolidation verified; FULL FEATURE PARITY incomplete.
