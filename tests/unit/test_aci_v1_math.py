"""Literal owner arithmetic conformance, independent of production quantities/rates.

Synthetic cases exercise grammar only; they never enable a model tariff.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.pricing_profile import (
    calculate_quantity,
    calculate_range,
    decimal_value,
    evaluate_charge_plan,
    normalize_rate,
)

GOLDENS = json.loads(
    (Path(__file__).parents[1] / "fixtures/aci_v1/mathematical-golden-tests.json").read_text(
        encoding="utf-8"
    )
)["cases"]


@pytest.mark.parametrize("case", GOLDENS, ids=lambda case: case["id"])
def test_literal_owner_math(case: dict[str, Any]) -> None:
    contract = case["input"]
    flags = {
        k: contract[k] for k in ("stale", "invalid", "conflict", "unknown_charge") if k in contract
    }
    result = evaluate_charge_plan(contract["charges"], contract.get("values", {}), **flags)
    assert result.state == case["expected"]["state"]
    literal = case["expected"]["amount"]
    assert result.amount_usd == (Decimal(literal) if literal is not None else None)


@pytest.mark.parametrize(
    "bad", [True, False, 0.1, None, "NaN", "sNaN", "Infinity", "-Infinity", "-0.01", "", {}, []]
)
def test_decimal_boundary_rejects_malformed_and_binary_values(bad: object) -> None:
    with pytest.raises(ValueError):
        decimal_value(bad)


@pytest.mark.parametrize(
    "raw,unit,expected",
    [("3.5", "cents", "0.035"), ("10.7", "USD_per_million", "0.0000107"), ("0", "USD", "0")],
)
def test_rate_normalization_once(raw: str, unit: str, expected: str) -> None:
    assert normalize_rate(raw, unit) == Decimal(expected)


@pytest.mark.parametrize(
    "quantity", ["width", "script_words_per_second", "__import__('os')", "unknown"]
)
def test_quantity_ids_are_bounded(quantity: str) -> None:
    with pytest.raises(ValueError):
        calculate_quantity(quantity, {"width": 1280, "height": 720, "output_seconds": 5})


@pytest.mark.parametrize("bad", [True, "NaN", "Infinity", "-1", 1.2, None])
def test_malformed_rate_never_becomes_zero_or_number(bad: object) -> None:
    result = evaluate_charge_plan([{"rate": bad, "unit": "USD", "quantity": "fixed"}], {})
    assert result.state == "UNKNOWN"
    assert result.amount_usd is None


def test_free_allowance_clamps_before_rounding() -> None:
    result = evaluate_charge_plan(
        [
            {"rate": "0.1", "unit": "USD", "quantity": "fixed"},
            {"rate": "0.5", "unit": "USD", "quantity": "reference_images", "free": 5},
        ],
        {"reference_images": 2},
    )
    assert result.amount_usd == Decimal("0.1")


@pytest.mark.parametrize(
    "charges",
    [
        [{"rate": "1", "unit": "USD", "quantity": "output_seconds", "rounding_quantum": "0"}],
        [
            {
                "rate": "1",
                "unit": "USD",
                "quantity": "output_seconds",
                "tiers": [{"through": "2", "rate": "1"}],
            }
        ],
        [
            {
                "rate": "1",
                "unit": "USD",
                "quantity": "output_seconds",
                "tiers": [{"through": None, "rate": "1"}, {"through": "3", "rate": "2"}],
            }
        ],
        [
            {
                "rate": "1",
                "unit": "USD",
                "quantity": "output_seconds",
                "tiers": [{"through": "3", "rate": "1"}, {"through": "2", "rate": "2"}],
            }
        ],
    ],
)
def test_invalid_quantum_or_incomplete_tiers_fail_closed(charges: list[dict[str, Any]]) -> None:
    result = evaluate_charge_plan(charges, {"output_seconds": 4})
    assert result.state == "UNKNOWN"
    assert result.amount_usd is None


def test_range_requires_every_alternative_complete() -> None:
    a = evaluate_charge_plan(
        [{"rate": "0.1", "unit": "USD", "quantity": "output_seconds"}], {"output_seconds": 4}
    )
    b = evaluate_charge_plan(
        [{"rate": "0.2", "unit": "USD", "quantity": "output_seconds"}], {"output_seconds": 4}
    )
    missing = evaluate_charge_plan([{"rate": "0.2", "unit": "USD", "quantity": "unknown"}], {})
    complete = calculate_range([a, b])
    assert complete.state == "RANGE"
    assert (complete.lower_usd, complete.upper_usd) == (Decimal("0.4"), Decimal("0.8"))
    assert complete.amount_usd is None
    for alternatives in ([], [a, missing]):
        incomplete = calculate_range(alternatives)
        assert incomplete.state == "UNKNOWN"
        assert incomplete.amount_usd is None
        assert incomplete.lower_usd is None and incomplete.upper_usd is None


def test_rate_refresh_is_dynamic_without_second_discount() -> None:
    charges = [{"sku": "fixture", "unit": "cents", "quantity": "output_seconds"}]
    before = evaluate_charge_plan(charges, {"output_seconds": 4}, rates={"fixture": "7"})
    after = evaluate_charge_plan(charges, {"output_seconds": 4}, rates={"fixture": "3.5"})
    assert before.amount_usd == Decimal("0.28")
    assert after.amount_usd == Decimal("0.14")


@pytest.mark.parametrize(
    "kind,values",
    [
        ("video_tokens_output_24", {"width": 0, "height": 720, "output_seconds": 5}),
        ("video_tokens_output_24", {"width": "NaN", "height": 720, "output_seconds": 5}),
        (
            "megapixel_seconds_binary_output_24",
            {"width": 1920, "height": "Infinity", "output_seconds": 5},
        ),
        ("reference_images", {"reference_images": "1.5"}),
        ("active_image_inputs", {"active_image_inputs": 1000000000000000000000000000000000000}),
    ],
)
def test_quantity_domains_reject_zero_geometry_fractional_or_unbounded_counts(
    kind: str, values: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        calculate_quantity(kind, values)


def test_correlated_range_enumerates_only_complete_allowed_pairs() -> None:
    # Documented finite pairs: short/audio and long/silent. Cross-products are forbidden.
    short_audio = evaluate_charge_plan(
        [{"rate": "0.30", "unit": "USD", "quantity": "output_seconds"}],
        {"output_seconds": 4},
    )
    long_silent = evaluate_charge_plan(
        [{"rate": "0.10", "unit": "USD", "quantity": "output_seconds"}],
        {"output_seconds": 8},
    )
    result = calculate_range([short_audio, long_silent])
    assert result.state == "RANGE"
    assert result.lower_usd == Decimal("0.8")
    assert result.upper_usd == Decimal("1.2")
    assert result.amount_usd is None


def test_owner_golden_fixture_retains_exact_supplied_bytes() -> None:
    path = Path(__file__).parents[1] / "fixtures/aci_v1/mathematical-golden-tests.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "759d9b8640e956b3ba20b8ec4b142c1cf094a6b2a21db533bdcdea3d3c197386"
    )
    assert len(GOLDENS) == 39
