"""Offline configuration audit; never infer a Cartesian configuration relation."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/adaptive-generation-controls/evidence"
FIELDS = {
    "resolution": "supported_resolutions",
    "aspect_ratio": "supported_aspect_ratios",
    "duration": "supported_durations",
    "size": "supported_sizes",
}


def main() -> None:
    raw = json.loads((EVIDENCE / "live-catalogue.json").read_text(encoding="utf-8"))
    product = json.loads((EVIDENCE / "current-product.json").read_text(encoding="utf-8"))
    pages = json.loads((EVIDENCE / "official-page-profiles.json").read_text(encoding="utf-8"))
    endpoints = json.loads(
        (EVIDENCE / "official-endpoint-profiles.json").read_text(encoding="utf-8")
    )
    model_ids = {m["id"] for m in raw["payload"]["data"]}
    if model_ids != {m["model_id"] for m in product["models"]}:
        raise ValueError("Public catalogue and canonical DEV model sets differ")
    facts = []
    models = []
    missing = 0
    for model in sorted(raw["payload"]["data"], key=lambda item: item["id"]):
        exact_id = model["id"]
        projected = next(item for item in product["models"] if item["model_id"] == exact_id)
        page = next(item for item in pages if item["exact_model_id"] == exact_id)
        endpoint = next(item for item in endpoints if item["exact_model_id"] == exact_id)
        record = {
            "exact_model_id": exact_id,
            "mode": "NO_SEPARATE_MODE_CONTROL_IN_ACCEPTED_SOURCE",
            "inference_methods": projected["inference_method_statuses"],
            "configuration_relation": "INDEPENDENT_STRUCTURED_DOMAINS_NO_EXPLICIT_COUPLING",
            "dependencies": {
                name: "UNKNOWN"
                for name in ("mode", "method", "input", "audio", "geometry_duration")
            },
            "facts": {},
            "official_description": page,
            "provider_metadata": endpoint["endpoints"],
            "conflicts": [],
        }
        for name, key in FIELDS.items():
            values = model.get(key)
            record["facts"][name] = {
                "state": "UNKNOWN" if values is None else "CONFIRMED_AXIS_VALUES",
                "values": values,
                "source_reference": raw["endpoint"],
                "authority": "LIVE_STRUCTURED_API",
                "observed_at": raw["observed_at"],
            }
            for value in values or []:
                represented = value in (projected.get(key) or [])
                missing += not represented
                facts.append(
                    {
                        "exact_model_id": exact_id,
                        "canonical_display": str(value),
                        "wire_value": value,
                        "semantic_type": name,
                        "state": "CONFIRMED_INDEPENDENT_PARAMETER",
                        "authority": "LIVE_STRUCTURED_API",
                        "source_reference": raw["endpoint"],
                        "observed_at": raw["observed_at"],
                        "method_applicability": "UNKNOWN",
                        "mode_applicability": "UNKNOWN",
                        "constraints": "UNKNOWN",
                        "represented_in_baseline": represented,
                    }
                )
        # Compare like-for-like endpoint arrays only. Null is absence, not a denial.
        for upstream in endpoint["endpoints"]:
            parameters = upstream.get("supported_video_parameters", {})
            for name, key in FIELDS.items():
                catalogue_values = model.get(key)
                provider_values = parameters.get(key)
                if (
                    catalogue_values is not None
                    and provider_values is not None
                    and set(catalogue_values) != set(provider_values)
                ):
                    record["conflicts"].append(
                        {
                            "field": name,
                            "catalogue": catalogue_values,
                            "official_endpoint": provider_values,
                            "provider": upstream.get("provider_name"),
                            "source_reference": page["source_url"],
                            "state": "CONFLICT_REVIEW_REQUIRED",
                        }
                    )
        models.append(record)
    report = {
        "schema_version": 1,
        "artifact_version": "adaptive-generation-configuration-audit-20261011-v1",
        "observed_at": raw["observed_at"],
        "catalogue_sha256": raw["sha256"],
        "catalog_model_count": len(models),
        "exact_model_ids": sorted(model_ids),
        "global_union": {
            name: sorted({v for m in raw["payload"]["data"] for v in (m.get(key) or [])})
            for name, key in FIELDS.items()
        },
        "confirmed_axis_facts": len(facts),
        "confirmed_axis_facts_represented_in_baseline": len(facts) - missing,
        "confirmed_axis_facts_missing_in_baseline": missing,
        "configuration_policy": "OWNER_20261011_INDEPENDENT_DOMAINS_EXPLICIT_COUPLING",
        "tuple_documentation_absence_is_unknown": False,
        "confirmed_configuration_relation_coverage": "INDEPENDENT_DOMAINS",
        "confirmed_overexposure": "NOT_YET_VERIFIED",
        "models_with_axis_facts": sum(
            any(f["values"] for f in m["facts"].values()) for m in models
        ),
        "models_with_any_unknown_axis": sum(
            any(f["values"] is None for f in m["facts"].values()) for m in models
        ),
        "models_with_conflicts": sum(bool(m["conflicts"]) for m in models),
        "models": models,
        "vocabulary": facts,
        "paid_post_count_this_audit": 0,
        "promotion": "CANDIDATE_ONLY_NO_PACKAGED_EVIDENCE_WRITE",
    }
    destination = ROOT / "docs/adaptive-generation-controls/configuration-audit.json"
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
