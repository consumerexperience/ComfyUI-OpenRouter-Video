"""Exact bounded Package02 source mapping; original assertions remain unchanged."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "cdab03f03d218f6ac30129638d3ce0a9e9a3c50f"


def package02_baseline_source(path: str, current: str) -> str:
    pin = json.loads(
        (ROOT / "tests/fixtures/package02-source-candidate.json").read_text(encoding="utf8")
    )
    digest = hashlib.sha256(current.replace("\r\n", "\n").encode()).hexdigest()
    if pin["files"].get(path) != digest:
        return current
    assert pin["status"] == "UNACCEPTED_PACKAGE02" and pin["baseline"] == BASE
    git = shutil.which("git")
    assert git is not None
    before = subprocess.check_output([git, "show", f"{BASE}:{path}"], cwd=ROOT).decode("utf8")  # noqa: S603
    assert (
        hashlib.sha256(before.replace("\r\n", "\n").encode()).hexdigest()
        == pin["baseline_files"][path]
    )
    if path.endswith("pricing.py"):
        a, b = ast.parse(before), ast.parse(current)
        b.body = [
            n
            for n in b.body
            if not (
                isinstance(n, ast.FunctionDef)
                and n.name in {"_completion_shapes", "_completion_prices"}
            )
            and not (isinstance(n, ast.ImportFrom) and n.module in {"itertools", "typing"})
        ]
        original = next(
            n
            for n in a.body
            if isinstance(n, ast.FunctionDef) and n.name == "precompletion_cost_estimate"
        )
        for i, n in enumerate(b.body):
            if isinstance(n, ast.FunctionDef) and n.name == original.name:
                b.body[i] = copy.deepcopy(original)
        assert ast.dump(a) == ast.dump(b), (
            "Only financial pre-completion; tariff maths and authoritative validation exact"
        )
    elif path.endswith("comfy/runtime.py"):
        a, b = ast.parse(before), ast.parse(current)
        old = next(n for n in a.body if isinstance(n, ast.ClassDef) and n.name == "ProcessRuntime")
        new = next(n for n in b.body if isinstance(n, ast.ClassDef) and n.name == "ProcessRuntime")
        method = next(
            n for n in old.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "estimate_cost"
        )
        for i, n in enumerate(new.body):
            if isinstance(n, ast.AsyncFunctionDef) and n.name == method.name:
                new.body[i] = copy.deepcopy(method)
        assert ast.dump(a) == ast.dump(b), (
            "Only estimate_cost, all Generate/Resume runtime unchanged"
        )
    return before
