"""Headless-core architecture and forbidden-boundary contracts."""

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


def test_production_never_imports_test_harness_or_fixtures() -> None:
    violations = {
        path.name: sorted(
            name for name in _imports(path) if name == "tests" or name.startswith("tests.")
        )
        for path in PACKAGE_ROOT.rglob("*.py")
    }
    assert not {name: imports for name, imports in violations.items() if imports}


def test_comfy_production_uses_only_numbered_api_and_no_executor_internals() -> None:
    comfy_files = tuple((PACKAGE_ROOT / "comfy").glob("*.py"))
    imports = {path.name: _imports(path) for path in comfy_files}
    comfy_api_imports = {
        path: sorted(name for name in names if name.startswith("comfy_api"))
        for path, names in imports.items()
    }
    assert {path: names for path, names in comfy_api_imports.items() if names} == {
        "compat.py": ["comfy_api.v0_0_2"]
    }
    forbidden = {
        path: sorted(
            name
            for name in names
            if name == "execution"
            or name.startswith("execution.")
            or name == "comfy_execution"
            or name.startswith("comfy_execution.")
        )
        for path, names in imports.items()
    }
    assert not {path: names for path, names in forbidden.items() if names}


def test_comfy_adapter_cache_fallback_has_no_business_identity_or_nan() -> None:
    sources = {
        path.name: path.read_text(encoding="utf-8")
        for path in (PACKAGE_ROOT / "comfy").glob("*.py")
    }
    public_surface = sources["nodes.py"] + sources["extension.py"]
    assert 'float("nan")' not in public_surface
    assert "next_cache_token" in public_surface
    for forbidden in (
        "workflow_id",
        "session_id",
        "installation_id",
        "machine_id",
        "node_instance_id",
    ):
        assert forbidden not in public_surface


def test_resume_runtime_constructs_no_generate_or_submit_service() -> None:
    runtime = ast.parse((PACKAGE_ROOT / "comfy" / "runtime.py").read_text(encoding="utf-8"))
    resume = next(
        node
        for node in ast.walk(runtime)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "resume"
    )
    names = {node.id for node in ast.walk(resume) if isinstance(node, ast.Name)}
    assert "ResumeService" in names
    assert "GenerateService" not in names


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
        if path.name not in {"models.py", "persistence.py"} and "node_instance_id" in text:
            hits.append("node_instance_id")
        if hits:
            violations[path.name] = hits
    assert violations == {}


def test_production_has_no_testability_escape_hatches() -> None:
    forbidden = (
        "base_url",
        "follow_redirects=True",
        "verify=False",
        "transport retries",
        "identity_override",
        "arbitrary_headers",
    )
    violations = {
        path.name: [token for token in forbidden if token in path.read_text(encoding="utf-8")]
        for path in CORE_FILES
    }
    assert not {name: hits for name, hits in violations.items() if hits}
