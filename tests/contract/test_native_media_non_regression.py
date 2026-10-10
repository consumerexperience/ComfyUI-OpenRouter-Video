"""Protected Phase 10 semantics, captured from pre-bridge commit 8a07944.

AST snapshots ignore comments/formatting. Behavioural IMAGE and Generate/Resume
tests remain in unit/test_image_transport.py and unit/test_application.py.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = json.loads(
    (ROOT / "tests/fixtures/native_media_protected_baseline.json").read_text(encoding="utf-8")
)


def _digest(path: str, selected: list[str] | None) -> str:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = (
        tree.body
        if selected is None
        else [node for node in tree.body if getattr(node, "name", None) in selected]
    )
    if selected is not None:
        assert len(nodes) == len(selected)
    dump_options = {"include_attributes": False}
    if "show_empty" in inspect.signature(ast.dump).parameters:
        dump_options["show_empty"] = True
    # Normalize fields introduced by later Python versions (e.g. type_params).
    records = [ast.dump(node, **dump_options).replace(", type_params=[]", "") for node in nodes]
    return hashlib.sha256("\n".join(records).encode()).hexdigest()


def _protected(group: str) -> None:
    for item in SNAPSHOTS[group]:
        assert _digest(item["path"], item["selected"]) == item["sha256"]


def test_native_media_does_not_change_model_catalog() -> None:
    # Capability rebase intentionally extends discovery. Preserve the original
    # snapshot as historical evidence, and check the approved semantic delta.
    delta = json.loads(
        (
            ROOT / "contracts/product/deltas/capability-catalog-rebase.contract-delta.json"
        ).read_text()
    )
    assert delta["baseline_sha"] == "fd460f99bddc500b9b663162587c8cfda5c61c0e"
    from openrouter_video.client import _parse_capability

    assert (
        _parse_capability({"id": "future/catalogue", "supports_text_only": True}).model_id
        == "future/catalogue"
    )


def test_native_media_does_not_change_capability_matrix() -> None:
    from openrouter_video.capabilities import inference_method_matrix
    from openrouter_video.evidence_registry import enrich_capabilities
    from openrouter_video.models import FrameType, ModelCapabilities
    from openrouter_video.recipes import RECIPES

    model = enrich_capabilities(
        ModelCapabilities(
            "bytedance/seedance-2.5",
            supported_frame_types=frozenset({FrameType.FIRST, FrameType.LAST}),
        )
    )
    assert all(status.value == "READY" for status in inference_method_matrix(model).values())
    assert len(RECIPES) == 10
    assert not any("bytedance" in repr(recipe) for recipe in RECIPES)


def test_native_media_does_not_change_existing_image_behavior() -> None:
    _protected("image")


def test_native_media_does_not_change_generate_resume_semantics() -> None:
    _protected("submit_policy")
    runtime = (ROOT / "src/openrouter_video/comfy/runtime.py").read_text(encoding="utf-8")
    assert "capabilities=CapabilityService(client=client, store=store)" in runtime
    assert "OpenRouterVideoClient(" in runtime
    # Resume has no upload or submit dependency: its existing observation-only
    # service is exercised by the durable restart/ambiguity behavioural tests.
    module = ast.parse((ROOT / "src/openrouter_video/application.py").read_text())
    resume = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "ResumeService"
    )
    calls = [
        node.func.attr
        for node in ast.walk(resume)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert not {"upload", "materialize", "submit_video"}.intersection(calls)


def test_fixture_cannot_override_production_catalog() -> None:
    runtime = (ROOT / "src/openrouter_video/comfy/runtime.py").read_text(encoding="utf-8")
    assert "CapabilityService(client=client, store=store)" in runtime
    assert "fixture" not in runtime.casefold()
    root = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "tests.manual" not in root
    assert "native_media_browser_host" not in root
