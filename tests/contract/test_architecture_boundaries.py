"""Scaffold architecture and no-product-behavior contracts."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "openrouter_video"
CORE_FILES = tuple(path for path in PACKAGE_ROOT.glob("*.py") if path.name != "__init__.py")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_core_never_imports_comfyui() -> None:
    violations = {
        path.name: sorted(
            name for name in _imports(path) if name == "comfy" or name.startswith("comfy_")
        )
        for path in CORE_FILES
    }
    assert not {name: imports for name, imports in violations.items() if imports}


def test_core_files_are_documentation_only_seams() -> None:
    violations: list[str] = []
    for path in CORE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        statements = (
            tree.body[1:] if tree.body and isinstance(tree.body[0], ast.Expr) else tree.body
        )
        if statements:
            violations.append(path.name)
    assert violations == []


def test_source_contains_no_openrouter_network_implementation() -> None:
    forbidden = ("/api/v1/videos", "submit_video(", "httpx.", "OPENROUTER_API_KEY")
    violations: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hits = [token for token in forbidden if token in text]
        if hits:
            violations[str(path.relative_to(PACKAGE_ROOT))] = hits
    assert violations == {}
