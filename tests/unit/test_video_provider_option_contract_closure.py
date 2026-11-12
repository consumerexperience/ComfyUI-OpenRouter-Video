from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.configuration import project_method, project_semantic_values
from openrouter_video.evidence_registry import enrich_capabilities, load_manifest
from openrouter_video.models import (
    GenerationRequest,
    InferenceMethod,
    ModelCapabilities,
    ProviderOption,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = json.loads(
    (ROOT / "tests/fixtures/op07-full-catalogue.json").read_text(encoding="utf-8")
)
MANIFEST = load_manifest()


def _model(model_id: str) -> ModelCapabilities:
    record = next(item for item in CATALOGUE["data"] if item["id"] == model_id)
    return enrich_capabilities(_parse_capability(record), MANIFEST)


def _provider_contract(model_id: str, method: str, provider: str) -> dict[str, Any]:
    method_profile = project_method(_model(model_id), method)
    assert method_profile["state"] == "SUPPORTED"
    control = method_profile["controls"]["provider_options"]
    assert control["state"] == "SUPPORTED"
    return cast(dict[str, Any], control["providers"][provider])


@pytest.mark.parametrize(
    ("model_id", "method"),
    [
        ("kwaivgi/kling-v3.0-pro", "T2V"),
        ("kwaivgi/kling-v3.0-pro", "I2V"),
        ("kwaivgi/kling-v3.0-pro", "FLF2V"),
        ("kwaivgi/kling-v3.0-std", "T2V"),
        ("kwaivgi/kling-v3.0-std", "I2V"),
        ("kwaivgi/kling-v3.0-std", "FLF2V"),
    ],
)
def test_kling_documented_controls_reach_validator_and_current_route_wire(
    model_id: str, method: str
) -> None:
    model = _model(model_id)
    options = _provider_contract(model_id, method, "atlas-cloud")
    assert options["cfg_scale"] == {"type": "number", "min": 0, "max": 1, "omitted_default": 0.5}
    assert options["negative_prompt"] == {"type": "string"}
    base = request_witness(model, InferenceMethod(method))
    assert base is not None
    for value in (0, 0.5, 1):
        request = replace(
            base,
            provider_options=(
                ProviderOption("atlas-cloud", "cfg_scale", value),
                ProviderOption("atlas-cloud", "negative_prompt", "offline example"),
            ),
        )
        RequestValidator().validate_capabilities(request, model)
        wire = cast(dict[str, Any], request.to_openrouter_payload())
        assert wire["provider"]["options"]["atlas-cloud"] == {
            "cfg_scale": value,
            "negative_prompt": "offline example",
        }


def test_kling_pro_t2v_restores_confirmed_method_without_claiming_geometry() -> None:
    profile = project_method(_model("kwaivgi/kling-v3.0-pro"), "T2V")
    assert profile["state"] == "SUPPORTED"
    assert profile["controls"]["resolution"]["state"] == "CONFLICT"
    assert profile["controls"]["size"]["state"] == "CONFLICT"


@pytest.mark.parametrize(
    ("model_id", "method"),
    [
        ("minimax/hailuo-3", "I2V"),
        ("minimax/hailuo-3", "FLF2V"),
        ("minimax/hailuo-3-max", "T2V"),
        ("minimax/hailuo-3-max", "I2V"),
        ("minimax/hailuo-3-max", "FLF2V"),
    ],
)
def test_minimax_h3_aigc_watermark_is_a_typed_boolean(model_id: str, method: str) -> None:
    contract = _provider_contract(model_id, method, "minimax")
    assert contract["aigc_watermark"] == {"type": "boolean", "omitted_default": False}
    defaulted = project_semantic_values(_model(model_id), method, {"provider_options": None})
    assert defaulted["provider_options"] == ()
    selected = project_semantic_values(
        _model(model_id),
        method,
        {"provider_options": (ProviderOption("minimax", "aigc_watermark", False),)},
    )
    assert selected["provider_options"] == (ProviderOption("minimax", "aigc_watermark", False),)
    wire = cast(
        dict[str, Any],
        GenerationRequest(
            model_id, "prompt", provider_options=selected["provider_options"]
        ).to_openrouter_payload(),
    )
    assert wire["provider"]["options"]["minimax"]["aigc_watermark"] is False


@pytest.mark.parametrize("method", ["T2V", "I2V"])
def test_kling_o1_negative_prompt_is_not_claimed_as_native_contract(method: str) -> None:
    profile = project_method(_model("kwaivgi/kling-video-o1"), method)
    option = profile["controls"].get("provider_options", {})
    assert option.get("state") != "SUPPORTED"
