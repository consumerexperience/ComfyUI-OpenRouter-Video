"""R3.1 primary media quantity authority through the public bounded parser."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.capabilities import request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.routes import _parse_estimate_inputs
from openrouter_video.configuration import project_semantic_values
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import InferenceMethod, ModelCapabilities
from openrouter_video.pricing import EstimateResult, PreflightCostEstimator

RAW = json.loads(
    (Path(__file__).parents[1] / "fixtures/aci_r31/current-raw-video-catalogue.json").read_text(
        encoding="utf-8"
    )
)
OBSERVED = datetime(2026, 11, 14, tzinfo=timezone.utc)


def setup(model_id: str, method: InferenceMethod) -> tuple[ModelCapabilities, dict[str, Any]]:
    cap = enrich_capabilities(
        _parse_capability(next(row for row in RAW["data"] if row["id"] == model_id))
    )
    witness = request_witness(cap, method)
    assert witness is not None
    names = (
        "duration",
        "resolution",
        "aspect_ratio",
        "size",
        "generate_audio",
        "upscale_factor",
        "creativity",
    )
    raw = {name: getattr(witness, name) for name in names}
    raw["geometry_authority"] = "EXACT" if witness.size else "NORMALIZED"
    values = project_semantic_values(cap, method.value, raw)
    kinds = (
        [item.kind.value for item in witness.input_references.references]
        if witness.input_references
        else []
    )
    media: list[dict[str, Any]] = [
        dict(kind=kind, role="reference", status="UNKNOWN") for kind in kinds
    ]
    for role, kind, present in [
        ("first_frame", "image", witness.first_frame is not None),
        ("last_frame", "image", witness.last_frame is not None),
        ("source_video", "video", witness.source_video is not None),
    ]:
        if present:
            media.append(dict(kind=kind, role=role, status="UNKNOWN"))
    for index, item in enumerate(media):
        item.update(occurrence_index=index, context_revision=7)
    body = dict(
        schema_version=2,
        context_revision=7,
        model_id=model_id,
        inference_method=method.value,
        reference_kinds=kinds,
        reference_count=len(kinds),
        source_video_present=witness.source_video is not None,
        media=media,
        **{name: values.get(name) for name in names},
    )
    if body["upscale_factor"] is not None:
        body["upscale_factor"] = str(body["upscale_factor"])
    return cap, body


def estimate(cap: ModelCapabilities, body: dict[str, Any]) -> EstimateResult:
    return PreflightCostEstimator().estimate(
        cap, _parse_estimate_inputs(body), observed_at=OBSERVED
    )


def source_hint() -> tuple[ModelCapabilities, dict[str, Any]]:
    cap, body = setup("runway/aleph-2", InferenceMethod.V2V_EDIT)
    assert len(body["media"]) == 1 and body["media"][0]["role"] == "source_video"
    body["media"][0].update(status="HINT", duration_seconds="7.5")
    return cap, body


def test_matching_source_hint_uses_only_source_quantity_and_retains_hint_disclosure() -> None:
    cap, body = source_hint()
    result = estimate(cap, body)
    assert result.state == "FORMULA" and result.amount_usd == Decimal("2.10")
    assert any("hint" in note and "preview" in note for note in result.assumptions)
    body["effective_output_seconds"] = "999999"
    assert estimate(cap, body).amount_usd == Decimal("2.10")


@pytest.mark.parametrize(
    "change",
    [
        {"context_revision": 6},
        {"occurrence_index": 1},
        {"context_revision": None},
        {"occurrence_index": None},
    ],
)
def test_replaced_or_unstamped_preview_cannot_supply_primary_source_quantity(
    change: dict[str, Any],
) -> None:
    cap, body = source_hint()
    body["media"][0].update(change)
    result = estimate(cap, body)
    assert result.state == "RATE_ONLY" and result.amount_usd is None
    assert result.rate_usd == Decimal("0.28")


def test_public_known_is_not_internal_native_metadata_authority() -> None:
    cap, body = source_hint()
    body["media"][0].update(status="KNOWN", context_revision=None)
    parsed = _parse_estimate_inputs(body)
    assert parsed.media[0].status == "HINT"
    assert estimate(cap, body).amount_usd is None


def test_missing_inventory_is_unknown_while_unknown_records_keep_valid_active_counts() -> None:
    cap, body = setup("x-ai/grok-imagine-video", InferenceMethod.IR2V)
    known_count = estimate(cap, body)
    assert known_count.state == "FORMULA" and known_count.amount_usd == Decimal("0.072")
    assert body["media"][0]["status"] == "UNKNOWN" and "duration_seconds" not in body["media"][0]
    missing = copy.deepcopy(body)
    missing["media"] = []
    result = estimate(cap, missing)
    assert result.state == "UNKNOWN" and result.amount_usd is None
    assert result.reason == "active_occurrence_metadata_missing"
    extra = copy.deepcopy(body)
    extra["media"].append(copy.deepcopy(extra["media"][0]))
    assert estimate(cap, extra).state == "INVALID"


def test_distinct_first_last_roles_cannot_be_reordered_for_pricing() -> None:
    cap, body = setup("bytedance/seedance-2.5", InferenceMethod.FLF2V)
    assert [row["role"] for row in body["media"]] == ["first_frame", "last_frame"]
    body["media"].reverse()
    result = estimate(cap, body)
    assert result.state == "INVALID" and result.amount_usd is None and result.planning is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("occurrence_index", True),
        ("occurrence_index", -1),
        ("context_revision", True),
        ("context_revision", "7"),
    ],
)
def test_media_revision_abi_rejects_malformed_counters(field: str, value: object) -> None:
    _, body = source_hint()
    body["media"][0][field] = value
    with pytest.raises(ValueError):
        _parse_estimate_inputs(body)


@pytest.mark.parametrize(
    "model_id,method,duration",
    [
        ("black-forest-labs/flux-video-edit", InferenceMethod.V2V_EDIT, "16"),
        ("black-forest-labs/flux-video-upscale", InferenceMethod.V2V_UPSCALE, "21"),
    ],
)
def test_known_media_quantity_outside_existing_core_limit_cannot_get_price(
    model_id: str,
    method: InferenceMethod,
    duration: str,
) -> None:
    cap, body = setup(model_id, method)
    body["media"][0].update(
        status="HINT", duration_seconds=duration, width=640, height=480, fps="24"
    )
    result = estimate(cap, body)
    assert result.state == "INVALID" and result.amount_usd is None and result.planning is None
    assert result.reason == "media_metadata_outside_projected_limits"
    # Replaced/unbound preview metadata is unknown, not proof of invalid media.
    body["media"][0]["context_revision"] = 0
    stale = estimate(cap, body)
    assert stale.state != "INVALID" and stale.amount_usd is None
