"""Manual, read-only Phase-8 catalog probe with sanitized output only.

This harness never reads credentials or process environment, never follows redirects, and never
prints a response body. It performs one GET to the canonical video-model catalog and emits only
approved capability evidence. It is intentionally excluded from pytest and CI.
"""

# ruff: noqa: T201 - this manual probe's only interface is sanitized stdout

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

ENDPOINT = "https://openrouter.ai/api/v1/videos/models"
SELECTED_FIELDS = (
    "input_modalities",
    "supported_frame_images",
    "input_references",
    "supported_input_references",
    "reference_media_types",
    "max_input_references",
    "supports_mixed_references",
    "prompt_required",
    "prompt_optional",
)


def _value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def main() -> None:
    observed_at = datetime.now(timezone.utc).isoformat()
    with httpx.Client(follow_redirects=False, timeout=20.0, trust_env=False) as client:
        response = client.get(ENDPOINT)
    if response.status_code != 200:
        print(
            json.dumps(
                {
                    "OBSERVED_AT_UTC": observed_at,
                    "ENDPOINT": f"GET {ENDPOINT}",
                    "MODEL_ID": None,
                    "FIELD": "http_status",
                    "VALUE_TYPE": "integer",
                    "SANITIZED_VALUE": response.status_code,
                    "PROVENANCE": "live unauthenticated catalog observation",
                    "EVIDENCE_CLASS": "OBSERVED",
                    "ENFORCEMENT_ELIGIBILITY": "NONE",
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1)

    payload: Any = response.json()
    models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise SystemExit("Sanitized probe: malformed data array")
    field_names = sorted(
        {
            field
            for model in models
            if isinstance(model, dict)
            for field in model
            if isinstance(field, str)
        }
    )
    observations: list[dict[str, object]] = [
        {
            "OBSERVED_AT_UTC": observed_at,
            "ENDPOINT": f"GET {ENDPOINT}",
            "MODEL_ID": "*",
            "FIELD": "catalog_model_fields",
            "VALUE_TYPE": "array[string]",
            "SANITIZED_VALUE": field_names,
            "PROVENANCE": "live unauthenticated catalog observation",
            "EVIDENCE_CLASS": "OBSERVED",
            "ENFORCEMENT_ELIGIBILITY": "FIELD_PRESENCE_ONLY",
        }
    ]
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            continue
        for field in SELECTED_FIELDS:
            if field not in model:
                continue
            value = model[field]
            observations.append(
                {
                    "OBSERVED_AT_UTC": observed_at,
                    "ENDPOINT": f"GET {ENDPOINT}",
                    "MODEL_ID": model["id"],
                    "FIELD": field,
                    "VALUE_TYPE": _value_type(value),
                    "SANITIZED_VALUE": value,
                    "PROVENANCE": "live unauthenticated catalog observation",
                    "EVIDENCE_CLASS": "OBSERVED",
                    "ENFORCEMENT_ELIGIBILITY": (
                        "FRAME_MODE_ONLY"
                        if field == "supported_frame_images"
                        else "REVIEW_REQUIRED"
                    ),
                }
            )
    print(json.dumps(observations, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
