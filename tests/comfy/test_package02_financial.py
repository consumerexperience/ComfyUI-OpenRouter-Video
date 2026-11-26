"""Financial-only completion against existing Core/catalogue; zero network."""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.client import _parse_capability
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import InferenceMethod, PricingEvidence, PricingSku
from openrouter_video.pricing import EstimateState
from tests.comfy.test_aci_r31_planning import RAW, model, payload, run, seedance_images


def empty(model_id: str, method: str) -> dict[str, Any]:
    body = payload(model_id, InferenceMethod(method))
    body.update(reference_count=0, reference_kinds=[], source_video_present=False, media=[])
    return body


@pytest.mark.parametrize(
    ("model_id", "method"),
    [
        ("alibaba/wan-2.6", "I2V"),
        ("alibaba/wan-3.0", "MMR2V"),
        ("bytedance/seedance-2.0", "MMR2V"),
        ("bytedance/seedance-2.5", "MI2V"),
        ("bytedance/seedance-2.5", "FLF2V"),
        ("bytedance/seedance-2.5", "VR2V"),
        ("bytedance/seedance-2.5", "AR2V"),
        ("runway/aleph-2", "V2V_EDIT"),
    ],
)
def test_empty_roles_have_scoped_financial_information_without_generation_readiness(
    model_id: str,
    method: str,
) -> None:
    body = empty(model_id, method)
    original = copy.deepcopy(body)
    result = run(body)
    assert body == original
    assert result.state is EstimateState.INVALID
    assert result.reason == "required_inputs_missing"
    assert result.amount_usd is result.estimated_cost_usd is None
    assert result.lower_usd is result.upper_usd is None
    advisory = result.precompletion_advisory
    assert advisory is not None
    assert advisory["actual_reference_kinds"] == []
    assert advisory["version"] in {"ACI-PRECOMPLETION-1", "ACI-PRECOMPLETION-2"}
    if advisory["version"] == "ACI-PRECOMPLETION-2":
        assert advisory["display"] in {"REFERENCE", "SCENARIOS", "RATE_ONLY", "UNKNOWN"}
        assert advisory["alternatives"]
        alternatives = advisory["alternatives"]
        assert isinstance(alternatives, list)
        for alternative in alternatives:
            assert alternative
    else:
        assert Decimal(str(advisory["amount_usd"])) >= 0


@pytest.mark.parametrize("kinds", [["image"], ["image", "video"]])
def test_wan_partial_inventory_preserves_unknown_quantities_and_alternatives(
    kinds: list[str],
) -> None:
    body = empty("alibaba/wan-3.0", "MMR2V")
    body.update(reference_kinds=kinds, reference_count=len(kinds))
    body["media"] = [dict(kind=kind, role="reference", status="UNKNOWN") for kind in kinds]
    before = copy.deepcopy(body)
    result = run(body)
    assert body == before
    # IMAGE+VIDEO already meets the mixed minimum. Its missing video metadata
    # remains honest uncertainty, not a fabricated quantity or input completion.
    if len(kinds) == 2:
        assert result.precompletion_advisory is None
        assert result.state in {
            EstimateState.RATE_ONLY,
            EstimateState.UNKNOWN,
            EstimateState.PARTIAL,
        }
    else:
        assert result.precompletion_advisory is not None
        assert result.precompletion_advisory["actual_reference_kinds"] == kinds


def test_alternative_mixed_completions_never_choose_one_hidden_media_set() -> None:
    result = run(empty("bytedance/seedance-2.0", "MMR2V"))
    advisory = result.precompletion_advisory
    assert advisory is not None
    assert advisory["version"] == "ACI-PRECOMPLETION-2"
    alternatives = advisory["alternatives"]
    assert isinstance(alternatives, list) and len(alternatives) > 1
    assert len(
        {tuple(sorted((item["kind"], item["count"]) for item in option)) for option in alternatives}
    ) == len(alternatives)
    assert not any(
        "duration_seconds" in item or "width" in item or "fps" in item
        for option in alternatives
        for item in option
    )


