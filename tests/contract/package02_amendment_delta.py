"""Exact proposed amendments 10–12; no acceptance or physical enforcement implied."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "0e55e984471ad8a8aecc91d8bd580ea3856520d8"


def _final_aci_predecessor(path: str, current: str) -> str:
    protected = "d3dcc6e1982ea6da901afd49b42432bb25deaa5c"
    pricing = "src/openrouter_video/pricing.py"
    rules = "src/openrouter_video/data/video-tariff-rules.json"
    if path not in {pricing, rules}:
        return current
    pin = json.loads(
        (ROOT / "tests/fixtures/package02-final-aci-source-candidate.json").read_text(
            encoding="utf8"
        )
    )
    entry = pin["files"][path]
    if (
        hashlib.sha256(current.replace("\r\n", "\n").encode()).hexdigest()
        != entry["candidate_sha256"]
    ):
        return current
    assert pin["baseline"] == protected and pin["status"] == "UNACCEPTED_FINAL_ACI"
    assert set(pin["files"]) == {pricing, rules, "web/openrouter_video.js"}
    git = shutil.which("git")
    assert git is not None
    before = subprocess.check_output(  # noqa: S603 - immutable local Git source
        [git, "show", f"{protected}:{path}"], cwd=ROOT
    ).decode("utf8")
    assert (
        hashlib.sha256(before.replace("\r\n", "\n").encode()).hexdigest()
        == entry["baseline_sha256"]
    )
    if path == rules:
        candidate = json.loads(current)
        additions = [
            p for p in candidate["profiles"] if p["model_id"] == "bytedance/seedance-2.5-flash"
        ]
        assert len(additions) == 1
        candidate["profiles"].remove(additions[0])
        assert candidate == json.loads(before)
    else:
        old, new = ast.parse(before), ast.parse(current)
        old_estimator = next(
            n
            for n in old.body
            if isinstance(n, ast.ClassDef) and n.name == "PreflightCostEstimator"
        )
        new_estimator = next(
            n
            for n in new.body
            if isinstance(n, ast.ClassDef) and n.name == "PreflightCostEstimator"
        )
        estimate = next(
            n for n in old_estimator.body if isinstance(n, ast.FunctionDef) and n.name == "estimate"
        )
        for index, node in enumerate(new_estimator.body):
            if isinstance(node, ast.FunctionDef) and node.name == "estimate":
                new_estimator.body[index] = estimate
        precompletion = next(
            n
            for n in old.body
            if isinstance(n, ast.FunctionDef) and n.name == "precompletion_cost_estimate"
        )
        for index, node in enumerate(new.body):
            if isinstance(node, ast.FunctionDef) and node.name == "precompletion_cost_estimate":
                new.body[index] = precompletion
        assert ast.dump(new) == ast.dump(old)
    return before


def package02_amendment_baseline_source(path: str, current: str) -> str:
    current = _final_aci_predecessor(path, current)
    pin = json.loads(
        (ROOT / "tests/fixtures/package02-amendments-source-candidate.json").read_text(
            encoding="utf8"
        )
    )
    digest = hashlib.sha256(current.replace("\r\n", "\n").encode()).hexdigest()
    if pin["files"].get(path) != digest:
        return current
    assert pin["status"] == "UNACCEPTED_PACKAGE02_FINAL_12" and pin["baseline"] == BASE
    git = shutil.which("git")
    assert git is not None
    before = subprocess.check_output([git, "show", f"{BASE}:{path}"], cwd=ROOT).decode("utf8")  # noqa: S603
    assert (
        hashlib.sha256(before.replace("\r\n", "\n").encode()).hexdigest()
        == pin["baseline_files"][path]
    )
    if path.endswith("configuration.py"):
        a, b = ast.parse(before), ast.parse(current)
        method = next(
            n
            for n in b.body
            if isinstance(n, ast.FunctionDef) and n.name == "_validate_provider_spec"
        )
        annotations = [
            n
            for n in method.body
            if isinstance(n, ast.If)
            and isinstance(n.test, ast.Compare)
            and isinstance(n.test.left, ast.Constant)
            and n.test.left.value == "presentation"
        ]
        assert len(annotations) == 1
        method.body.remove(annotations[0])
        for node in ast.walk(method):
            if isinstance(node, ast.Set):
                node.elts = [
                    v
                    for v in node.elts
                    if not (isinstance(v, ast.Constant) and v.value == "presentation")
                ]
        assert ast.dump(a) == ast.dump(b), (
            "Only bounded presentation metadata validation; no contract weakening"
        )
    elif path.endswith("comfy/nodes.py"):
        a, b = ast.parse(before), ast.parse(current)
        helpers = [
            n
            for n in b.body
            if isinstance(n, ast.FunctionDef) and n.name == "_creative_provider_label"
        ]
        assert len(helpers) == 1
        b.body.remove(helpers[0])
        labels = [
            n
            for n in ast.walk(b)
            if isinstance(n, ast.keyword)
            and n.arg == "display_name"
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "_creative_provider_label"
        ]
        assert len(labels) == 1
        labels[0].value = ast.Constant(value="negative prompt")
        assert ast.dump(a) == ast.dump(b), (
            "Only native STRING display label; "
            "paid lifecycle, schema wire IDs and outputs unchanged"
        )
    elif path.endswith("capability-evidence.json"):
        a, b = json.loads(before), json.loads(current)

        def strip(value: object) -> None:
            if isinstance(value, dict):
                value.pop("presentation", None)
                if value.get("text_semantic") == "creative_prompt":
                    value.pop("text_semantic")
                for child in value.values():
                    strip(child)
            elif isinstance(value, list):
                for child in value:
                    strip(child)

        strip(b)
        b["content_hash"] = a["content_hash"]
        assert a == b, (
            "Only reviewed UI semantics/labels; "
            "original domains, constraints, variants and capabilities exact"
        )
    return before
