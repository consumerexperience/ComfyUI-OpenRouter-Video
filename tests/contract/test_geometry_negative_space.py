"""Exact protected adapter AST outside owner-authorized geometry is unchanged."""

import ast
import copy
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_adapter_and_projection_changes_are_geometry_only() -> None:
    git = shutil.which("git")
    assert git is not None
    for name in ("comfy/nodes.py", "comfy/projection.py"):
        path = "src/openrouter_video/" + name
        original = ast.parse(
            subprocess.check_output(  # noqa: S603 - fixed revision and enumerated local paths
                [git, "-C", str(ROOT), "show", "7af8197:" + path], text=True, encoding="utf-8"
            )
        )
        current = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        current.body = [
            item
            for item in current.body
            if not (isinstance(item, ast.ImportFrom) and item.module == "openrouter_video.geometry")
        ]
        original_request = (
            next(
                item
                for item in ast.walk(original)
                if isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "GenerationRequest"
            )
            if name == "comfy/nodes.py"
            else None
        )
        for item in ast.walk(current):
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "execute"
                and any(arg.arg == "geometry_authority" for arg in item.args.args)
            ):
                assert item.args.args[-1].arg == "geometry_authority"
                item.args.args.pop()
                item.args.defaults.pop()
                blocks = [
                    statement
                    for statement in item.body
                    if isinstance(statement, ast.Try)
                    and any(
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == "wire_geometry"
                        for call in ast.walk(statement)
                    )
                ]
                assert len(blocks) == 1
                item.body.remove(blocks[0])
            if isinstance(item, ast.List):
                item.elts = [
                    elt
                    for elt in item.elts
                    if not (
                        isinstance(elt, ast.Call)
                        and elt.args
                        and isinstance(elt.args[0], ast.Constant)
                        and elt.args[0].value == "geometry_authority"
                    )
                ]
            if isinstance(item, ast.Dict):
                pairs = [
                    (key, value)
                    for key, value in zip(item.keys, item.values, strict=True)
                    if not (isinstance(key, ast.Constant) and key.value == "geometry_profile")
                ]
                item.keys = [key for key, _ in pairs]
                item.values = [value for _, value in pairs]
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "GenerationRequest"
            ):
                assert original_request is not None
                for keyword in item.keywords:
                    if keyword.arg in ("resolution", "aspect_ratio", "size"):
                        assert isinstance(keyword.value, ast.Name) and keyword.value.id in (
                            "wire_resolution",
                            "wire_aspect",
                            "wire_size",
                        )
                        keyword.value = copy.deepcopy(
                            next(k.value for k in original_request.keywords if k.arg == keyword.arg)
                        )
        assert ast.dump(current, include_attributes=False) == ast.dump(
            original, include_attributes=False
        ), path
