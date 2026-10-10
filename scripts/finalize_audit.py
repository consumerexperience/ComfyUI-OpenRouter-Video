# ruff: noqa: E501
# Source-faithful audit prose is emitted as complete Markdown lines.
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "docs/capability-audit"
live = json.loads((root / "live-catalogue.json").read_text())
models = live["payload"]["data"]
pages = json.loads((root / "official-page-profiles.json").read_text())
product = json.loads((root / "current-product.json").read_text())
facts = json.loads((root / "semantic-comparison.json").read_text())
facts = [f for f in facts if f.get("source") == "LIVE_STRUCTURED_API"]
observed = live["observed_at"]


def add(slug, cap, value, exposure, status, url, authority="EXACT_OFFICIAL_MODEL_PAGE"):
    facts.append(
        dict(
            exact_model_id=slug,
            capability=cap,
            value=value,
            current_product_exposure=exposure,
            status=status,
            source_url=url,
            observed_at=observed,
            authority=authority,
        )
    )


for fact in facts:
    if fact["capability"] == "pricing_skus":
        fact["status"] = "UNDEREXPOSED"
        fact["current_product_exposure"] = (
            "SKU evidence retained; estimator supports only generate/per-second simple families; native video/audio explicitly unavailable"
        )
    elif fact["capability"] == "allowed_passthrough_parameters" and fact["value"]:
        fact["status"] = "MISSING"
        fact["current_product_exposure"] = "No typed provider controls or payload passthrough"
under = set()
for model in models:
    slug = model["id"]
    page = next(p for p in pages if p["exact_model_id"] == slug)
    p = next(m for m in product["models"] if m["model_id"] == slug)
    description = page["description"].lower()
    url = page["source_url"]
    if model["allowed_passthrough_parameters"]:
        under.add(slug)
    # Exact documented operation evidence; modality alone is not reference proof.
    for phrase, cap, mode in [
        ("multimodal reference-to-video", "multimodal_references", "MMR2V"),
        ("set of image, video, and audio references", "multimodal_references", "MMR2V"),
        ("set of reference images", "multiple_image_references", "MI2V"),
        ("multiple reference images", "multiple_image_references", "MI2V"),
        ("up to seven reference images", "multiple_image_references", "MI2V"),
        ("video continuation workflows", "continuation", "V2V_EXTEND"),
        ("video editing model", "editing", "V2V_EDIT"),
        ("source video and an edit prompt", "editing", "V2V_EDIT"),
        ("video-to-video motion transfer", "motion_transfer", None),
        ("scene extension", "extension", "V2V_EXTEND"),
    ]:
        if phrase in description:
            ready = mode in p["supported_inference_methods"] if mode else False
            add(
                slug,
                cap,
                True,
                mode if ready else "NOT_EXPOSED",
                "CORRECT" if ready else ("UNMAPPED_CAPABILITY" if mode is None else "MISSING"),
                url,
            )
            if not ready:
                under.add(slug)
    for cap in (
        "prompt_constraints",
        "reference_order_contract",
        "duplicate_reference_contract",
        "minimum_reference_count",
        "maximum_by_kind",
        "source_media_precedence",
        "output_formats",
        "fps",
        "provider_availability",
    ):
        add(slug, cap, None, None, "UNKNOWN_UPSTREAM", url)
over = [
    "black-forest-labs/flux-video-edit",
    "black-forest-labs/flux-video-upscale",
    "runway/aleph-2",
    "heygen/avatar-iv",
]
for slug in over:
    add(
        slug,
        "unconditional_text_only_recipe",
        "Requires source video or image",
        "T2V READY",
        "OVEREXPOSED",
        "https://openrouter.ai/" + slug,
    )
unmapped_types = [
    "VIDEO_UPSCALE",
    "AVATAR_LIPSYNC",
    "MOTION_TRANSFER",
    "CREATIVITY_CONTROL",
    "UPSCALE_FACTOR_CONTROL",
    "TYPED_PROVIDER_CONTROLS",
]
for slug, cap in [
    ("black-forest-labs/flux-video-upscale", "VIDEO_UPSCALE"),
    ("heygen/avatar-iv", "AVATAR_LIPSYNC"),
]:
    add(slug, cap, True, "NO_RECIPE", "UNMAPPED_CAPABILITY", "https://openrouter.ai/" + slug)
    under.add(slug)