@pytest.mark.parametrize("count", [0, 1, 2, 15, 30, 31])
def test_seedance_connected_count_and_boundary_preserved(count: int) -> None:
    body = seedance_images(count)
    result = run(body)
    assert body["reference_count"] == count
    if count < 2:
        assert result.precompletion_advisory is not None
        assert result.state is EstimateState.INVALID
    elif count == 31:
        assert result.state is EstimateState.INVALID and result.precompletion_advisory is None
    else:
        assert result.state is EstimateState.FORMULA and result.precompletion_advisory is None


@pytest.mark.parametrize(
    "mutation", ["geometry", "duration", "audio_limit", "capacity", "provider"]
)
def test_hard_invalid_cannot_be_hidden_by_missing_media(mutation: str) -> None:
    body = empty("alibaba/wan-3.0", "MMR2V")
    if mutation == "geometry":
        body["resolution"] = "not-supported"
    elif mutation == "duration":
        body["duration"] = 999
    elif mutation == "audio_limit":
        body.update(reference_count=1, reference_kinds=["audio"])
        body["media"] = [
            dict(
                kind="audio",
                role="reference",
                status="HINT",
                duration_seconds="15.284535",
                occurrence_index=0,
                context_revision=1,
            )
        ]
    elif mutation == "capacity":
        body.update(reference_count=11, reference_kinds=["image"] * 11)
        body["media"] = [dict(kind="image", role="reference", status="UNKNOWN") for _ in range(11)]
    else:
        body["provider_controls"] = [dict(provider="invalid", key="invalid", number_value="2")]
        body["provider_policy_version"] = "ACI-1.0"
    result = run(body)
    if mutation == "provider":
        # Unknown pricing policy is not a claim of invalid generation. The
        # historical neutral-control boundary must remain honest and closed.
        assert result.state is EstimateState.UNKNOWN
        assert result.reason == "provider_configuration_pricing_unverified"
    else:
        assert result.state is EstimateState.INVALID
    assert result.precompletion_advisory is None and result.amount_usd is None


def test_rate_changes_recalculate_reference_without_hardcoded_prices() -> None:
    body = empty("alibaba/wan-2.6", "I2V")
    cap = model(body["model_id"])
    assert cap.pricing_evidence is not None
    doubled = replace(
        cap,
        pricing_evidence=PricingEvidence(
            tuple(PricingSku(sku.key, sku.rate_usd * 2) for sku in cap.pricing_evidence.skus)
        ),
    )
    a, b = run(body, cap=cap), run(body, cap=doubled)
    assert a.precompletion_advisory is not None and b.precompletion_advisory is not None
    assert (
        Decimal(str(b.precompletion_advisory["amount_usd"]))
        == Decimal(str(a.precompletion_advisory["amount_usd"])) * 2
    )
    assert a.rates_hash != b.rates_hash


def test_entire_existing_catalogue_and_supported_method_accounting() -> None:
    from openrouter_video.capabilities import eligible_methods

    records = []
    for raw in RAW["data"]:
        cap = model(raw["id"])
        for method in eligible_methods(cap):
            body = empty(cap.model_id, method.value)
            original = copy.deepcopy(body)
            result = run(body, cap=cap)
            assert body == original
            assert not (result.amount_usd is not None and result.precompletion_advisory is not None)
            advisory = result.precompletion_advisory
            if advisory:
                assert result.state is EstimateState.INVALID
                assert result.reason == "required_inputs_missing"
                assert advisory["actual_reference_kinds"] == []
            records.append(
                (
                    cap.model_id,
                    method.value,
                    result.state.value,
                    advisory["version"] if advisory else None,
                )
            )
    assert len({row[0] for row in records}) >= 30
    assert len(records) >= 124


