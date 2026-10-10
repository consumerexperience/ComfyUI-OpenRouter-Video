"""Reclassify every retained BEFORE fact against candidate Core and live DEV.

Capability-only representation is reported separately from executable support.
It never certifies an unconfirmed request wire contract or provider generation.
"""

import json
from collections import Counter
from pathlib import Path

import httpx

from openrouter_video.client import _parse_capability
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.pricing_profile import PricingUnit, normalize_pricing

root = Path(__file__).resolve().parents[1] / "docs/capability-audit"
receipt = json.loads((root / "live-catalogue.json").read_text(encoding="utf-8"))
baseline = json.loads((root / "semantic-comparison.json").read_text(encoding="utf-8"))
response = httpx.get("http://127.0.0.1:8189/openrouter-video/v1/ui-capabilities")
response.raise_for_status()
live = response.json()
(root / "canonical-after-product.json").write_text(json.dumps(live, indent=2), encoding="utf-8")
projected = {m["model_id"]: m for m in live["models"]}
models = {m["id"]: enrich_capabilities(_parse_capability(m)) for m in receipt["payload"]["data"]}
if set(models) != set(projected):
    raise ValueError("Live DEV catalogue differs from audit identity set")
mapping = {"supported_frame_images": "supported_frame_types", "seed": "supports_seed"}
operations = {
    "editing": "operation.editing",
    "continuation": "operation.continuation",
    "extension": "operation.continuation",
    "motion_transfer": "operation.motion_transfer",
    "VIDEO_UPSCALE": "operation.video_upscale",
    "AVATAR_LIPSYNC": "operation.avatar_lipsync",
}
rows = []
for fact in baseline:
    model = models[fact["exact_model_id"]]
    projection = projected[model.model_id]
    evidence = {f["key"]: f for f in projection["capability_evidence"]}
    key = fact["capability"]
    status = "MISSING"
    scope = "EXECUTABLE_KNOWN_ONTOLOGY"
    if fact["status"] == "UNKNOWN_UPSTREAM":
        status = "UNKNOWN_UPSTREAM"
    elif fact["status"] == "CONFLICT":
        status = "CONFLICT"
    elif key in projection or key in mapping:
        actual = projection.get(mapping.get(key, key))
        if isinstance(actual, list) and isinstance(fact["value"], list):
            actual, expected = sorted(actual), sorted(fact["value"])
        else:
            expected = fact["value"]
        status = "CORRECT" if actual == expected else "MISSING"
    elif key == "pricing_skus":
        dimensions = normalize_pricing(model.pricing_evidence) if model.pricing_evidence else ()
        status = (
            "CORRECT"
            if dimensions and all(d.unit is not PricingUnit.UNKNOWN for d in dimensions)
            else "UNKNOWN_UPSTREAM"
        )
        scope = "CORE_TYPED_PRICING; unsafe quantity remains UNAVAILABLE"
    elif key in ("allowed_passthrough_parameters", "upscale_factor", "creativity"):
        descriptor = evidence.get(key)
        status = "CORRECT" if descriptor and descriptor["value"] is not None else "UNKNOWN_UPSTREAM"
        scope = "CAPABILITY_ONLY_CONFIRMED; no executable passthrough"
    elif key in ("multimodal_references", "multiple_image_references"):
        method = "MMR2V" if key == "multimodal_references" else "MI2V"
        status = "CORRECT" if method in projection["supported_inference_methods"] else "MISSING"
    elif key == "unconditional_text_only_recipe":
        status = (
            "CORRECT"
            if "T2V" not in projection["supported_inference_methods"]
            and model.source_required is True
            else "OVEREXPOSED"
        )
    elif key in operations:
        descriptor = evidence.get(operations[key])
        status = "CORRECT" if descriptor and descriptor["value"] is True else "MISSING"
        scope = "CAPABILITY_ONLY_CONFIRMED; executable wire not certified"
    rows.append({**fact, "before_status": fact["status"], "status": status, "scope": scope})
counts = Counter(row["status"] for row in rows)
summary = {
    "CATALOG_MODEL_COUNT": len(models),
    "CONFIRMED_CAPABILITY_FACTS": sum(
        row["status"] not in {"UNKNOWN_UPSTREAM", "CONFLICT"} for row in rows
    ),
    "CONFIRMED_FACTS_CORRECTLY_EXPOSED": counts["CORRECT"],
    "CONFIRMED_FACTS_MISSING": counts["MISSING"],
    "CONFIRMED_OVEREXPOSURES": counts["OVEREXPOSED"],
    "MODELS_WITH_CONFIRMED_UNDEREXPOSURE": len(
        {r["exact_model_id"] for r in rows if r["status"] == "MISSING"}
    ),
    "MODELS_WITH_CONFIRMED_OVEREXPOSURE": len(
        {r["exact_model_id"] for r in rows if r["status"] == "OVEREXPOSED"}
    ),
    "UNKNOWN_UPSTREAM_FACTS": counts["UNKNOWN_UPSTREAM"],
    "CAPABILITY_CONFLICTS": sum(
        f["state"] == "CONFLICT" for m in live["models"] for f in m["capability_evidence"]
    ),
    "UNMAPPED_UPSTREAM_CAPABILITIES": sorted(
        {k for m in live["models"] for k in m["unmapped_upstream_capabilities"]}
    ),
    "CAPABILITY_ONLY_FACTS": sum(
        r["status"] == "CORRECT" and r["scope"].startswith("CAPABILITY_ONLY") for r in rows
    ),
    "MANUAL_OVERLAY_DEPENDENT_MODELS": 0,
    "OPENROUTER_PAID_POST_COUNT": 0,
    "provider_execution_certified": False,
}
(root / "after-semantic-comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
(root / "after-audit-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))  # noqa: T201 - public CLI summary
