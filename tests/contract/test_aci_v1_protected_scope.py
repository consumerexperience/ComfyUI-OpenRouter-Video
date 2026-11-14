"""ACI may change cost projection, never the accepted paid/credential lifecycle."""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "f8ba174347bd4bfed155dc64aec1d7168c39c1fa"
GIT = shutil.which("git")
assert GIT is not None


def baseline(path: str) -> str:
    assert GIT is not None
    return subprocess.check_output(  # noqa: S603 - fixed git and immutable source revision
        [GIT, "show", f"{BASELINE}:{path}"], cwd=ROOT
    ).decode()


def declarations(source: str) -> dict[str, str]:
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = ast.dump(node, include_attributes=False)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[f"{node.name}.{item.name}"] = ast.dump(item, include_attributes=False)
                else:
                    result.setdefault(f"{node.name}.__class_data__", "")
                    result[f"{node.name}.__class_data__"] += ast.dump(
                        item, include_attributes=False
                    )
    return result


def test_aci_runtime_changes_only_existing_estimate_branch() -> None:
    path = "src/openrouter_video/comfy/runtime.py"
    before = declarations(baseline(path))
    after = declarations((ROOT / path).read_text(encoding="utf8"))
    allowed = {"ProcessRuntime.estimate_cost"}
    assert set(after) - set(before) <= allowed
    for name in before.keys() - allowed:
        assert after.get(name) == before[name], name


def test_aci_routes_preserve_auth_oauth_registration_and_other_handlers() -> None:
    path = "src/openrouter_video/comfy/routes.py"
    before = declarations(baseline(path))
    after = declarations((ROOT / path).read_text(encoding="utf8"))
    allowed = {
        "_cost_estimate_handler",
        "_parse_estimate_inputs",
        "_cost_decimal",
        "_parse_cost_decimal",
        "_parse_cost_media",
        "_parse_cost_provider_control",
    }
    assert set(after) - set(before) <= allowed
    for name in before.keys() - allowed:
        assert after.get(name) == before[name], name
