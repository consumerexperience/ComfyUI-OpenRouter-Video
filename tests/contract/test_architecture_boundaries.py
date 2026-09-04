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


def test_phase_5_and_comfy_product_modules_remain_documentation_only() -> None:
    deferred = {
        "application.py",
        "capabilities.py",
        "client.py",
        "lifecycle.py",
        "media.py",
        "models.py",
        "persistence.py",
    }
    violations: list[str] = []
    for path in (PACKAGE_ROOT / name for name in deferred):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        statements = (
            tree.body[1:] if tree.body and isinstance(tree.body[0], ast.Expr) else tree.body
        )
        if statements:
            violations.append(path.name)
    assert violations == []


def test_security_sensitive_production_ownership_is_centralized() -> None:
    sources = {path.name: path.read_text(encoding="utf-8") for path in CORE_FILES}
    env_owners = {name for name, text in sources.items() if "OPENROUTER_API_KEY" in text}
    header_owners = {name for name, text in sources.items() if "X-OpenRouter-Title" in text}
    async_client_owners = {
        name
        for name, text in sources.items()
        if "AsyncClient(" in text or "AsyncHTTPTransport(" in text
    }

    assert env_owners == {"secrets.py"}
    assert header_owners == {"request_policy.py"}
    assert async_client_owners == {"transport.py"}


def test_official_release_identity_is_owned_only_by_app_identity() -> None:
    sources = {path.name: path.read_text(encoding="utf-8") for path in CORE_FILES}
    referer_owners = {
        name
        for name, text in sources.items()
        if "https://github.com/consumerexperience/ComfyUI-OpenRouter-Video" in text
    }
    assert referer_owners == {"app_identity.py"}


def test_core_contains_no_tracking_telemetry_or_provider_branches() -> None:
    forbidden_imports = {"uuid", "getpass", "platform"}
    forbidden_tokens = (
        "gethostname(",
        "node_instance_id",
        "workflow_id",
        "installation_id",
        "machine_id",
        "analytics_sdk",
        "telemetry_backend",
        'provider == "',
        "model.startswith(",
    )
    violations: dict[str, list[str]] = {}
    for path in CORE_FILES:
        text = path.read_text(encoding="utf-8")
        imports = _imports(path) & forbidden_imports
        hits = sorted(imports) + [token for token in forbidden_tokens if token in text]
        if hits:
            violations[path.name] = hits
    assert violations == {}
