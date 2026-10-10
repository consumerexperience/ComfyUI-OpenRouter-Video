"""Offline AFTER projection proof against the retained exact live catalogue."""

import json
from datetime import datetime
from pathlib import Path

from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_model
from openrouter_video.evidence_registry import enrich_capabilities, load_manifest

root = Path(__file__).resolve().parents[1] / "docs/capability-audit"
receipt = json.loads((root / "live-catalogue.json").read_text(encoding="utf-8"))
baseline = json.loads((root / "current-product.json").read_text(encoding="utf-8"))
before = {m["model_id"]: m for m in baseline["models"]}
observed = datetime.fromisoformat(receipt["observed_at"])
models = []
for raw in receipt["payload"]["data"]:
    model = enrich_capabilities(_parse_capability(raw))
    projected = project_model(model, observed).as_dict()
    prior = before[model.model_id]
    protected_controls = (
        "supported_durations",
        "supported_resolutions",
        "supported_aspect_ratios",
        "supported_sizes",
        "supports_seed",
        "generate_audio",
        "supported_frame_types",
    )
    differences = {
        key: {"before": prior.get(key), "after": projected.get(key)}
        for key in projected
        if json.dumps(prior.get(key), sort_keys=True) != json.dumps(projected[key], sort_keys=True)
    }
    if set(differences) & set(protected_controls):
        raise ValueError(f"Protected control changed: {model.model_id}")
    models.append(
        {"exact_model_id": model.model_id, "projection": projected, "semantic_diff": differences}
    )
if len(models) != 30 or set(before) != {model["exact_model_id"] for model in models}:
    raise ValueError("Exact catalogue identity changed")
result = {
    "catalogue_sha256": receipt["sha256"],
    "manifest_sha256": load_manifest()["content_hash"],
    "model_count": len(models),
    "existing_geometry_and_basic_controls": "PASS",
    "model_identity_set": "PASS",
    "canonical_runtime_acceptance": "PENDING",
    "paid_post_count": 0,
    "models": models,
}
(root / "after-projection-proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