@pytest.mark.parametrize("durations", [["10", "10"], ["15.000001"]])
def test_incomplete_mixed_shape_cannot_bypass_aggregate_or_individual_audio_limits(
    durations: list[str],
) -> None:
    body = empty("alibaba/wan-3.0", "MMR2V")
    body.update(reference_count=len(durations), reference_kinds=["audio"] * len(durations))
    body["media"] = [
        dict(
            kind="audio",
            role="reference",
            status="HINT",
            duration_seconds=duration,
            occurrence_index=index,
            context_revision=body["context_revision"],
        )
        for index, duration in enumerate(durations)
    ]
    result = run(body)
    assert result.state is EstimateState.INVALID
    assert result.amount_usd is None and result.precompletion_advisory is None


def test_recorded_frontend_completion_witnesses_equal_actual_backend() -> None:
    import json
    from dataclasses import asdict
    from pathlib import Path

    records = json.loads(
        (Path(__file__).parents[1] / "fixtures/package02-financial-witnesses.json").read_text(
            encoding="utf8"
        )
    )
    for record in records.values():
        result = asdict(run(record["request"]))
        result["state"] = result["state"].value
        result["availability"] = result["availability"].value
        result["valid_for_ms"] = 900000
        assert json.loads(json.dumps(result, default=str)) == record["result"]


def test_auto_mixed_completion_retains_only_documented_rates_with_unknown_extra_sku() -> None:
    body = empty("bytedance/seedance-2.5", "MMR2V")
    body["duration"] = -1
    cap = model(body["model_id"])
    assert cap.pricing_evidence is not None
    cap = replace(
        cap,
        supported_durations=(-1, *(cap.supported_durations or ())),
        pricing_evidence=PricingEvidence(
            (*cap.pricing_evidence.skus, PricingSku("unknown_extra_charge", Decimal("1")))
        ),
    )
    result = run(body, cap=cap)
    assert result.state is EstimateState.INVALID
    assert result.reason == "required_inputs_missing", (body, cap.supported_durations)
    assert result.amount_usd is None
    advisory = result.precompletion_advisory
    assert advisory is not None and advisory["display"] == "RATE_ONLY"
    assert advisory["amount_usd"] is None and not advisory["scenarios"]
    assert advisory["rates"]
    assert all(rate["rate_unit"] == "token" for rate in advisory["rates"])
    assert all("additional charges" in rate["assumption"] for rate in advisory["rates"])
    assert body["duration"] == -1 and body["media"] == []


@pytest.mark.parametrize("connected", [False, True])
def test_seedance_flash_owner_witness_has_rate_without_assumed_tokens(connected: bool) -> None:
    fixture = Path(__file__).parents[1] / "fixtures/aci_r31/seedance-2.5-flash-catalogue.json"
    cap = enrich_capabilities(_parse_capability(json.loads(fixture.read_text(encoding="utf-8"))))
    body = dict(
        schema_version=2,
        context_revision=1,
        model_id=cap.model_id,
        inference_method="I2V",
        duration=20,
        resolution="480p",
        aspect_ratio="16:9",
        generate_audio=False,
        reference_count=0,
        reference_kinds=[],
        media=[dict(kind="image", role="first_frame", status="UNKNOWN")] if connected else [],
    )
    result = run(body, cap=cap)
    assert result.amount_usd is result.lower_usd is result.upper_usd is None
    assert result.applied_skus == ("video_tokens_without_audio",)
    if connected:
        assert result.state is EstimateState.RATE_ONLY
        assert result.rate_usd == Decimal("0.000007")
        assert result.rate_unit == "token"
        assert result.precompletion_advisory is None
    else:
        assert result.state is EstimateState.INVALID
        assert result.precompletion_advisory is not None
        assert result.precompletion_advisory["display"] == "RATE_ONLY"
        assert result.precompletion_advisory["rates"][0]["rate_usd"] == "0.000007"
