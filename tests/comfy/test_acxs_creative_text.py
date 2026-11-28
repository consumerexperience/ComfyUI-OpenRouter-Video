"""Native STRING schema/bridge contract, zero-spend real Core serialization."""

import asyncio
import json
import types
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.comfy import nodes
from openrouter_video.comfy.nodes import (
    OpenRouterVideoGenerate,
    _creative_provider_inputs,
    _merge_linked_creative_text,
)
from openrouter_video.configuration import _validate_provider_spec
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import InferenceMethod, ProviderOption

RAW = json.loads(
    (Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text(encoding="utf8")
)["data"]


def test_native_optional_string_inputs_keep_original_dynamic_machine_names() -> None:
    schema = cast(Any, OpenRouterVideoGenerate.define_schema())
    fields = {item.name: item for item in schema.inputs}
    identities = _creative_provider_inputs()
    assert set(identities) == {
        "provider_option:atlas-cloud::negative_prompt",
        "provider_option:google-vertex:parameters:negativePrompt",
        "provider_option:heygen::motion_prompt",
    }
    for name in identities:
        assert fields[name].options["multiline"] is True
        assert fields[name].options["optional"] is True
        assert fields[name].options["display_name"] == (
            "motion prompt"
            if name == "provider_option:heygen::motion_prompt"
            else "negative prompt"
        )
    assert fields["prompt"].options["multiline"] is True


@pytest.mark.parametrize(
    "mid,provider,container,key",
    [
        ("alibaba/wan-2.6", "atlas-cloud", None, "negative_prompt"),
        ("google/veo-3.1", "google-vertex", "parameters", "negativePrompt"),
    ],
)
def test_linked_text_uses_existing_validated_provider_wire_mapping(
    mid: str, provider: str, container: str | None, key: str
) -> None:
    model = enrich_capabilities(_parse_capability(next(row for row in RAW if row["id"] == mid)))
    witness = request_witness(model, InferenceMethod.T2V)
    assert witness is not None
    name = f"provider_option:{provider}:{container or ''}:{key}"
    old = ProviderOption(provider, key, "old preserved literal", container)
    saved = (old,)
    merged = _merge_linked_creative_text(model, "T2V", saved, {name: "grain\nblur"})
    assert saved == (old,)
    assert merged == (ProviderOption(provider, key, "grain\nblur", container),)
    request = replace(witness, provider_options=merged)
    RequestValidator().validate_capabilities(request, model)
    provider_payload = cast(dict[str, Any], request.to_openrouter_payload()["provider"])
    value = provider_payload["options"][provider]
    if container:
        value = value[container]
    assert value[key] == "grain\nblur"
    assert _merge_linked_creative_text(model, "T2V", saved, {name: ""}) == ()
    assert _merge_linked_creative_text(model, "T2V", saved, {}) == saved


def test_unsupported_or_non_string_link_never_grants_generation_authority() -> None:
    model = enrich_capabilities(
        _parse_capability(next(row for row in RAW if row["id"] == "bytedance/seedance-2.5"))
    )
    name = "provider_option:atlas-cloud::negative_prompt"
    for inputs in ({name: "unsupported"}, {name: ""}, {name: 42}, {"unreviewed_input": "text"}):
        with pytest.raises(ValueError):
            _merge_linked_creative_text(model, "T2V", (), inputs)


def test_presentation_semantics_do_not_relax_provider_validation() -> None:
    _validate_provider_spec({"type": "string", "text_semantic": "negative_prompt"})
    for spec in (
        {"type": "boolean", "text_semantic": "negative_prompt"},
        {"type": "string", "text_semantic": "arbitrary"},
        {"type": "string", "text_semantic": "negative_prompt", "values": ["a"]},
    ):
        with pytest.raises(ValueError):
            _validate_provider_spec(spec)


def test_native_string_reaches_generate_request_once_without_a_paid_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = enrich_capabilities(
        _parse_capability(next(row for row in RAW if row["id"] == "alibaba/wan-2.6"))
    )
    witness = request_witness(model, InferenceMethod.T2V)
    assert witness is not None
    received: list[object] = []

    class ProbeCompleteError(Exception):
        pass

    class Runtime:
        async def effective_catalog(self) -> object:
            return types.SimpleNamespace(models=(model,))

        async def generate(self, request: object, node_id: str | None) -> object:
            received.append(request)
            assert node_id == "creative-test-node"
            raise ProbeCompleteError

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(
        OpenRouterVideoGenerate,
        "hidden",
        types.SimpleNamespace(unique_id="creative-test-node"),
        raising=False,
    )
    with pytest.raises(ProbeCompleteError):
        asyncio.run(
            cast(Any, OpenRouterVideoGenerate.execute)(
                model=model.model_id,
                prompt=witness.prompt or "TEST ONLY",
                inference_method="T2V",
                duration=witness.duration or 0,
                resolution=witness.resolution or "",
                aspect_ratio=witness.aspect_ratio or "",
                geometry_authority="NORMALIZED",
                **{"provider_option:atlas-cloud::negative_prompt": "linked\ntext"},
            )
        )
    assert len(received) == 1
    request = cast(Any, received[0])
    assert request.provider_options == (
        ProviderOption("atlas-cloud", "negative_prompt", "linked\ntext"),
    )
