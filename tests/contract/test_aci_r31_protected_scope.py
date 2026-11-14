"""Direct current-source guards for the Owner-approved R3.1 terminal UI delta."""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "15cc5aea7570fe43d2154b4e3b6f1efba8f4ac2d"


def baseline(path: str) -> str:
    git = shutil.which("git")
    assert git is not None
    return subprocess.check_output(  # noqa: S603 - fixed immutable Git source
        [git, "show", f"{BASELINE}:{path}"], cwd=ROOT
    ).decode("utf8")


def declarations(source: str) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result[f"{node.name}.{child.name}"] = child
    return result


def same(left: ast.AST, right: ast.AST) -> bool:
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def test_r31_runtime_preserves_every_non_estimate_method() -> None:
    path = "src/openrouter_video/comfy/runtime.py"
    before = declarations(baseline(path))
    after = declarations((ROOT / path).read_text(encoding="utf8"))
    for name in before:
        if name != "ProcessRuntime.estimate_cost":
            assert name in after and same(before[name], after[name]), name
    assert set(after) - set(before) <= {"ProcessRuntime.estimate_cost"}


def test_r31_routes_preserve_auth_oauth_registration_and_non_cost_handlers() -> None:
    path = "src/openrouter_video/comfy/routes.py"
    before = declarations(baseline(path))
    after = declarations((ROOT / path).read_text(encoding="utf8"))
    cost_names = {"_cost_estimate_handler", "_parse_estimate_inputs"}
    for name in before:
        if name not in cost_names and not name.startswith(("_cost_", "_parse_cost_")):
            assert name in after and same(before[name], after[name]), name
    assert all(name.startswith(("_cost_", "_parse_cost_")) for name in set(after) - set(before))


class _WithoutActualPresentation(ast.NodeTransformer):
    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "_node_output":
            node.args = node.args[:2]
            node.keywords = [
                field
                for field in node.keywords
                if field.arg not in {"operation_kind", "expected_job_id"}
            ]
        return node


def test_r31_nodes_change_only_terminal_ui_and_explicit_operation_metadata() -> None:
    path = "src/openrouter_video/comfy/nodes.py"
    before = declarations(baseline(path))
    after = declarations((ROOT / path).read_text(encoding="utf8"))
    allowed_terminal = {"_node_output", "_actual_ui_metadata"}
    assert set(after) - set(before) <= allowed_terminal
    for name in before:
        if name in allowed_terminal:
            continue
        if name in {"OpenRouterVideoGenerate.execute", "OpenRouterVideoResume.execute"}:
            assert same(
                _WithoutActualPresentation().visit(before[name]),
                _WithoutActualPresentation().visit(after[name]),
            ), name
        else:
            assert name in after and same(before[name], after[name]), name


def test_r31_output_declarations_keep_all_six_positional_outputs_exact() -> None:
    path = "src/openrouter_video/comfy/nodes.py"
    before = declarations(baseline(path))
    after = declarations((ROOT / path).read_text(encoding="utf8"))
    assert same(before["_outputs"], after["_outputs"])
    assert same(
        before["OpenRouterVideoResume.define_schema"], after["OpenRouterVideoResume.define_schema"]
    )
