"""Authoritative presentation annotations and native STRING wire parity; no traffic."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.comfy.nodes import _merge_linked_creative_text
from openrouter_video.comfy.projection import project_model
from openrouter_video.configuration import _validate_provider_spec, project_method
from openrouter_video.models import InferenceMethod, ProviderOption
from tests.comfy.test_aci_r31_planning import OBSERVED, model

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("method", [InferenceMethod.IR2V, InferenceMethod.AVATAR_AUDIO])
def test_heygen_native_motion_string_preserves_nested_wire_contract(
    method: InferenceMethod,
) -> None:
    cap = model("heygen/avatar-iv")
    profile = project_method(cap, method.value)
    spec = profile["controls"]["provider_options"]["providers"]["heygen"]["motion_prompt"]
    assert spec["text_semantic"] == "creative_prompt"
    assert profile["controls"]["prompt"]["state"] == (
        "SUPPORTED" if method is InferenceMethod.IR2V else "UNSUPPORTED"
    )
    witness = request_witness(cap, method)
    assert witness is not None
    saved = witness.provider_options
    merged = _merge_linked_creative_text(
        cap, method.value, saved, {"provider_option:heygen::motion_prompt": "look up\nsmile"}
    )
    request = replace(witness, provider_options=merged)
    RequestValidator().validate_capabilities(request, cap)
    provider = cast(dict[str, Any], request.to_openrouter_payload()["provider"])
    assert provider["options"]["heygen"]["motion_prompt"] == "look up\nsmile"
    assert ProviderOption("heygen", "motion_prompt", "look up\nsmile") in merged
    assert witness.provider_options == saved


def test_semantic_registry_delta_never_changes_provider_types_limits_variants_or_capabilities() -> (
    None
):
    git = shutil.which("git")
    assert git is not None
    path = "src/openrouter_video/data/capability-evidence.json"
    before = json.loads(
        subprocess.check_output(  # noqa: S603 - immutable local checkpoint
            [git, "show", f"0e55e984471ad8a8aecc91d8bd580ea3856520d8:{path}"], cwd=ROOT
        )
    )
    after = json.loads((ROOT / path).read_text(encoding="utf8"))

    def strip(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("presentation", None)
            if value.get("text_semantic") == "creative_prompt":
                value.pop("text_semantic")
            for child in value.values():
                strip(child)
        elif isinstance(value, list):
            for child in value:
                strip(child)

    strip(after)
    after["content_hash"] = before["content_hash"]
    assert before == after


@pytest.mark.parametrize("mid", ["heygen/avatar-iv", "alibaba/wan-2.6"])
def test_real_route_projection_fixture_matches_core(mid: str) -> None:
    fixture = json.loads(
        (ROOT / "tests/fixtures/package02-provider-projection.json").read_text(encoding="utf8")
    )
    expected = next(row for row in fixture["models"] if row["model_id"] == mid)
    actual = json.loads(json.dumps(project_model(model(mid), OBSERVED).as_dict(), default=str))
    for value in (expected, actual):
        for evidence in value["capability_evidence"]:
            if evidence.get("authority") in {"LIVE_STRUCTURED_API", "LIVE_CATALOGUE_EVIDENCE"}:
                assert isinstance(evidence.pop("observed_at"), str)
    assert expected == actual


@pytest.mark.parametrize(
    "view",
    [
        {"label": {"en": "Audio URL", "ru": "URL аудио"}, "group": "advanced", "input": "url"},
        {"label": {"en": "Motion prompt", "ru": "Движение"}, "group": "creative"},
    ],
)
def test_bounded_presentation_is_not_validation_or_transport(view: dict[str, Any]) -> None:
    spec = {"type": "string", "presentation": view}
    _validate_provider_spec(spec)
    original = copy.deepcopy(spec)
    assert spec == original


@pytest.mark.parametrize(
    "view",
    [
        None,
        {},
        {"label": {"en": "x"}, "group": "voice"},
        {"label": {"en": "x", "ru": "x"}, "group": "unknown"},
        {"label": {"en": "x", "ru": "x"}, "group": "voice", "input": "audio_socket"},
        {"label": {"en": "x", "ru": "x"}, "group": "voice", "endpoint": "https://bad.invalid"},
    ],
)
def test_malformed_semantics_cannot_broaden_authority(view: Any) -> None:
    with pytest.raises(ValueError):
        _validate_provider_spec({"type": "string", "presentation": view})
