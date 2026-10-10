"""Dogfood the Builder v0.5 Product Contract Guard on exact Phase 10 Git trees."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
BUILDER_OVERRIDE = os.environ.get("OPENROUTER_VIDEO_BUILDER_RC")
GUARD_PATH = (
    Path(BUILDER_OVERRIDE) / "scripts" / "product_contract_guard.py"
    if BUILDER_OVERRIDE
    else ROOT / "tests" / "tooling" / "product_contract_guard.py.fixture"
)
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
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, str(path))
    )
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


SHIELD = ROOT / "contracts/product/accepted/native-media-e2e-v1.product-contract.json"
SHIELD_DELTA = (
    ROOT / "contracts/product/deltas/native-media-e2e-regression-shield.contract-delta.json"
)


def _shield_current(accepted: dict[str, Any]) -> dict[str, Any]:
    current = copy.deepcopy(accepted)
    owners = {
        key: surface
        for surface, files in accepted["surfaces"]["product_owned"].items()
        for key in files
    }
    owned: dict[str, dict[str, str]] = {surface: {} for surface in set(owners.values())}
    files = list((ROOT / "src/openrouter_video").rglob("*")) + list((ROOT / "web").glob("*.js"))
    for path in files:
        if path.suffix not in {".py", ".json", ".js"}:
            continue
        key = path.relative_to(ROOT).as_posix().replace("/", "~1").replace(".", "_")
        surface = owners.get(key, "capabilities")
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        owned[surface][key] = hashlib.sha256(text.encode()).hexdigest()
    current["surfaces"]["product_owned"] = owned
    return current


def test_live_accepted_source_has_no_undeclared_protected_delta() -> None:
    accepted = _load(SHIELD)
    delta_path = os.environ.get("OPENROUTER_VIDEO_CONTRACT_DELTA")
    delta = _load(ROOT / delta_path) if delta_path else _load(SHIELD_DELTA)
    assert delta["baseline_sha"] == accepted["subject_sha"]
    result = guard.semantic_diff(accepted, _shield_current(accepted), delta)
    assert result["STATUS"] == "PASS", result["UNAUTHORIZED_DELTA"]


def test_every_protected_surface_rejects_unexpected_delta() -> None:
    accepted = _load(SHIELD)
    for surface, files in accepted["surfaces"]["product_owned"].items():
        current = copy.deepcopy(accepted)
        current["surfaces"]["product_owned"][surface][next(iter(files))] = "regression"
        result = guard.semantic_diff(accepted, current, _load(SHIELD_DELTA))
        assert result["STATUS"] == "FAIL", surface
        assert result["UNAUTHORIZED_DELTA"]


def test_shield_snapshot_cannot_be_rewritten_to_hide_source_regression() -> None:
    accepted = _load(SHIELD)
    assert accepted["subject_sha"] == "0f05665cb302fe4bc8398f2e9e04b08a5116a313"
    reader = exporter.TreeReader(ROOT, accepted["subject_sha"])
    for files in accepted["surfaces"]["product_owned"].values():
        for key, expected in files.items():
            stem, extension = key.rsplit("_", 1)
            relative = stem.replace("~1", "/") + "." + extension
            text = reader.text(relative).replace("\r\n", "\n")
            assert hashlib.sha256(text.encode()).hexdigest() == expected, relative


def test_live_receipt_is_bound_to_certified_product_not_shield_commit() -> None:
    receipt = _load(ROOT / "contracts/product/evidence/native-media-e2e-live-acceptance-v1.json")
    assert receipt["LIVE_TESTED_PRODUCT_SHA"] == _load(SHIELD)["subject_sha"]
    assert receipt["PAID_POST_COUNT"] == 1
    assert receipt["ACTUAL_COST_USD"] == "0.169617"
    assert receipt["FINAL_RESULT"] == "OPENROUTER_VIDEO_NATIVE_MEDIA_E2E_ACCEPTED"
    assert receipt["provenance"]["binary_committed"] is False
    assert receipt["provenance"]["native_inputs"] == ["IMAGE", "VIDEO", "AUDIO"]
    assert receipt["RESUBMIT_OCCURRED"] == "NO"
    assert receipt["REGRESSION_SHIELD_HEAD_SHA"] == "e861db343580e402293aab9b751d68255be07744"
    assert receipt["ACCEPTED_BASELINE_MERGE_SHA"] == "72998e931e5e9e59a277b63c2f2b0cd4cb513164"
    assert receipt["REGRESSION_SHIELD_CHECKPOINT_SHA"] == receipt["ACCEPTED_BASELINE_MERGE_SHA"]
    assert receipt["checkpoint_state"] == "ACCEPTED_CANONICAL"


def test_acceptance_index_resolves_new_checkpoint_tag_and_provenance() -> None:
    index = _load(ROOT / "contracts/product/acceptance-index.json")
    entry = next(
        item
        for item in index["accepted_canonical"]
        if item["checkpoint_tag"] == "openrouter-video-native-media-e2e-v1"
    )
    assert entry["protected_product_merge_sha"] == "72998e931e5e9e59a277b63c2f2b0cd4cb513164"
    assert entry["regression_shield_head_sha"] == "e861db343580e402293aab9b751d68255be07744"
    assert entry["live_tested_product_sha"] == "0f05665cb302fe4bc8398f2e9e04b08a5116a313"


def test_regression_contract_has_executable_coverage_and_no_paid_ci() -> None:
    contract = _load(ROOT / "contracts/product/accepted/native-media-e2e-v1.invariants.json")
    assert contract["paid_ci"] is False
    assert set(contract["invariants"]) == set(contract["executable_coverage"])
    for paths in contract["executable_coverage"].values():
        assert paths
        for path in paths:
            assert (ROOT / path).is_file()
            assert "def test_" in (ROOT / path).read_text(encoding="utf-8")
