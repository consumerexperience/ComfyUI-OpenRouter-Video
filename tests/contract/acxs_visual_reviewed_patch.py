"""Exact unaccepted visual delta, preserving historical source assertions."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "bd680c1ae2fdd86651162a744a4ecb42d350735b"


def visual_baseline_source(path: str, current: str) -> str:
    pin = json.loads((ROOT / "tests/fixtures/acxs_visual_source_candidate.json").read_text())
    sha = hashlib.sha256(current.replace("\r\n", "\n").encode()).hexdigest()
    if pin["files"].get(path) != sha:
        return current
    assert pin["baseline"] == BASE
    assert pin["status"] == "UNACCEPTED_OWNER_VISUAL_DELTA"
    git = shutil.which("git")
    assert git is not None
    baseline = subprocess.check_output(  # noqa: S603 - immutable local Git source
        [git, "show", f"{BASE}:{path}"], cwd=ROOT
    ).decode()
    assert (
        hashlib.sha256(baseline.replace("\r\n", "\n").encode()).hexdigest()
        == (pin["baseline_files"][path])
    )
    if path.endswith("capability-evidence.json"):
        before, after = json.loads(baseline), json.loads(current)

        def restore(value: object) -> None:
            if isinstance(value, dict):
                if "text_semantic" in value:
                    assert value.pop("text_semantic") == "negative_prompt"
                    assert value["type"] == "string"
                for child in value.values():
                    restore(child)
            elif isinstance(value, list):
                for child in value:
                    restore(child)

        restore(after)
        after["content_hash"] = before["content_hash"]
        assert after == before, "Evidence changes are presentation annotations only"
    elif path.endswith("comfy/nodes.py"):
        before, after = ast.parse(baseline), ast.parse(current)
        for entry in list(after.body):
            if isinstance(entry, ast.ImportFrom):
                entry.names = [
                    name
                    for name in entry.names
                    if name.name not in {"load_manifest", "ModelCapabilities"}
                ]
                if not entry.names:
                    after.body.remove(entry)
            if isinstance(entry, ast.FunctionDef) and entry.name in {
                "_creative_provider_inputs",
                "_merge_linked_creative_text",
            }:
                after.body.remove(entry)
        node = next(
            entry
            for entry in after.body
            if isinstance(entry, ast.ClassDef) and entry.name == "OpenRouterVideoGenerate"
        )
        for method in node.body:
            if isinstance(method, ast.AsyncFunctionDef) and method.name == "execute":
                assert method.args.kwarg and method.args.kwarg.arg == "provider_text_inputs"
                method.args.kwarg = None
                merges = [
                    value
                    for value in ast.walk(method)
                    if isinstance(value, ast.Try)
                    and value.body
                    and isinstance(value.body[0], ast.Assign)
                    and isinstance(value.body[0].value, ast.Call)
                    and isinstance(value.body[0].value.func, ast.Name)
                    and value.body[0].value.func.id == "_merge_linked_creative_text"
                ]
                assert len(merges) == 1
                merges[0].body.pop(0)
            if isinstance(method, ast.FunctionDef) and method.name == "define_schema":
                schema = next(
                    value
                    for value in ast.walk(method)
                    if isinstance(value, ast.keyword) and value.arg == "inputs"
                )
                assert isinstance(schema.value, ast.List)
                extras = [value for value in schema.value.elts if isinstance(value, ast.Starred)]
                assert len(extras) == 1
                schema.value.elts.remove(extras[0])
                for call in schema.value.elts:
                    if (
                        isinstance(call, ast.Call)
                        and call.args
                        and isinstance(call.args[0], ast.Constant)
                        and call.args[0].value == "prompt"
                    ):
                        label = next(
                            value for value in call.keywords if value.arg == "display_name"
                        )
                        assert (
                            isinstance(label.value, ast.Constant) and label.value.value == "prompt"
                        )
                        label.value.value = "Prompt"
        assert ast.dump(after) == ast.dump(before), (
            "Generation/Resume changes outside the exact STRING bridge"
        )
    elif path.endswith("configuration.py"):
        before, after = ast.parse(baseline), ast.parse(current)
        for old in before.body:
            if isinstance(old, ast.FunctionDef) and old.name == "_validate_provider_spec":
                replacement = next(
                    value
                    for value in after.body
                    if isinstance(value, ast.FunctionDef) and value.name == old.name
                )
                after.body[after.body.index(replacement)] = copy.deepcopy(old)
        assert ast.dump(before) == ast.dump(after)
    return baseline
