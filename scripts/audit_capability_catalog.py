"""Read-only, zero-paid official evidence harvest. No runtime imports or secrets."""

import concurrent.futures
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1] / "docs" / "capability-audit"
ROOT.mkdir(parents=True, exist_ok=True)
NOW = datetime.now(timezone.utc).isoformat()


def get(url):
    parsed = urlsplit(url)
    if not (
        (parsed.scheme == "https" and parsed.hostname == "openrouter.ai")
        or (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port == 8189)
    ):
        raise ValueError("Audit destination outside first-party/canonical DEV boundary")
    req = urllib.request.Request(  # noqa: S310 - scheme and host validated above
        url, headers={"User-Agent": "OpenRouter-Capability-Audit/1.0"}
    )
    with urllib.request.urlopen(req, timeout=35) as response:  # noqa: S310 - validated request
        return response.read().decode("utf-8")


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


raw = get("https://openrouter.ai/api/v1/videos/models")
catalogue = json.loads(raw)
current = json.loads(get("http://127.0.0.1:8189/openrouter-video/v1/ui-capabilities"))
save(
    "live-catalogue.json",
    {
        "endpoint": "https://openrouter.ai/api/v1/videos/models",
        "observed_at": NOW,
        "sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "payload": catalogue,
    },
)
save("current-product.json", current)
models = catalogue["data"]
if {m["id"] for m in models} != {m["model_id"] for m in current["models"]}:
    raise ValueError("Live catalogue and canonical DEV identities differ")


def harvest(model):
    slug = model["id"]
    url = "https://openrouter.ai/" + slug
    record = {"exact_model_id": slug, "url": url, "observed_at": NOW}
    try:
        html = get(url)
        (ROOT / (slug.replace("/", "__") + ".html")).write_text(html, encoding="utf-8")
        record.update(status="RETRIEVED", sha256=hashlib.sha256(html.encode()).hexdigest())
    except Exception as error:
        record.update(status="UNAVAILABLE", error_class=type(error).__name__)
    return record


with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    pages = list(pool.map(harvest, models))
save("official-page-receipts.json", pages)
profiles = []
facts = []
gaps = []
unmapped = []
mapping = {
    "supported_resolutions": "supported_resolutions",
    "supported_aspect_ratios": "supported_aspect_ratios",
    "supported_sizes": "supported_sizes",
    "supported_durations": "supported_durations",
    "supported_frame_images": "supported_frame_types",
    "generate_audio": "generate_audio",
    "seed": "supports_seed",
}
metadata = {"id", "canonical_slug", "hugging_face_id", "name", "created", "description"}
for model in models:
    slug = model["id"]
    product = next(m for m in current["models"] if m["model_id"] == slug)
    profile = {"exact_model_id": slug, "structured": model, "product": product, "evidence": []}
    for key, value in model.items():
        if key in metadata:
            continue
        target = mapping.get(key)
        exposure = product.get(target) if target else None
        if value is None:
            status = "UNKNOWN_UPSTREAM"
        elif target:
            equal = (
                set(value) == set(exposure or []) if isinstance(value, list) else value == exposure
            )
            status = "CORRECT" if equal else "INCORRECT"
        else:
            # Further backend/control inspection is required; projection absence alone
            # does not establish that a passthrough/control is absent from the product.
            status = "UNMAPPED_CAPABILITY" if value not in ([], {}) else "CORRECT"
        fact = {
            "exact_model_id": slug,
            "capability": key,
            "value": value,
            "source": "LIVE_STRUCTURED_API",
            "source_url": "https://openrouter.ai/api/v1/videos/models",
            "observed_at": NOW,
            "authority": "A",
            "current_product_exposure": exposure,
            "status": status,
        }
        facts.append(fact)
        profile["evidence"].append(fact)
        if status == "UNMAPPED_CAPABILITY":
            unmapped.append(fact)
    description = model.get("description", "")
    profile["description_evidence"] = {
        "value": description,
        "source_url": "https://openrouter.ai/api/v1/videos/models",
        "authority": "A_EXACT_DESCRIPTION",
        "observed_at": NOW,
    }
    # Candidate findings are reviewable text, never inferred runtime support.
    reference_sentences = [
        s
        for s in re.split(r"(?<=[.!?])\s+", description)
        if re.search(r"reference|edit|extend|extension|audio input|video input", s, re.I)
    ]
    profile["review_required_sentences"] = reference_sentences
    if reference_sentences:
        gaps.append(
            {
                "exact_model_id": slug,
                "official_exact_description": reference_sentences,
                "current_methods": product["inference_method_statuses"],
                "classification": "REQUIRES_SEMANTIC_REVIEW",
            }
        )
    profiles.append(profile)
save("normalized-capability-matrix.json", profiles)
save("semantic-comparison.json", facts)
save("candidate-gaps.json", gaps)
save("unmapped-candidates.json", unmapped)
summary = {
    "catalog_model_count": len(models),
    "fact_count": len(facts),
    "status_counts": {
        status: sum(f["status"] == status for f in facts)
        for status in sorted({f["status"] for f in facts})
    },
    "pages_retrieved": sum(p["status"] == "RETRIEVED" for p in pages),
    "manual_overlay_dependent_models": ["bytedance/seedance-2.5"],
    "paid_post_count": 0,
    "audit_status": "HARVEST_COMPLETE_SEMANTIC_REVIEW_REQUIRED",
}
save("harvest-summary.json", summary)
print(json.dumps(summary))  # noqa: T201 - public CLI summary
