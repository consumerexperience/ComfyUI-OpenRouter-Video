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


def wan_payload(
    output: int = 10,
    videos: tuple[str | None, ...] = ("5.041667",),
    audios: tuple[str | None, ...] = (),
) -> dict[str, Any]:
    body = payload("alibaba/wan-3.0", InferenceMethod.MMR2V)
    body.update(duration=output, resolution="1080p", aspect_ratio="16:9", generate_audio=False)
    kinds = ["image", "image"] + ["video"] * len(videos) + ["audio"] * len(audios)
    body.update(reference_count=len(kinds), reference_kinds=kinds)
    body["media"] = []
    for index, (kind, duration) in enumerate(
        [("image", None), ("image", None)]
        + [("video", value) for value in videos]
        + [("audio", value) for value in audios]
    ):
        item: dict[str, Any] = dict(kind=kind, role="reference", status="UNKNOWN")
        if duration is not None:
            item.update(
                status="HINT",
                duration_seconds=duration,
                occurrence_index=index,
                context_revision=body["context_revision"],
            )
            if kind == "video":
                item.update(width=720, height=416)
        body["media"].append(item)
    return body


@pytest.mark.parametrize(
    ("output", "videos", "audios", "reason"),
    [
        (25, ("5.041667",), (), "media_input_output_duration_exceeds_limit"),
        (30, ("5.041667",), (), "media_input_output_duration_exceeds_limit"),
        (10, ("8", "8"), (), "media_combined_duration_exceeds_limit"),
        (10, ("5.041667",), ("8", "8"), "media_combined_duration_exceeds_limit"),
    ],
)
def test_known_aggregate_violation_cannot_have_model_or_total(
    output: int,
    videos: tuple[str, ...],
    audios: tuple[str, ...],
    reason: str,
) -> None:
    result = run(wan_payload(output, videos, audios))
    assert result.state == "INVALID"
    assert result.reason == reason
    assert result.amount_usd is result.estimated_cost_usd is None
    assert result.planning is None


@pytest.mark.parametrize("output", [10, 20, 24])
@pytest.mark.parametrize("audio", [(), ("15",)])
def test_valid_duration_boundaries_remain_available_to_existing_pricing(
    output: int,
    audio: tuple[str, ...],
) -> None:
    result = run(wan_payload(output, audios=audio))
    assert result.state != "INVALID"
    assert result.planning is not None
    assert result.planning["display"] == ("DETAIL_ONLY" if audio else "MODELLED")


@pytest.mark.parametrize("output", [10, 20])
def test_individual_audio_just_over_limit_stays_invalid(output: int) -> None:
    assert run(wan_payload(output, audios=("15.284535",))).state == "INVALID"


def test_unknown_video_duration_is_not_zero_or_hard_invalid() -> None:
    result = run(wan_payload(videos=(None,)))
    assert result.state != "INVALID"
    assert result.amount_usd is None


def test_known_partial_sum_over_cap_is_invalid_even_with_unknown_duration() -> None:
    assert run(wan_payload(videos=("8", "8", None))).state == "INVALID"


@pytest.mark.parametrize("extra", ["0", "0.000001"])
def test_exact_aggregate_boundary_and_just_over(extra: str) -> None:
    from decimal import Decimal

    second = str(Decimal("7.5") + Decimal(extra))
    result = run(wan_payload(15, videos=("7.5", second)))
    assert (result.state == "INVALID") == (extra != "0")


def seedance_images(count: int) -> dict[str, Any]:
    body = payload("bytedance/seedance-2.5", InferenceMethod.MI2V)
    body.update(duration=8, resolution="720p", aspect_ratio="16:9", generate_audio=False)
    body.update(reference_count=count, reference_kinds=["image"] * count)
    body["media"] = [dict(kind="image", role="reference", status="UNKNOWN") for _ in range(count)]
    return body


@pytest.mark.parametrize("count", [0, 1, 2, 15, 30, 31])
def test_image_boundaries_preserve_actual_intent_and_primary_readiness(count: int) -> None:
    body = seedance_images(count)
    saved = copy.deepcopy(body)
    result = run(body)
    assert body == saved
    if count in {0, 1}:
        assert result.state == "INVALID" and result.availability.value == "UNAVAILABLE"
        assert result.amount_usd is result.estimated_cost_usd is None
        assert result.lower_usd is result.upper_usd is None
        assert result.planning is None
        advisory = result.precompletion_advisory
        assert advisory is not None
        assert advisory["version"] == "ACI-PRECOMPLETION-1"
        assert advisory["actual_reference_kinds"] == ["image"] * count
        assert advisory["missing_inputs"] == [
            {"kind": "image", "role": "reference", "count": 2 - count}
        ]
        assert Decimal(str(advisory["amount_usd"])) == Decimal("1.8489600")
        assert advisory["scenario"]["amount_usd"] == advisory["amount_usd"]  # type: ignore[index]
        assert result.rates_hash
    elif count == 31:
        assert result.state == "INVALID" and result.precompletion_advisory is None
    else:
        assert result.state == "FORMULA" and result.amount_usd == Decimal("1.8489600")
        assert result.precompletion_advisory is None


@pytest.mark.parametrize(
    "change",
    [
        {"duration": 1000},
        {"resolution": "invalid"},
        {"size": "1280x720"},
        {"reference_count": 2},
        {"reference_kinds": ["audio"]},
        {"provider_controls": [{"provider": "unknown", "key": "unknown", "number_value": "2"}]},
    ],
)
def test_incomplete_shape_cannot_mask_other_invalid_intent(change: dict[str, Any]) -> None:
    body = seedance_images(1)
    body.update(change)
    result = run(body)
    assert result.precompletion_advisory is None
    assert result.amount_usd is None


