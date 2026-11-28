"""Exporter disclosure must not rewrite history or claim partial new semantics."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "topology_contract_exporter", ROOT / "scripts/export_product_contract.py"
)
assert SPEC is not None and SPEC.loader is not None
EXPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORTER)


def test_historical_b628_media_policy_is_preserved() -> None:
    source = EXPORTER.TreeReader(ROOT, "b6289127e7d2e6f735f6497e7e6cf0f26c5adcac").text(
        "web/openrouter_video.js"
    )
    assert EXPORTER._media_transition_policy(source) == "preserve_state_and_block_generate"


def test_partial_projection_cannot_claim_new_contract() -> None:
    with pytest.raises(EXPORTER.ExportError, match="Incomplete"):
        EXPORTER._media_transition_policy("function projectMediaIntent(entries) {}")


def test_new_policy_requires_explicit_cause_boundary() -> None:
    source = (
        "function projectMediaIntent(entries) {}\n"
        "function reconcileReferenceTopology(node) {}\n"
        "if (transition.cause !== 'explicit') return;"
    )
    assert EXPORTER._media_transition_policy(source) == (
        "explicit_selection_park_restore_external_drift_preserve_and_block"
    )
    with pytest.raises(EXPORTER.ExportError, match="Incomplete"):
        EXPORTER._media_transition_policy(source.split("if (")[0])
