"""Protect generation/Resume behavior outside the explicit auth addition."""

import ast
import shutil
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


def test_ci_typing_delta_preserves_credential_backend_mechanism() -> None:
    path = "src/openrouter_video/credential_backend.py"
    git_executable = shutil.which("git")
    assert git_executable is not None
    before = ast.parse(
        subprocess.check_output(  # noqa: S603 - fixed exact reviewed source
            [git_executable, "show", f"c0d96009f11785bac92f6e9e78d7fed8014a8455:{path}"], cwd=ROOT
        ).decode()
    )
    after = ast.parse((ROOT / path).read_text(encoding="utf-8"))

    class NormalizeFactory(ast.NodeTransformer):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom | None:
            if node.module == "collections.abc" and [a.name for a in node.names] == ["Callable"]:
                return None
            return node

        def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AnnAssign | None:
            if isinstance(node.target, ast.Name) and node.target.id == "linux_factory":
                assert isinstance(node.value, ast.Name) and node.value.id == "LinuxVault"
                assert ast.unparse(node.annotation) == "Callable[[], CredentialBackend]"
                return None
            return node

        def visit_Call(self, node: ast.Call) -> ast.Call:
            if isinstance(node.func, ast.Name) and node.func.id == "linux_factory":
                assert not node.args and not node.keywords
                node.func.id = "LinuxVault"
            return node

    assert ast.dump(NormalizeFactory().visit(after)) == ast.dump(before)