counts = Counter(f["status"] for f in facts)
summary = dict(
    CATALOG_MODEL_COUNT=len(models),
    MODELS_FULLY_EXPOSED=0,
    MODELS_UNDEREXPOSED=len(under),
    MODELS_OVEREXPOSED_OR_INCORRECT=len(over),
    UNMAPPED_UPSTREAM_CAPABILITIES=len(unmapped_types),
    MANUAL_OVERLAY_DEPENDENT_MODELS=1,
    DYNAMIC_MODEL_DISCOVERY="PASS",
    DYNAMIC_CAPABILITY_DISCOVERY="FAIL",
    DYNAMIC_PRESET_DERIVATION="PASS_FOR_EXISTING_ONTOLOGY",
    NEW_MODEL_WITHOUT_CODE_CHANGE="FAIL_FOR_NONSTRUCTURED_OR_NEW_OPERATIONS",
    AUDIT_RESULT="CAPABILITY_CATALOG_REBASE_REQUIRED",
    PAID_POST_COUNT=0,
    counts=counts,
    underexposed_models=sorted(under),
    overexposed_models=over,
    fully_exposed_definition="Fully proven across complete requested ontology; unknown facts prevent certification. Counts are confirmed findings, not proof other models have no gaps.",
)
(root / "audit-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
(root / "semantic-comparison.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
(root / "normalized-capability-matrix.json").write_text(
    json.dumps(
        [
            dict(
                exact_model_id=m["id"],
                facts=[f for f in facts if f["exact_model_id"] == m["id"]],
                official_page=next(p for p in pages if p["exact_model_id"] == m["id"]),
            )
            for m in models
        ],
        indent=2,
    ),
    encoding="utf-8",
)
(root / "gap-report.json").write_text(
    json.dumps(
        [
            f
            for f in facts
            if f["status"] in ("MISSING", "INCORRECT", "OVEREXPOSED", "UNDEREXPOSED")
        ],
        indent=2,
    ),
    encoding="utf-8",
)
(root / "unmapped-report.json").write_text(
    json.dumps(
        dict(
            vocabulary_candidates=unmapped_types,
            facts=[f for f in facts if f["status"] == "UNMAPPED_CAPABILITY"],
            note="Vocabulary candidates require wire/authority review; they are not implemented or runtime-supported.",
        ),
        indent=2,
    ),
    encoding="utf-8",
)
recipes = {
    "T2V": {"requires": {"operation": "generation", "prompt_only": True}},
    "I2V": {"requires": {"first_frame": True}},
    "FLF2V": {"requires": {"first_frame": True, "last_frame": True}},
    "IR2V": {"requires": {"image_reference": True, "max_count": 1}},
    "MI2V": {"requires": {"image_reference": True, "max_count_at_least": 2}},
    "VR2V": {"requires": {"video_reference": True}},
    "AR2V": {"requires": {"audio_reference": True}},
    "MMR2V": {
        "requires": {
            "mixed_references": True,
            "distinct_kinds_at_least": 2,
            "max_count_at_least": 2,
        }
    },
    "V2V_EDIT": {"requires": {"source_video": True, "editing": True}},
    "V2V_EXTEND": {"requires": {"source_video": True, "extension": True}},
    "VIDEO_UPSCALE": {
        "requires": {"source_video": True, "upscale_factor": True},
        "state": "PROPOSED_REQUIRES_WIRE_REVIEW",
    },
    "AVATAR_LIPSYNC": {
        "requires": {"image": True, "audio_or_script": True, "lipsync": True},
        "state": "PROPOSED_REQUIRES_WIRE_REVIEW",
    },
    "MOTION_TRANSFER": {
        "requires": {"source_video": True, "motion_transfer": True},
        "state": "PROPOSED_REQUIRES_WIRE_REVIEW",
    },
}
(root / "proposed-recipe-registry.json").write_text(json.dumps(recipes, indent=2), encoding="utf-8")
lines = [
    "# Full capability catalogue audit — Product Owner review",
    "",
    f"Observed: {observed}. All 30 exact official pages retrieved. Public catalogue GET returned 200 without credentials; canonical DEV model ID set matches exactly. No paid calls.",
    "",
    "## Baseline",
    "Accepted tag phase10-native-media-v1 remains fd460f99bddc500b9b663162587c8cfda5c61c0e. Audit branch audit/full-capability-catalog starts from canonical origin/main 9e6969415379dbaf344dabd86ade9fb4146a06f8. Owner dirty checkout and DEV 08838ab remain untouched. Product exposure is observed DEV, not a claim DEV equals canonical main.",
    "",
    "## Conclusions",
    "Existing inference_method_matrix already derives recipes generically from primitive facts. The systemic gap is evidence enrichment plus incomplete operation ontology; replacing the entire matcher would be unnecessary redesign.",
    "Exactly one manual overlay exists: bytedance/seedance-2.5. New structured models can acquire existing methods without code changes; nonstructured facts cannot. All models currently get T2V READY, including source-only models.",
    "",
    "## Counts and limits",
    json.dumps(summary, indent=2),
    "",
    "Counts overlap. Fully exposed=0 means no complete certification: unknowns remain, not all models are broken. Per-model missing controls and operation evidence appear in semantic-comparison.json. Pricing underexposure affects all 30 models in this catalogue: existing estimator rejects video/audio references and does not understand the current observed token/input/minimum/mode SKU vocabulary. Model/provider availability cannot be inferred from description or page retrieval.",
    "",
    "## Evidence conflicts",
    "Wan 2.6 exact page description advertises video/audio inputs while its featureList lists text/image only. Preserve both; do not infer exact wire mode. Empty or null API signals are UNKNOWN, not unsupported. Model modality alone does not prove ordered reference support. Reference limits, ordering, duplicates and operation-specific wire contracts remain unknown unless explicitly documented.",
    "",
    "## Dynamic update design",
    "Layer 1 imports structured exact-model facts and detects unknown keys. Layer 2 uses generated versioned JSON evidence from exact OpenRouter model page structured data/provider metadata and official documentation. Normal execution performs no scraping. Offline/CI ingestion produces candidate diffs; explicit review promotes supported facts. Each fact stores exact ID, value, source, observed_at, authority, scope and freshness. Layer 3 returns UNKNOWN/conflict when support remains unproven.",
    "Precedence: explicit structured signal > exact official page > exact-model-inclusive documentation > controlled evidence. Record conflicts even when higher authority selects effective value. Null is absence, never denial. Unknown upstream operation emits UNMAPPED_UPSTREAM_CAPABILITY.",
    "Independent registry updates are feasible only through validated schema/version/hash, trusted distribution, rollback and review. No autonomous remote executable code or silent capability promotion. Initially ship reviewed JSON with product; separate-data update design needs Product Owner/security acceptance.",
    "",
    "## Bounded implementation packages (not executed)",
    "1. Extend normalized capability ontology and provenance/conflicts, tolerant-reader unmapped facts and negative tests.",
    "2. Generate reviewed exact-model evidence manifest; replace handwritten overlay data while preserving effective accepted facts.",
    "3. Extract current matcher requirements into declarative recipes; add source-required operation prerequisites. Preserve existing order/socket contracts.",
    "4. Add reviewed upscale/avatar/motion-transfer wire contracts and controls only when exact endpoint support is established. Provider-native claims alone are insufficient.",
    "5. Implement typed, validated provider controls and dimension-aware pricing with fail-closed bounds; no arbitrary header/body passthrough.",
    "6. Add reproducible ingestion/diff CI and new-model contract tests; validate all 30 models, save/reload, native sockets, source semantics and one-submit/Resume invariants.",
    "",
    "## Protected regression surfaces",
    "Native IMAGE/VIDEO/AUDIO normalization, private staging, signed URL transience, exact-owned deletion, ambiguity preservation, Resume no submit/upload, duplicates/order, capability-driven geometry, AppIdentity/credential isolation and protected 8188 remain unchanged. No runtime restart or canonical delivery.",
    "",
    "## Review gate",
    "Audit complete at evidence/coverage assessment level; unresolved upstream facts and exact new-operation wire details are explicitly UNKNOWN. Production implementation has not begun. Product Owner review required by attached task.",
]
(root / "AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
print(json.dumps(summary))  # noqa: T201 - public CLI summary
