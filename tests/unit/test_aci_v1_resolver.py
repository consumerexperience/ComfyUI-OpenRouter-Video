"""Production resolver boundaries; fixture identity never grants activation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from openrouter_video.models import InferenceMethod, ModelCapabilities, PricingEvidence, PricingSku
from openrouter_video.pricing import CostEstimateInputs, EstimateResult, PreflightCostEstimator

OBSERVED = datetime(2026, 11, 13, tzinfo=timezone.utc)


def model(model_id: str = "google/veo-3.1-fast") -> ModelCapabilities:
    return ModelCapabilities(
        model_id,
        canonical_slug=(
            "google/veo-3.1-fast-20260320" if model_id == "google/veo-3.1-fast" else model_id
        ),
        supports_text_only=True,
        supported_durations=(4, 8),
        supported_resolutions=("720p", "1080p", "4K"),
        supported_aspect_ratios=("16:9", "9:16"),
        generate_audio=True,
        pricing_evidence=PricingEvidence(
            (
                PricingSku("duration_seconds_without_audio", Decimal("0.10")),
                PricingSku("duration_seconds_with_audio", Decimal("0.12")),
                PricingSku("duration_seconds_without_audio_720p", Decimal("0.08")),
                PricingSku("duration_seconds_with_audio_720p", Decimal("0.10")),
                PricingSku("duration_seconds_without_audio_4k", Decimal("0.30")),
                PricingSku("duration_seconds_with_audio_4k", Decimal("0.30")),
            )
        ),
    )


def estimate(cap: ModelCapabilities, **kwargs: Any) -> EstimateResult:
    inputs = CostEstimateInputs(cap.model_id, duration=4, resolution="720p", **kwargs)
    return PreflightCostEstimator().estimate(cap, inputs, observed_at=OBSERVED)


@pytest.mark.parametrize(
    "audio,expected,sku",
    [
        (False, "0.32", "duration_seconds_without_audio_720p"),
        (True, "0.40", "duration_seconds_with_audio_720p"),
    ],
)
def test_specialized_tier_is_exclusive_not_generic_max(
    audio: bool, expected: str, sku: str
) -> None:
    result = estimate(model(), generate_audio=audio)
    assert result.estimated_cost_usd == Decimal(expected)
    assert result.applied_skus == (sku,)


def test_price_only_refresh_changes_number_and_rate_identity() -> None:
    original = model()
    assert original.pricing_evidence is not None
    changed = replace(
        original,
        pricing_evidence=PricingEvidence(
            tuple(replace(sku, rate_usd=sku.rate_usd * 2) for sku in original.pricing_evidence.skus)
        ),
    )
    before, after = estimate(original), estimate(changed)
    assert before.estimated_cost_usd == Decimal("0.32")
    assert after.estimated_cost_usd == Decimal("0.64")
    assert before.rates_hash != after.rates_hash
    assert before.rules_version == after.rules_version


def test_unknown_new_sku_fails_closed_instead_of_ignoring_fee() -> None:
    cap = model()
    assert cap.pricing_evidence is not None
    unknown = replace(
        cap,
        pricing_evidence=PricingEvidence(
            cap.pricing_evidence.skus + (PricingSku("unclassified_extra_fee", Decimal("0.4")),)
        ),
    )
    result = estimate(unknown)
    assert result.estimated_cost_usd is None
    assert result.availability.value == "UNAVAILABLE"
    assert result.reason


def test_missing_audio_does_not_match_explicit_false() -> None:
    result = estimate(model(), generate_audio=None)
    assert result.estimated_cost_usd is None
    assert result.availability.value == "UNAVAILABLE"


def test_exact_identity_no_provider_pattern_activation() -> None:
    result = estimate(model("unrecognized/veo-3.1-fast"))
    assert result.estimated_cost_usd is None


def test_unsupported_geometry_never_infers_silent_tier() -> None:
    cap = model()
    result = PreflightCostEstimator().estimate(
        cap, CostEstimateInputs(cap.model_id, duration=4, resolution="480p"), observed_at=OBSERVED
    )
    assert result.estimated_cost_usd is None


def test_legacy_fixed_generate_caller_remains_numeric() -> None:
    cap = ModelCapabilities(
        "fixture/fixed",
        supports_text_only=True,
        pricing_evidence=PricingEvidence((PricingSku("generate", Decimal("0")),)),
    )
    result = PreflightCostEstimator().estimate(
        cap, CostEstimateInputs(cap.model_id), observed_at=OBSERVED
    )
    assert result.estimated_cost_usd == Decimal("0")
    assert result.availability.value == "AVAILABLE"


def test_unexposed_method_is_not_activated_by_tariff() -> None:
    result = estimate(model(), inference_method=InferenceMethod.V2V_EXTEND)
    assert result.estimated_cost_usd is None


def synthetic_profile() -> dict[str, Any]:
    """One bounded test grammar profile, never registered for product activation."""
    return {
        "model_id": "fixture/strict",
        "canonical_slug": "fixture/strict-20261113",
        "capture_methods": ["T2V"],
        "known_skus": ["duration_seconds"],
        "rules": [
            {
                "id": "fixture:1",
                "when": {"method": ["T2V"]},
                "expected_state": "FORMULA",
                "charges": [
                    {
                        "sku": "duration_seconds",
                        "unit": "USD",
                        "quantity": "output_seconds",
                        "relation": "base",
                    }
                ],
                "reason": None,
                "evidence": "https://example.invalid/test-only",
                "activation": "CANDIDATE",
            }
        ],
        "sku_accounting": [
            {"sku": "duration_seconds", "disposition": "RULE_REFERENCE", "rule_ids": ["fixture:1"]}
        ],
        "gaps": [],
        "source": "https://example.invalid/test-only",
        "activation": "CANDIDATE_REQUIRES_FRESH_CAPTURE_AND_EVIDENCE_REVIEW",
        "default": {"state": "UNKNOWN", "reason": "NO_PROVEN_APPLICABLE_RULE"},
        "geometry_map": {},
        "geometry_status": "NOT_APPLICABLE",
    }


def test_profile_compiler_accepts_bounded_test_profile() -> None:
    from openrouter_video.pricing_profile import compile_profile

    compile_profile(synthetic_profile())


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_rules",
        "empty_charges",
        "minimum_only",
        "unknown_quantity",
        "unknown_unit",
        "unknown_relation",
        "unknown_activation",
        "unknown_disposition",
        "empty_predicate",
        "negative_duration",
        "zero_duration",
        "unknown_field",
        "raw_price",
        "unaccounted_sku",
    ],
)
def test_profile_compiler_rejects_semantic_schema_holes(mutation: str) -> None:
    from openrouter_video.pricing_profile import compile_profile

    raw = synthetic_profile()
    rule = raw["rules"][0]
    charge = rule["charges"][0]
    if mutation == "empty_rules":
        raw["rules"] = []
    elif mutation == "empty_charges":
        rule["charges"] = []
    elif mutation == "minimum_only":
        charge["relation"] = "minimum"
    elif mutation == "unknown_quantity":
        charge["quantity"] = "arbitrary_expression"
    elif mutation == "unknown_unit":
        charge["unit"] = "EUR"
    elif mutation == "unknown_relation":
        charge["relation"] = "multiply"
    elif mutation == "unknown_activation":
        rule["activation"] = "JUST_TRUST_IT"
    elif mutation == "unknown_disposition":
        raw["sku_accounting"][0]["disposition"] = "IGNORE"
    elif mutation == "empty_predicate":
        rule["when"]["method"] = []
    elif mutation == "negative_duration":
        rule["when"]["duration"] = [-5]
    elif mutation == "zero_duration":
        rule["when"]["duration"] = [0]
    elif mutation == "unknown_field":
        raw["api_key"] = "synthetic forbidden field"
    elif mutation == "raw_price":
        charge["rate"] = "0.1"
    elif mutation == "unaccounted_sku":
        raw["known_skus"].append("unexpected_fee")
    with pytest.raises(ValueError):
        compile_profile(raw)


def test_profile_duration_predicate_cannot_treat_boolean_as_one() -> None:
    from openrouter_video.pricing_profile import compile_profile

    raw = synthetic_profile()
    raw["rules"][0]["when"]["duration"] = [True]
    with pytest.raises(ValueError):
        compile_profile(raw)


def test_equal_alias_guard_is_rechecked_after_rate_refresh() -> None:
    cap = ModelCapabilities(
        "kwaivgi/kling-v3.0-pro",
        canonical_slug="kwaivgi/kling-v3.0-pro-20260429",
        supports_text_only=True,
        supported_durations=(5,),
        supported_resolutions=("720p",),
        generate_audio=True,
        pricing_evidence=PricingEvidence(
            tuple(
                PricingSku(key, Decimal(rate))
                for key, rate in (
                    ("duration_seconds", "0.112"),
                    ("duration_seconds_with_audio", "0.168"),
                    ("text_to_video_duration_seconds_480p", "0.112"),
                    ("text_to_video_duration_seconds_720p", "0.112"),
                    ("image_to_video_duration_seconds_720p", "0.112"),
                    ("text_to_video_duration_seconds_1080p", "0.112"),
                    ("image_to_video_duration_seconds_1080p", "0.112"),
                )
            )
        ),
    )
    selected = CostEstimateInputs(cap.model_id, duration=5, resolution="720p", generate_audio=False)
    before = PreflightCostEstimator().estimate(cap, selected, observed_at=OBSERVED)
    assert before.estimated_cost_usd == Decimal("0.560")
    assert cap.pricing_evidence is not None
    divergent = replace(
        cap,
        pricing_evidence=PricingEvidence(
            tuple(
                replace(sku, rate_usd=Decimal("0.13")) if sku.key == "duration_seconds" else sku
                for sku in cap.pricing_evidence.skus
            )
        ),
    )
    after = PreflightCostEstimator().estimate(divergent, selected, observed_at=OBSERVED)
    assert after.estimated_cost_usd is None
    assert after.reason


def fixture_model(model_id: str) -> ModelCapabilities:
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
        _parse_capability(next(row for row in rows if row["id"] == model_id)), load_manifest()
    )


def test_seedance_video_input_is_applicable_rate_only_never_output_formula() -> None:
    from openrouter_video.capabilities import request_witness

    cap = fixture_model("bytedance/seedance-2.5")
    witness = request_witness(cap, InferenceMethod.VR2V)
    assert witness is not None and witness.input_references is not None
    kinds = tuple(reference.kind for reference in witness.input_references.references)
    selected = CostEstimateInputs(
        cap.model_id,
        duration=witness.duration,
        resolution=witness.resolution,
        aspect_ratio=witness.aspect_ratio,
        size=witness.size,
        generate_audio=False,
        inference_method=InferenceMethod.VR2V,
        reference_kinds=kinds,
        reference_count=len(kinds),
    )
    result = PreflightCostEstimator().estimate(cap, selected, observed_at=OBSERVED)
    assert result.state == "RATE_ONLY"
    assert result.rate_usd == Decimal("0.0000064")
    assert result.rate_unit == "token"
    assert result.estimated_cost_usd is None
    assert result.lower_usd is None and result.upper_usd is None


def test_source_edit_missing_duration_has_applicable_unit_rate_not_total() -> None:
    cap = fixture_model("black-forest-labs/flux-video-edit")
    selected = CostEstimateInputs(
        cap.model_id, inference_method=InferenceMethod.V2V_EDIT, source_video_present=True
    )
    result = PreflightCostEstimator().estimate(cap, selected, observed_at=OBSERVED)
    assert result.state == "RATE_ONLY"
    assert result.rate_usd == Decimal("0.03")
    assert result.rate_unit == "s"
    assert result.estimated_cost_usd is None


def test_metadata_adapter_reads_callbacks_without_encoding_or_execution() -> None:
    from pathlib import Path

    from openrouter_video.local_media import LocalMedia
    from openrouter_video.models import InputReferenceKind
    from openrouter_video.pricing import metadata_from_local_media

    def forbidden_write(path: Path) -> None:
        raise AssertionError("cost metadata must never encode/stage media")

    media = LocalMedia(
        "video/mp4", ".mp4", forbidden_write, duration=lambda: 7.5, geometry=lambda: (1920, 1080)
    )
    metadata = metadata_from_local_media(media, kind=InputReferenceKind.VIDEO, role="source_video")
    assert metadata.duration_seconds == Decimal("7.5")
    assert (metadata.width, metadata.height) == (1920, 1080)
    assert metadata.status == "KNOWN"


def test_metadata_cannot_override_core_geometry_or_reference_count() -> None:
    from openrouter_video.models import InputReferenceKind
    from openrouter_video.pricing import MediaCostMetadata

    cap = model()
    metadata = MediaCostMetadata(
        InputReferenceKind.IMAGE, "reference", width=1280, height=720, status="KNOWN"
    )
    for selected in (
        CostEstimateInputs(cap.model_id, duration=4, resolution="480p", media=(metadata,)),
        CostEstimateInputs(
            cap.model_id,
            duration=4,
            resolution="720p",
            reference_count=0,
            reference_kinds=(),
            media=(metadata,),
        ),
    ):
        result = PreflightCostEstimator().estimate(cap, selected, observed_at=OBSERVED)
        assert result.state == "INVALID"
        assert result.estimated_cost_usd is None


def test_profile_rejects_broad_and_specific_exclusive_overlap() -> None:
    from copy import deepcopy

    from openrouter_video.pricing_profile import compile_profile

    raw = synthetic_profile()
    narrow = deepcopy(raw["rules"][0])
    narrow["id"] = "fixture:2"
    narrow["when"]["generated_audio"] = [False]
    raw["rules"].append(narrow)
    raw["sku_accounting"][0]["rule_ids"].append("fixture:2")
    with pytest.raises(ValueError):
        compile_profile(raw)


def test_r31_owner_approved_aleph_source_formula_is_advisory_with_floor() -> None:
    from openrouter_video.capabilities import request_witness
    from openrouter_video.models import InputReferenceKind
    from openrouter_video.pricing import MediaCostMetadata

    cap = fixture_model("runway/aleph-2")
    witness = request_witness(cap, InferenceMethod.V2V_EDIT)
    assert witness is not None
    selected = CostEstimateInputs(
        cap.model_id,
        duration=witness.duration,
        resolution=witness.resolution,
        aspect_ratio=witness.aspect_ratio,
        size=witness.size,
        inference_method=InferenceMethod.V2V_EDIT,
        source_video_present=True,
        media=(
            MediaCostMetadata(
                InputReferenceKind.VIDEO,
                "source_video",
                duration_seconds=Decimal("7.5"),
                width=1920,
                height=1080,
                status="KNOWN",
            ),
        ),
    )
    result = PreflightCostEstimator().estimate(cap, selected, observed_at=OBSERVED)
    # Owner-approved R3.1 source-duration policy supersedes the earlier guard.
    # This is the supplied formula contract, not newly verified invoice evidence.
    assert result.state == "FORMULA"
    assert result.amount_usd == result.estimated_cost_usd == Decimal("2.10")
    assert result.planning is None
    assert result.provenance == "evidence-scoped catalogue tariff"
    assert any("Advisory continuous formula" in note for note in result.assumptions)
    assert any(
        row.quantity == Decimal("7.5") and row.rate_usd == Decimal("0.28") and row.evidence
        for row in result.breakdown
        if row.relation == "base"
    )
    assert result.lower_usd is None and result.upper_usd is None
    assert any(
        row.relation == "minimum" and row.amount_usd == Decimal("0.56") for row in result.breakdown
    )


def test_one_documented_output_second_sku_uses_shared_arithmetic_for_ordinary_intent() -> None:
    for key, raw_rate in (
        ("duration_seconds", "0.03"),
        ("duration_seconds_720p", "0.03"),
        ("cents_per_video_output_second", "3"),
        ("cents_per_video_output_second_720p", "3"),
    ):
        cap = ModelCapabilities(
            "fixture/future-second",
            supports_text_only=True,
            supported_durations=(4,),
            supported_resolutions=("720p",),
            pricing_evidence=PricingEvidence((PricingSku(key, Decimal(raw_rate)),)),
        )
        result = PreflightCostEstimator().estimate(
            cap,
            CostEstimateInputs(cap.model_id, duration=4, resolution="720p"),
            observed_at=OBSERVED,
        )
        assert result.state == "FORMULA"
        assert result.amount_usd == Decimal("0.12")
        assert result.applied_skus == (key,)


def test_single_second_template_does_not_ignore_a_new_fee() -> None:
    cap = ModelCapabilities(
        "fixture/future-second",
        supports_text_only=True,
        supported_durations=(4,),
        supported_resolutions=("720p",),
        pricing_evidence=PricingEvidence(
            (
                PricingSku("duration_seconds_720p", Decimal("0.03")),
                PricingSku("unknown_extra_fee", Decimal("0.4")),
            )
        ),
    )
    result = PreflightCostEstimator().estimate(
        cap, CostEstimateInputs(cap.model_id, duration=4, resolution="720p"), observed_at=OBSERVED
    )
    assert result.amount_usd is None
    assert result.availability.value == "UNAVAILABLE"


def test_single_second_template_never_borrows_a_different_resolution() -> None:
    cap = ModelCapabilities(
        "fixture/future-second",
        supports_text_only=True,
        supported_durations=(4,),
        supported_resolutions=("720p", "1080p"),
        pricing_evidence=PricingEvidence((PricingSku("duration_seconds_1080p", Decimal("0.03")),)),
    )
    result = PreflightCostEstimator().estimate(
        cap, CostEstimateInputs(cap.model_id, duration=4, resolution="720p"), observed_at=OBSERVED
    )
    assert result.amount_usd is None
    assert result.availability.value == "UNAVAILABLE"


def test_generic_legacy_bridge_requires_duration_invariant_charge_plan() -> None:
    from openrouter_video.pricing import _legacy_profile_is_complete
    from openrouter_video.pricing_profile import TariffCase, TariffProfile

    def case(sku: str, durations: tuple[object, ...], resolution: str = "720p") -> TariffCase:
        return TariffCase(
            id=sku,
            when=(("method", ("T2V",)), ("resolution", (resolution,)), ("duration", durations)),
            expected_state="FORMULA",
            charges=({"sku": sku, "unit": "USD", "quantity": "output_seconds"},),
            reason=None,
            evidence="https://example.invalid/test-only-tariff-contract",
            active=True,
        )

    short = case("short_seconds", (5, 15))
    long = case("long_seconds", (16, 20))
    profile = TariffProfile(
        model_id="synthetic/conditional",
        canonical_slug="synthetic/conditional-v1",
        known_skus=("short_seconds", "long_seconds"),
        rules=(short, long),
        geometry_map={},
        geometry_status="NOT_APPLICABLE",
        default_reason="unknown",
        source="test",
    )
    inputs = CostEstimateInputs(profile.model_id, duration=20, resolution="720p")
    assert not _legacy_profile_is_complete(profile, inputs)
    assert not _legacy_profile_is_complete(profile, replace(inputs, duration=15))
    # Splitting a domain without changing its charge plan does not lose legacy support.
    same_plan = replace(profile, rules=(short, replace(long, charges=short.charges)))
    assert _legacy_profile_is_complete(same_plan, inputs)
    # An unrelated explicit resolution is not a duration-conditioned alias conflict.
    other_tier = replace(profile, rules=(long, case("other_seconds", (20,), "1080p")))
    assert _legacy_profile_is_complete(other_tier, inputs)


def test_documented_grok_legacy_t2v_bridge_remains_available() -> None:
    import json
    from pathlib import Path

    from openrouter_video.client import _parse_capability
    from openrouter_video.evidence_registry import enrich_capabilities

    raw = json.loads(
        (Path(__file__).parents[1] / "fixtures/op07-topology-catalogue-b628912.json").read_text(
            encoding="utf8"
        )
    )
    cap = enrich_capabilities(
        _parse_capability(
            next(row for row in raw["data"] if row["id"] == "x-ai/grok-imagine-video")
        )
    )
    cap = replace(
        cap,
        pricing_evidence=PricingEvidence((PricingSku("per-video-second-720p", Decimal("0.03")),)),
    )
    result = PreflightCostEstimator().estimate(
        cap, CostEstimateInputs(cap.model_id, duration=4, resolution="720p"), observed_at=OBSERVED
    )
    assert result.state == "FORMULA"
    assert result.amount_usd == Decimal("0.12")
