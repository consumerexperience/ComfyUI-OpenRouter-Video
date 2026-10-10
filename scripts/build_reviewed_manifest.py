"""Materialize the accepted audit as data; never scrape during execution."""

import argparse
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
audit = root / "docs/capability-audit"
catalog = json.loads((audit / "live-catalogue.json").read_text())
pages = json.loads((audit / "official-page-profiles.json").read_text())
source_only = {
    "black-forest-labs/flux-video-edit",
    "black-forest-labs/flux-video-upscale",
    "runway/aleph-2",
    "heygen/avatar-iv",
}
entries = []
for model in catalog["payload"]["data"]:
    slug = model["id"]
    page = next(p for p in pages if p["exact_model_id"] == slug)
    description = page["description"].lower()
    facts = {}

    def fact(key, value, scope="OpenRouter video model", target=facts, source_page=page):
        target[key] = {
            "value": value,
            "authority": "EXACT_OFFICIAL_MODEL_PAGE",
            "source_reference": source_page["source_url"],
            "observed_at": catalog["observed_at"],
            "scope": scope,
        }

    if slug in source_only:
        fact("supports_text_only", False)
        fact("source_required", True)
    elif any(
        phrase in description
        for phrase in (
            "text-to-video",
            "text prompt",
            "from text or image prompts",
            "from text, images, reference videos, or audio",
        )
    ):
        fact("supports_text_only", True)
        fact("source_required", False)
    if (
        "multimodal reference-to-video" in description
        or "set of image, video, and audio references" in description
    ):
        fact("reference_kinds", ["image", "video", "audio"])
        fact("mixed_reference_kinds", True)
    elif (
        "set of reference images" in description
        or "multiple reference images" in description
        or "up to seven reference images" in description
    ):
        fact("reference_kinds", ["image"])
    if slug == "bytedance/seedance-2.5":
        fact("supports_text_only", True)
        fact("source_required", False)
        fact("reference_kinds", ["image", "video", "audio"])
        fact("mixed_reference_kinds", True)
        fact("max_reference_count", 50)
        fact("supports_edit", True)
        fact("supports_extend", True)
        fact("preferred_inference_method", "MI2V", "Preserved accepted UI preference")
    if "up to seven reference images" in description:
        fact("max_reference_count", 7)
    # These operations are evidence only until exact OpenRouter wire is confirmed.
    for phrase, key in [
        ("video upscaling model", "operation.video_upscale"),
        ("lip-synced talking-head", "operation.avatar_lipsync"),
        ("video-to-video motion transfer", "operation.motion_transfer"),
        ("video continuation", "operation.continuation"),
        ("in-context video editing", "operation.editing"),
        ("video editing model", "operation.editing"),
        ("source video and an edit prompt", "operation.editing"),
        ("scene extension", "operation.continuation"),
    ]:
        if phrase in description:
            fact(key, True, "CAPABILITY_ONLY_CONFIRMED")
    if slug == "alibaba/wan-2.6":
        fact(
            "input_modalities_conflict",
            None,
            "Conflicting description vs featureList; no executable enrichment",
        )
        facts["input_modalities_conflict"]["conflicting_evidence"] = [
            page["description"],
            page["features"],
        ]
    entries.append({"exact_model_id": slug, "facts": facts})
payload = {
    "schema_version": 1,
    "artifact_version": "2026-10-10.1",
    "review_status": "PRODUCT_OWNER_APPROVED_AUDIT",
    "models": entries,
}
payload["content_hash"] = hashlib.sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=audit / "candidate-capability-evidence.json")
target = parser.parse_args().output
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
