"""ACI v2 cost-only input bounds and compatibility; never acquire submit authority."""

from __future__ import annotations

from typing import Any

import pytest

from openrouter_video.comfy.routes import _parse_estimate_inputs
from openrouter_video.models import ModelCapabilities
from openrouter_video.pricing import EstimateResult


def payload(**fields: Any) -> dict[str, Any]:
    return {"model_id": "fixture/strict", "schema_version": 2, "context_revision": 7, **fields}


def test_v1_false_v2_omitted_and_null_audio_remain_distinct() -> None:
    assert _parse_estimate_inputs({"model_id": "fixture/strict"}).generate_audio is False
    assert _parse_estimate_inputs(payload()).generate_audio is None
    assert _parse_estimate_inputs(payload(generate_audio=None)).generate_audio is None
    assert _parse_estimate_inputs(payload(generate_audio=False)).generate_audio is False
    assert _parse_estimate_inputs(payload(generate_audio=True)).generate_audio is True


@pytest.mark.parametrize(
    "fields",
    [
        {"schema_version": True},
        {"schema_version": 3},
        {"context_revision": True},
        {"context_revision": -1},
        {"context_revision": 10**50},
        {"duration": True},
        {"duration": 0},
        {"duration": -2},
        {"duration": "5"},
        {"generate_audio": 0},
        {"generate_audio": "false"},
        {"reference_count": True},
        {"reference_count": -1},
        {"reference_count": 10**30},
        {"reference_kinds": ["not_media"]},
        {"effective_output_seconds": "NaN"},
        {"effective_output_seconds": "Infinity"},
        {"effective_output_seconds": "-1"},
        {"effective_output_seconds": 1.1},
        {"upscale_factor": True},
        {"upscale_factor": -1},
        {"creativity": 2},
        {"media": "metadata"},
        {"media": [{"kind": "video", "role": "source_video", "path": "private"}]},
        {"media": [{"kind": "video", "role": "source_video", "width": 0}]},
        {"media": [{"kind": "video", "role": "source_video", "width": True}]},
        {"media": [{"kind": "video", "role": "source_video", "duration_seconds": "NaN"}]},
        {"media": [{"kind": "video", "role": "source_video", "fps": "Infinity"}]},
        {"media": [{"kind": "video", "role": "parked"}]},
    ],
)
def test_v2_rejects_malformed_or_unbounded_values(fields: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _parse_estimate_inputs(payload(**fields))


@pytest.mark.parametrize(
    "field",
    ["prompt", "api_key", "node_id", "path", "url", "filename", "output_count", "reference_images"],
)
def test_v2_does_not_accept_sensitive_or_independent_quantity_overrides(field: str) -> None:
    with pytest.raises(ValueError):
        _parse_estimate_inputs(payload(**{field: "synthetic"}))


def test_v2_unknown_metadata_preserves_explicit_null() -> None:
    parsed = _parse_estimate_inputs(
        payload(
            source_video_present=True,
            media=[
                {
                    "kind": "video",
                    "role": "source_video",
                    "status": "UNKNOWN",
                    "duration_seconds": None,
                    "width": None,
                    "height": None,
                    "fps": None,
                }
            ],
        )
    )
    assert parsed.context_revision == 7
    assert len(parsed.media) == 1
    assert parsed.media[0].duration_seconds is None


def test_v2_reference_metadata_preserves_duplicate_occurrences() -> None:
    occurrence = {"kind": "image", "role": "reference", "status": "UNKNOWN"}
    parsed = _parse_estimate_inputs(
        payload(
            reference_kinds=["image", "image"],
            reference_count=2,
            media=[occurrence, occurrence],
        )
    )
    assert len(parsed.media) == 2
    assert parsed.reference_count == 2


def _neutral_runtime_model() -> ModelCapabilities:
    import json
    from pathlib import Path

    from openrouter_video.client import _parse_capability
    from openrouter_video.evidence_registry import enrich_capabilities, load_manifest

    rows = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text(
            encoding="utf-8"
        )
    )["data"]
    return enrich_capabilities(
        _parse_capability(next(row for row in rows if row["id"] == "kwaivgi/kling-v3.0-pro")),
        load_manifest(),
    )


def _neutral_runtime_result(
    *, version: str = "ACI-1.0", canonical_mismatch: bool = False
) -> EstimateResult:
    import asyncio
    from dataclasses import replace
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from openrouter_video.comfy.runtime import ProcessRuntime

    model = _neutral_runtime_model()
    if canonical_mismatch:
        model = replace(model, canonical_slug="kwaivgi/kling-v3.0-pro-unreviewed-revision")
    observed = datetime(2026, 11, 13, tzinfo=timezone.utc)

    class Catalogue:
        async def effective_catalog(self) -> Any:
            return SimpleNamespace(models=(model,), observed_at=observed)

        def is_fresh(self, observation: object) -> bool:
            return True

    class FakeRuntime:
        def _require_resources(self) -> Any:
            return SimpleNamespace(capabilities=Catalogue())

        async def _dispatch(self, run: Any) -> Any:
            return await run(SimpleNamespace(raise_if_interrupted=lambda: None))

    inputs = _parse_estimate_inputs(
        {
            "model_id": model.model_id,
            "schema_version": 2,
            "context_revision": 1,
            "duration": 3,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "generate_audio": False,
            "inference_method": "T2V",
            "provider_policy_version": version,
            "provider_controls": [
                {"provider": "atlas-cloud", "key": "cfg_scale", "number_value": "0.5"},
                {"provider": "atlas-cloud", "key": "negative_prompt", "text_length": 30},
            ],
        }
    )
    return asyncio.run(ProcessRuntime.estimate_cost(FakeRuntime(), inputs))  # type: ignore[arg-type]


def test_neutral_controls_keep_known_kling_price_through_real_cost_runtime() -> None:
    from decimal import Decimal

    result = _neutral_runtime_result()
    assert result.state == "FORMULA"
    assert result.amount_usd == Decimal("0.336")


@pytest.mark.parametrize(
    "version,canonical_mismatch", [("UNREVIEWED-POLICY", False), ("ACI-1.0", True)]
)
def test_neutral_policy_version_or_canonical_scope_mismatch_is_unknown(
    version: str, canonical_mismatch: bool
) -> None:
    result = _neutral_runtime_result(version=version, canonical_mismatch=canonical_mismatch)
    assert result.state == "UNKNOWN"
    assert result.amount_usd is None


@pytest.mark.parametrize(
    "control",
    [
        {"provider": "atlas-cloud", "key": "negative_prompt", "value": "PRIVATE_TEXT"},
        {"provider": "atlas-cloud", "key": "negative_prompt", "text_length": 4, "path": []},
        {"provider": "atlas-cloud", "key": "cfg_scale", "number_value": True},
    ],
)
def test_neutral_cost_payload_rejects_raw_text_paths_and_malformed_number(
    control: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        _parse_estimate_inputs(
            payload(provider_policy_version="ACI-1.0", provider_controls=[control])
        )