def test_no_advisory_for_stale_catalogue_or_missing_rates() -> None:
    assert run(seedance_images(1), fresh=False).precompletion_advisory is None
    cap = replace(model("bytedance/seedance-2.5"), pricing_evidence=None)
    assert run(seedance_images(1), cap=cap).precompletion_advisory is None


def test_incomplete_input_with_known_bad_geometry_gets_no_advisory() -> None:
    body = payload("alibaba/wan-3.0", InferenceMethod.MI2V)
    body.update(reference_count=1, reference_kinds=["image"])
    body["media"] = [dict(kind="image", role="reference", status="UNKNOWN")]
    body["media"][0].update(
        status="HINT",
        width=1,
        height=1,
        occurrence_index=0,
        context_revision=1,
    )
    assert run(body).precompletion_advisory is None


@pytest.mark.parametrize("method", [InferenceMethod.I2V, InferenceMethod.FLF2V])
def test_missing_fixed_frames_are_not_fabricated_for_advisory(method: InferenceMethod) -> None:
    body = payload("bytedance/seedance-2.5", method)
    body["media"] = []
    result = run(body)
    assert result.amount_usd is None and result.precompletion_advisory is None


def test_accepted_seedance_mixed_witness_keeps_yellow_scenario_semantics() -> None:
    body = payload("bytedance/seedance-2.5", InferenceMethod.MMR2V)
    body.update(duration=23, resolution="720p", aspect_ratio="16:9", generate_audio=False)
    body.update(reference_count=4, reference_kinds=["image", "image", "video", "audio"])
    body["media"] = [
        dict(kind=kind, role="reference", status="UNKNOWN") for kind in body["reference_kinds"]
    ]
    for index, seconds in [(2, "5.041667"), (3, "15.284535")]:
        body["media"][index].update(
            status="HINT", duration_seconds=seconds, occurrence_index=index, context_revision=1
        )
    body["media"][2].update(width=720, height=416)
    result = run(body)
    assert result.precompletion_advisory is None
    assert planning(result)["display"] == "SCENARIO_RANGE"
    assert scenario_amounts(result) == {Decimal("5.3913600"), Decimal("5.3971200")}


def test_identical_independent_contexts_and_restore_do_not_share_mutable_advisory() -> None:
    first = seedance_images(1)
    other = copy.deepcopy(first)
    a, b = run(first), run(other)
    first["duration"] = 10
    changed = run(first)
    assert a.precompletion_advisory == b.precompletion_advisory
    assert changed.precompletion_advisory != b.precompletion_advisory
    assert run(copy.deepcopy(other)).precompletion_advisory == b.precompletion_advisory


def test_pux02_individual_and_aggregate_audio_details_keep_hint_authority() -> None:
    result = run(wan_payload(20, audios=("15.284535",)))
    assert result.state == "INVALID"
    first, group = result.validation_details
    assert first["field"] == "duration_seconds" and first["kind"] == "audio"
    assert first["kind_index"] == 1 and first["observed"] == "15.284535"
    assert first["bound"] == "15" and first["metadata_status"] == "HINT"
    assert group["field"] == "combined_duration" and group["bound"] == "15"


def test_pux02_combined_input_output_is_not_sum_of_inputs() -> None:
    result = run(wan_payload(30))
    detail = result.validation_details[0]
    assert detail["field"] == "input_output_duration"
    assert detail["observed"] == "35.041667" and detail["bound"] == "30"
    assert detail["correction_key"] == "shorten_input_or_output"


@pytest.mark.parametrize("count", [0, 1])
def test_pux02_distinct_types_and_reference_minimum_are_different(count: int) -> None:
    body = wan_payload(videos=())
    body.update(
        reference_count=count,
        reference_kinds=["image"] * count,
        media=[dict(kind="image", role="reference", status="UNKNOWN") for _ in range(count)],
    )
    result = run(body)
    assert result.state == "INVALID"
    assert any(
        d["field"] == "distinct_media_types" and d["observed"] == count and d["bound"] == 2
        for d in result.validation_details
    )


def test_pux02_advisory_retains_readiness_diagnostic_without_changing_primary() -> None:
    result = run(seedance_images(1))
    assert result.precompletion_advisory is not None and result.state == "INVALID"
    assert result.validation_details[0]["observed"] == 1
    assert result.validation_details[0]["bound"] == 2


def test_pux02_coupled_duration_exposes_existing_core_filtered_domain() -> None:
    body = payload("google/veo-3.1", InferenceMethod.T2V)
    body.update(duration=4, resolution="1080p", aspect_ratio="16:9")
    result = run(body)
    assert result.state == "UNKNOWN"  # Existing outcome preserved, not weakened.
    assert any(d["field"] == "duration" and d["allowed"] == [8] for d in result.validation_details)


def test_pux02_missing_frame_and_unknown_media_have_no_fabricated_quantities() -> None:
    body = payload("bytedance/seedance-2.5", InferenceMethod.I2V)
    body["media"] = []
    assert run(body).validation_details[0]["field"] == "first_frame"
    unknown = run(wan_payload(videos=(None,)))
    assert any(
        d["metadata_status"] == "UNKNOWN" and "observed" not in d
        for d in unknown.validation_details
    )
