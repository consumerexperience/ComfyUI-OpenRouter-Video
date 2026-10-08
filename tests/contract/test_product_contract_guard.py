"""Dogfood the Builder v0.5 Product Contract Guard on exact Phase 10 Git trees."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parent
BUILDER_ROOT = Path(
    os.environ.get(
        "OPENROUTER_VIDEO_BUILDER_RC",
        WORKSPACE / "plugins" / "openrouter-video-builder",
    )
)
GUARD_PATH = BUILDER_ROOT / "scripts" / "product_contract_guard.py"
EXPORTER_PATH = ROOT / "scripts" / "export_product_contract.py"
BASELINE_SHA = "b492184f41492d37677a2dde9afdbe88666717a2"
CURRENT_SHA = "08838ab93df2abe370d69dcc0375db3b135aa3fa"
BASELINE_PATH = (
    ROOT / "contracts/product/accepted/phase9-runtime-reliability-b492184.product-contract.json"
)
CURRENT_PATH = ROOT / "contracts/product/current/phase10-native-media-08838ab.product-contract.json"
DELTA_PATH = ROOT / "contracts/product/deltas/phase10-native-media.contract-delta.json"
CANDIDATE_PATH = (
    ROOT / "contracts/product/candidates/phase10-native-media-08838ab.acceptance-record.json"
)


def _module(name: str, path: Path) -> ModuleType:
    if not path.is_file():
        raise RuntimeError(f"Required side-by-side Builder RC file is absent: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _module("phase10_product_contract_guard", GUARD_PATH)
exporter = _module("phase10_product_contract_exporter", EXPORTER_PATH)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _export(revision: str, baseline: bool) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        exporter.export_contract(
            ROOT,
            revision,
            (
                "phase9-runtime-reliability-canonical-main"
                if baseline
                else "phase10-native-media-candidate-08838ab"
            ),
            (
                "openrouter-video-phase9-runtime-reliability-v1"
                if baseline
                else "openrouter-video-phase10-native-media-candidate-v1"
            ),
            ROOT
            / (
                "contracts/product/evidence/phase9-b492184.json"
                if baseline
                else "contracts/product/evidence/phase10-08838ab.json"
            ),
        ),
    )


def test_exact_git_exports_are_deterministic_and_match_snapshots() -> None:
    assert _export(BASELINE_SHA, True) == _load(BASELINE_PATH)
    assert _export(CURRENT_SHA, False) == _load(CURRENT_PATH)


def test_contracts_and_delta_validate_with_side_by_side_builder_rc() -> None:
    guard.validate_product_contract(_load(BASELINE_PATH))
    guard.validate_product_contract(_load(CURRENT_PATH))
    guard.validate_contract_delta(_load(DELTA_PATH))
    guard.validate_acceptance_record(_load(CANDIDATE_PATH))


def test_phase10_semantic_diff_has_no_unauthorized_delta() -> None:
    result = guard.semantic_diff(_load(BASELINE_PATH), _load(CURRENT_PATH), _load(DELTA_PATH))
    assert result["STATUS"] == "PASS"
    assert result["AUTHORIZED_DELTA"]
    assert result["UNAUTHORIZED_DELTA"] == []


def test_protected_resume_submit_regression_fails_even_if_snapshot_is_rewritten() -> None:
    current = copy.deepcopy(_load(CURRENT_PATH))
    current["surfaces"]["product_owned"]["lifecycle"]["resume_submit_authority"] = True
    result = guard.semantic_diff(_load(BASELINE_PATH), current, _load(DELTA_PATH))
    assert result["STATUS"] == "FAIL"
    assert any(
        item["path"].endswith("/lifecycle/resume_submit_authority")
        for item in result["UNAUTHORIZED_DELTA"]
    )


def test_fixture_evidence_cannot_define_catalogue_or_capability_semantics() -> None:
    current = _load(CURRENT_PATH)
    owned = json.dumps(current["surfaces"]["product_owned"], sort_keys=True).casefold()
    dynamic = current["surfaces"]["upstream_dynamic"]
    evidence = current["surfaces"]["observed_evidence"]
    assert "fixture" not in owned
    assert dynamic["immutable_model_count"] is False
    assert "fixture" not in evidence["observation_source"].casefold()
