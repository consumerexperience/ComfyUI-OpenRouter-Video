"""Protect generation/Resume behavior outside the explicit auth addition."""

import ast
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_existing_runtime_methods_are_unchanged() -> None:
    path = "src/openrouter_video/comfy/runtime.py"
    before = ast.parse(
        subprocess.check_output(["git", "show", f"796697a:{path}"], cwd=ROOT).decode()  # noqa: S603,S607
    )
    after = ast.parse((ROOT / path).read_text(encoding="utf-8"))

    def members(tree: ast.Module) -> dict[str, str]:
        cls = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "ProcessRuntime"
        )
        return {
            node.name: ast.dump(node)
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    old, new = members(before), members(after)
    assert set(new) - set(old) == {"validate_connection"}
    assert all(new[name] == value for name, value in old.items())
