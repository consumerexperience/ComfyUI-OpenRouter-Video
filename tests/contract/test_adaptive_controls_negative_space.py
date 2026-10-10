"""Protect existing semantics inside the six files authorized for configuration work."""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "72998e931e5e9e59a277b63c2f2b0cd4cb513164"


def baseline(path: str) -> str:
    git = shutil.which("git")
    assert git is not None
    return subprocess.check_output(  # noqa: S603 - fixed Git read of accepted source
        [git, "-C", str(ROOT), "show", f"{BASE}:{path}"], text=True, encoding="utf-8"
    )


def definitions(text: str) -> dict[str, str]:
    return {
        node.name: ast.dump(node, include_attributes=False)
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def test_existing_method_recipes_discovery_cache_and_http_classes_are_unchanged() -> None:
    for relative, exceptions in {
        "src/openrouter_video/capabilities.py": {"RequestValidator"},
        "src/openrouter_video/client.py": {"_parse_capability", "_optional_int_tuple"},
        "src/openrouter_video/evidence_registry.py": {"load_manifest", "enrich_capabilities"},
    }.items():
        before = definitions(baseline(relative))
        after = definitions((ROOT / relative).read_text(encoding="utf-8"))
        for name, original in before.items():
            if name not in exceptions:
                assert after[name] == original, (relative, name)


def test_request_validation_changes_only_configuration_capability_validation() -> None:
    relative = "src/openrouter_video/capabilities.py"
    methods = []
    for text in (baseline(relative), (ROOT / relative).read_text(encoding="utf-8")):
        validator = next(
            node
            for node in ast.parse(text).body
            if isinstance(node, ast.ClassDef) and node.name == "RequestValidator"
        )
        methods.append(
            {
                node.name: ast.dump(node, include_attributes=False)
                for node in validator.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name != "validate_capabilities"
            }
        )
    assert methods[0] == methods[1]


def test_protected_native_media_security_pricing_and_wire_files_are_exactly_preserved() -> None:
    paths = [
        "src/openrouter_video/application.py",
        "src/openrouter_video/models.py",
        "src/openrouter_video/persistence.py",
        "src/openrouter_video/pricing.py",
        "src/openrouter_video/pricing_profile.py",
        "src/openrouter_video/recipes.py",
        "src/openrouter_video/request_policy.py",
        "src/openrouter_video/transport.py",
        "src/openrouter_video/secrets.py",
        "src/openrouter_video/staging.py",
        "src/openrouter_video/s3_upload.py",
        "src/openrouter_video/local_media.py",
        "src/openrouter_video/image_transport.py",
        "src/openrouter_video/comfy/nodes.py",
        "src/openrouter_video/comfy/native_media.py",
        "src/openrouter_video/comfy/runtime.py",
        "src/openrouter_video/comfy/compat.py",
        "src/openrouter_video/data/capability-evidence.json",
    ]
    for path in paths:
        assert (ROOT / path).read_text(encoding="utf-8") == baseline(path), path
