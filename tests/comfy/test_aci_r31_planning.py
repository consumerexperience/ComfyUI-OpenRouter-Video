"""R3 financial dimensions and input authority, using real Core witnesses.

Metadata fixtures are explicit synthetic hints, never measured user media.
Literal amounts are the supplied R3 reference cases; no tariff research here.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from openrouter_video.capabilities import FRESH_TTL, eligible_methods, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy import compat, routes
from openrouter_video.comfy.runtime import ProcessRuntime
from openrouter_video.configuration import project_semantic_values
from openrouter_video.evidence_registry import enrich_capabilities, load_manifest
from openrouter_video.models import InferenceMethod, ModelCapabilities, PricingEvidence, PricingSku
from openrouter_video.pricing import EstimateResult
from openrouter_video.pricing_planning import compile_planning_policy

OBSERVED = datetime(2026, 11, 14, 11, 44, 50, tzinfo=timezone.utc)
RAW = json.loads(
    (Path(__file__).parents[1] / "fixtures/aci_r31/current-raw-video-catalogue.json").read_text(
        encoding="utf-8"
    )
)


def model(model_id: str) -> ModelCapabilities:
    return enrich_capabilities(
        _parse_capability(next(row for row in RAW["data"] if row["id"] == model_id)),
        load_manifest(),
    )


def payload(model_id: str, method: InferenceMethod) -> dict[str, Any]:
    cap = model(model_id)
    assert method in eligible_methods(cap)
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
    raw.update(
        geometry_authority="EXACT" if witness.size else "NORMALIZED",
        provider_options=witness.provider_options,
    )
    effective = project_semantic_values(cap, method.value, raw)
    kinds = (
        [reference.kind.value for reference in witness.input_references.references]
        if witness.input_references
        else []
    )
    media = [{"kind": kind, "role": "reference", "status": "UNKNOWN"} for kind in kinds]
    for role, kind, present in (
        ("first_frame", "image", witness.first_frame is not None),
        ("last_frame", "image", witness.last_frame is not None),
        ("source_video", "video", witness.source_video is not None),
    ):
        if present:
            media.append({"kind": kind, "role": role, "status": "UNKNOWN"})
    return dict(
        schema_version=2,
        context_revision=1,
        model_id=model_id,
        duration=effective.get("duration"),
        resolution=effective.get("resolution"),
        aspect_ratio=effective.get("aspect_ratio"),
        size=effective.get("size"),
        generate_audio=effective.get("generate_audio"),
        inference_method=method.value,
        reference_kinds=kinds,
        reference_count=len(kinds),
        source_video_present=witness.source_video is not None,
        media=media,
        creativity=effective.get("creativity"),
        upscale_factor=str(effective["upscale_factor"])
        if effective.get("upscale_factor") is not None
        else None,
    )


def synthetic_hint(body: dict[str, Any], duration: str = "5") -> dict[str, Any]:
    result = copy.deepcopy(body)
    for index, occurrence in enumerate(result["media"]):
        if occurrence["kind"] in {"video", "audio"}:
            occurrence.update(
                status="HINT",
                duration_seconds=duration,
                occurrence_index=index,
                context_revision=result["context_revision"],
            )
            if occurrence["kind"] == "video":
                occurrence.update(width=1280, height=720, fps="24")
    return result


def run(
    body: dict[str, Any], *, cap: ModelCapabilities | None = None, fresh: bool = True
) -> EstimateResult:
    selected = cap or model(body["model_id"])

    class Catalogue:
        async def effective_catalog(self) -> Any:
            return SimpleNamespace(models=(selected,), observed_at=OBSERVED)

        def is_fresh(self, observation: object) -> bool:
            return fresh

    class Runtime:
        def _require_resources(self) -> Any:
            return SimpleNamespace(capabilities=Catalogue())

        async def _dispatch(self, operation: Any) -> Any:
            return await operation(SimpleNamespace(raise_if_interrupted=lambda: None))

    return asyncio.run(ProcessRuntime.estimate_cost(Runtime(), routes._parse_estimate_inputs(body)))  # type: ignore[arg-type]


def planning(result: EstimateResult) -> dict[str, Any]:
    assert result.planning is not None
    return dict(result.planning)


def scenario_amounts(result: EstimateResult) -> set[Decimal]:
    return {Decimal(row["amount_usd"]) for row in planning(result)["scenarios"]}


def assert_not_primary_money(result: EstimateResult) -> None:
    assert result.state not in {"FORMULA", "RANGE"}
    assert result.availability.value == "UNAVAILABLE"
    assert result.amount_usd is result.estimated_cost_usd is None
    assert result.lower_usd is result.upper_usd is None


def test_conditional_geometry_scenarios_are_not_primary_or_guaranteed_range() -> None:
    result = run(payload("bytedance/seedance-2.0-mini", InferenceMethod.T2V))
    assert_not_primary_money(result)
    assert planning(result)["version"] == "ACI-PLANNING-1"
    assert planning(result)["display"] == "SCENARIO_RANGE"
    assert scenario_amounts(result) == {Decimal("0.0756"), Decimal("0.1344")}
    assert all(row["scope"] == "CONDITIONAL_TOTAL" for row in planning(result)["scenarios"])
    assert "spending cap" in planning(result)["notice"]
    json.dumps(planning(result), allow_nan=False)


def test_seed_video_input_reference_literal_scenarios_and_unknown_quantity() -> None:
    body = synthetic_hint(payload("bytedance/seedance-2.5", InferenceMethod.VR2V), "2")
    body.update(resolution="720p", aspect_ratio="16:9", duration=5)
    result = run(body)
    assert_not_primary_money(result)
    assert scenario_amounts(result) == {Decimal("1.24416"), Decimal("1.24992")}
    body["media"][0] = {"kind": "video", "role": "reference", "status": "UNKNOWN"}
    missing = run(body)
    assert_not_primary_money(missing)
    assert not planning(missing)["scenarios"]
    assert planning(missing)["missing"]


def test_gemini_silent_amount_is_comparison_only() -> None:
    result = run(payload("google/gemini-omni-1.2-flash", InferenceMethod.T2V))
    assert_not_primary_money(result)
    assert planning(result)["display"] == "DETAIL_ONLY"
    assert scenario_amounts(result) == {Decimal("0.208512")}
    assert all(row["scope"] == "COMPARISON" for row in planning(result)["scenarios"])


def test_heygen_video_components_never_form_a_total_or_lower_bound() -> None:
    result = run(synthetic_hint(payload("heygen/heygen-video-1", InferenceMethod.VR2V)))
    assert_not_primary_money(result)
    assert planning(result)["display"] == "DETAIL_ONLY"
    assert {row["scope"] for row in planning(result)["scenarios"]} <= {"COMPONENT", "COMPARISON"}
    assert any(row["scope"] == "COMPONENT" for row in planning(result)["scenarios"])


def test_nominal_upscale_binary_megapixel_scenario_is_modelled_only() -> None:
    result = run(
        synthetic_hint(payload("black-forest-labs/flux-video-upscale", InferenceMethod.V2V_UPSCALE))
    )
    assert_not_primary_money(result)
    assert planning(result)["display"] == "MODELLED"
    assert scenario_amounts(result) == {Decimal("0.3460693359375")}


@pytest.mark.parametrize("mutation", ["missing", "extra", "wrong_role", "changed_kind"])
def test_active_occurrence_inventory_mismatch_cannot_be_rescued_by_planning(mutation: str) -> None:
    body = synthetic_hint(payload("bytedance/seedance-2.5", InferenceMethod.VR2V), "2")
    if mutation == "missing":
        body["media"] = []
    elif mutation == "extra":
        body["media"].append(copy.deepcopy(body["media"][0]))
    elif mutation == "wrong_role":
        body["media"][0]["role"] = "source_video"
    else:
        body["media"][0]["kind"] = "image"
    result = run(body)
    assert result.amount_usd is None
    assert not result.planning or not result.planning.get("scenarios")


def test_duplicate_active_video_occurrences_are_not_deduplicated() -> None:
    body = synthetic_hint(payload("bytedance/seedance-2.5", InferenceMethod.VR2V), "5")
    body.update(resolution="720p", aspect_ratio="16:9", duration=5)
    once = run(body)
    body["media"].append(copy.deepcopy(body["media"][0]))
    body["reference_kinds"].append("video")
    body["reference_count"] += 1
    body["media"][-1]["occurrence_index"] = len(body["media"]) - 1
    twice = run(body)
    assert_not_primary_money(twice)
    assert max(scenario_amounts(twice)) > max(scenario_amounts(once))


def test_client_effective_billed_duration_cannot_create_or_change_a_scenario() -> None:
    body = payload("black-forest-labs/flux-video-upscale", InferenceMethod.V2V_UPSCALE)
    before = run(body)
    body["effective_output_seconds"] = "999999"
    after = run(body)
    assert before.amount_usd is after.amount_usd is None
    assert before.planning == after.planning


@pytest.mark.parametrize(
    "mutation", ["revision", "new_sku", "removed_sku", "invalid_config", "stale"]
)
def test_invalid_or_drifted_context_never_gets_scenarios(mutation: str) -> None:
    body = payload("bytedance/seedance-2.0-mini", InferenceMethod.T2V)
    cap = model(body["model_id"])
    assert cap.pricing_evidence is not None
    evidence = cap.pricing_evidence
    if mutation == "revision":
        cap = replace(cap, canonical_slug="unreviewed/revision")
    elif mutation == "new_sku":
        cap = replace(
            cap,
            pricing_evidence=PricingEvidence(
                evidence.skus + (PricingSku("unknown_fee", Decimal("0.01")),)
            ),
        )
    elif mutation == "removed_sku":
        cap = replace(cap, pricing_evidence=PricingEvidence(evidence.skus[:-1]))
    elif mutation == "invalid_config":
        body["duration"] = 999
    result = run(body, cap=cap, fresh=mutation != "stale")
    assert result.planning is None
    assert result.amount_usd is None


def test_scenario_rates_refresh_without_becoming_primary_money() -> None:
    body = payload("bytedance/seedance-2.0-mini", InferenceMethod.T2V)
    cap = model(body["model_id"])
    assert cap.pricing_evidence is not None
    changed = replace(
        cap,
        pricing_evidence=PricingEvidence(
            tuple(replace(sku, rate_usd=sku.rate_usd * 2) for sku in cap.pricing_evidence.skus)
        ),
    )
    before, after = run(body), run(body, cap=changed)
    assert_not_primary_money(after)
    assert scenario_amounts(after) == {amount * 2 for amount in scenario_amounts(before)}
    assert before.rates_hash != after.rates_hash


@pytest.mark.parametrize(
    "policy",
    [
        {"kind": "TOKEN_GEOMETRY", "note": "synthetic", "floor_evidence": "GUESSED"},
        {"kind": "AUDIO_DURATION", "note": "synthetic", "rate": "1"},
        {"kind": "AUDIO_OUTPUT_COMPARISON", "note": "synthetic", "tier_skus": {"720p": "unknown"}},
        {"kind": "NOMINAL_UPSCALE", "note": ""},
    ],
)
def test_planning_policy_is_bounded_and_cannot_embed_prices_or_unknown_skus(
    policy: dict[str, Any],
) -> None:
    compiler: Callable[[object, tuple[str, ...]], object] = compile_planning_policy
    with pytest.raises(ValueError):
        compiler(policy, ("duration_seconds",))


def test_route_freshness_budget_uses_existing_ttl_and_observation_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run(payload("bytedance/seedance-2.0-mini", InferenceMethod.T2V))

    class Runtime:
        async def estimate_cost(self, inputs: object) -> EstimateResult:
            return result

    class Request:
        async def json(self) -> dict[str, Any]:
            return payload("bytedance/seedance-2.0-mini", InferenceMethod.T2V)

    class Clock:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return OBSERVED + timedelta(seconds=30)

    monkeypatch.setattr(routes, "get_runtime", lambda: Runtime())
    monkeypatch.setattr(routes, "datetime", Clock)
    monkeypatch.setattr(compat, "json_response", lambda body, status=200: (body, status))
    body, status = asyncio.run(routes._cost_estimate_handler(Request()))
    assert status == 200
    assert body["valid_for_ms"] == int(FRESH_TTL.total_seconds() * 1000) - 30000
    assert body["planning"]["display"] == "SCENARIO_RANGE"
    assert body["amount_usd"] is None
    assert body.get("estimated_cost_usd") is None
    assert body["lower_usd"] is body["upper_usd"] is None


def test_aleph_unknown_source_keeps_only_applicable_rate_and_explicit_floor() -> None:
    result = run(payload("runway/aleph-2", InferenceMethod.V2V_EDIT))
    assert result.state == "RATE_ONLY"
    assert_not_primary_money(result)
    assert result.rate_usd == Decimal("0.28") and result.rate_unit == "s"
    assert any(
        row.relation == "minimum" and row.amount_usd == Decimal("0.56") for row in result.breakdown
    )


def test_r31_source_preview_formula_keeps_advisory_hint_status() -> None:
    result = run(synthetic_hint(payload("runway/aleph-2", InferenceMethod.V2V_EDIT), "7.5"))
    assert result.state == "FORMULA" and result.amount_usd == Decimal("2.10")
    assert result.planning is None
    assert any("preview" in note and "hint" in note for note in result.assumptions)
    assert any("Advisory continuous formula" in note for note in result.assumptions)


@pytest.mark.parametrize("mutation", ["unstamped", "stale_revision", "wrong_occurrence"])
def test_unbound_preview_quantities_are_unknown_not_synthetic_zero(mutation: str) -> None:
    body = synthetic_hint(payload("bytedance/seedance-2.5", InferenceMethod.VR2V), "5")
    if mutation == "unstamped":
        body["media"][0].pop("occurrence_index")
        body["media"][0].pop("context_revision")
    elif mutation == "stale_revision":
        body["media"][0]["context_revision"] += 1
    else:
        body["media"][0]["occurrence_index"] += 1
    result = run(body)
    assert_not_primary_money(result)
    assert not result.planning or not result.planning.get("scenarios")


def test_public_known_cannot_bypass_revision_bound_hint_authority() -> None:
    body = synthetic_hint(payload("runway/aleph-2", InferenceMethod.V2V_EDIT), "7.5")
    body["media"][0]["status"] = "KNOWN"
    parsed = routes._parse_estimate_inputs(body)
    assert parsed.media[0].status == "HINT"
    body["media"][0].pop("occurrence_index")
    result = run(body)
    assert result.state == "RATE_ONLY" and result.amount_usd is None
    assert result.rate_usd == Decimal("0.28")


def test_explicit_hidden_control_is_invalid_not_silently_projected() -> None:
    body = payload("runway/aleph-2", InferenceMethod.V2V_EDIT)
    assert body["generate_audio"] is None
    body["generate_audio"] = False
    result = run(body)
    assert result.state == "INVALID" and result.amount_usd is None
    assert result.planning is None


def test_unstamped_revision_zero_has_no_metadata_authority_exception() -> None:
    body = synthetic_hint(payload("runway/aleph-2", InferenceMethod.V2V_EDIT), "7.5")
    body["context_revision"] = 0
    body["media"][0].pop("context_revision")
    body["media"][0].pop("occurrence_index")
    result = run(body)
    assert result.state == "RATE_ONLY" and result.amount_usd is None
