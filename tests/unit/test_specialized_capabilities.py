from dataclasses import replace
from typing import Any, cast

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.configuration import REQUEST_SHAPES_KEY
from openrouter_video.errors import ProductFailureError
from openrouter_video.models import (
    CapabilityFact,
    CapabilityFactState,
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCapabilities,
    InputReferenceCollection,
    InputReferenceKind,
    ModelCapabilities,
    ProviderOption,
)


def _method(topology: dict[str, Any], controls: dict[str, Any]) -> dict[str, Any]:
    return {"state": "SUPPORTED", "topology": topology, "controls": controls}


def _profile() -> ModelCapabilities:
    upscale_topology = {
        "fixed": ["source_video"],
        "reference_kinds": [],
        "kind_sets": [[]],
        "min": 0,
        "max": 0,
        "per_kind_max": {},
    }
    avatar_topology = {
        "fixed": [],
        "reference_kinds": ["image", "audio"],
        "kind_sets": [["image", "audio"]],
        "min": 2,
        "max": 2,
        "per_kind_max": {"image": 1, "audio": 1},
    }
    methods = {
        InferenceMethod.V2V_UPSCALE.value: _method(
            upscale_topology,
            {
                "prompt": {"state": "SUPPORTED", "required": False},
                "upscale_factor": {"state": "SUPPORTED", "required": True},
                "creativity": {"state": "SUPPORTED", "values": [0, 1]},
                "seed": {"state": "SUPPORTED", "integer_range": {"min": 4, "max": 9}},
            },
        ),
        InferenceMethod.AVATAR_AUDIO.value: _method(
            avatar_topology,
            {"prompt": {"state": "SUPPORTED", "required": False}},
        ),
    }
    shapes = {"schema_version": 1, "methods": methods}
    facts = (
        CapabilityFact(
            "vendor/model",
            REQUEST_SHAPES_KEY,
            shapes,
            CapabilityFactState.SUPPORTED,
            "reviewed",
            "synthetic",
            "2026-11-09T00:00:00Z",
            "unit",
            "test",
        ),
        CapabilityFact(
            "vendor/model",
            "upscale_factor",
            {"type": "number", "min": 1.5, "max": 3},
            CapabilityFactState.SUPPORTED,
            "LIVE_STRUCTURED_API",
            "synthetic",
            "2026-11-09T00:00:00Z",
            "test",
            "live",
        ),
        CapabilityFact(
            "vendor/model",
            "creativity",
            {"type": "number", "min": 0, "max": 1},
            CapabilityFactState.SUPPORTED,
            "LIVE_STRUCTURED_API",
            "synthetic",
            "2026-11-09T00:00:00Z",
            "test",
            "live",
        ),
        CapabilityFact(
            "vendor/model",
            "allowed_passthrough_parameters",
            ["temperature"],
            CapabilityFactState.SUPPORTED,
            "LIVE_STRUCTURED_API",
            "synthetic",
            "2026-11-09T00:00:00Z",
            "test",
            "live",
        ),
    )
    return ModelCapabilities(
        "vendor/model",
        supports_seed=True,
        input_reference_capabilities=InputReferenceCapabilities(
            reference_kinds=frozenset(InputReferenceKind),
            max_reference_count=2,
            mixed_reference_kinds=True,
        ),
        evidence_facts=facts,
    )


def test_video_upscale_validates_fields_and_serializes_without_prompt() -> None:
    model = _profile()
    request = GenerationRequest(
        model.model_id,
        None,
        InferenceMethod.V2V_UPSCALE,
        generate_audio=None,
        source_video=InputReference(InputReferenceKind.VIDEO, "https://example.com/source.mp4"),
        upscale_factor=2.5,
        creativity=1,
    )
    validator = RequestValidator()
    validator.validate_shape(request)
    validator.validate_capabilities(request, model)
    assert request.to_openrouter_payload() == {
        "model": model.model_id,
        "upscale_factor": 2.5,
        "creativity": 1,
        "input_references": [
            {"type": "video_url", "video_url": {"url": "https://example.com/source.mp4"}}
        ],
    }
    for bad in (float("nan"), float("inf"), True, -1, 1.4, 3.1):
        with pytest.raises((ValueError, ProductFailureError)):
            invalid = replace(request, upscale_factor=bad)
            validator.validate_shape(invalid)
            validator.validate_capabilities(invalid, model)
    for bad_creativity in (True, 1.0):
        with pytest.raises(ValueError):
            replace(request, creativity=cast(Any, bad_creativity))
    for bad_creativity in (-1, 2):
        with pytest.raises(ProductFailureError):
            validator.validate_capabilities(
                replace(request, creativity=cast(Any, bad_creativity)), model
            )
    with pytest.raises(ValueError):
        replace(request, previous_job_id="not-a-generation-id")
    required_control_model = model
    shapes = {
        "schema_version": 1,
        "methods": {
            InferenceMethod.V2V_UPSCALE.value: _method(
                {
                    "fixed": ["source_video"],
                    "reference_kinds": [],
                    "kind_sets": [[]],
                    "min": 0,
                    "max": 0,
                    "per_kind_max": {},
                },
                {
                    "prompt": {"state": "SUPPORTED", "required": False},
                    "upscale_factor": {"state": "SUPPORTED", "required": True},
                    "creativity": {"state": "SUPPORTED", "values": [0, 1]},
                },
            )
        },
    }
    facts = tuple(
        replace(fact, value=shapes) if fact.key == REQUEST_SHAPES_KEY else fact
        for fact in model.evidence_facts
    )
    required_control_model = replace(model, evidence_facts=facts)
    with pytest.raises(ProductFailureError):
        validator.validate_capabilities(
            replace(request, upscale_factor=None), required_control_model
        )


def test_avatar_audio_requires_exactly_one_image_and_one_audio_and_allows_prompt() -> None:
    model = _profile()
    refs = InputReferenceCollection(
        (
            InputReference(InputReferenceKind.IMAGE, "https://example.com/avatar.png"),
            InputReference(InputReferenceKind.AUDIO, "https://example.com/voice.wav"),
        )
    )
    request = GenerationRequest(
        model.model_id,
        None,
        InferenceMethod.AVATAR_AUDIO,
        generate_audio=None,
        input_references=refs,
    )
    validator = RequestValidator()
    validator.validate_shape(request)
    validator.validate_capabilities(request, model)
    wire = cast(dict[str, Any], request.to_openrouter_payload())
    assert "prompt" not in wire
    assert [entry["type"] for entry in wire["input_references"]] == ["image_url", "audio_url"]
    with pytest.raises(ProductFailureError):
        validator.validate_shape(
            replace(request, input_references=InputReferenceCollection(refs.references[:1]))
        )


def test_provider_options_need_both_reviewed_schema_and_live_allowlist() -> None:
    model = _profile()
    shapes = {
        "schema_version": 1,
        "methods": {
            InferenceMethod.AVATAR_AUDIO.value: _method(
                {
                    "fixed": [],
                    "reference_kinds": ["image", "audio"],
                    "kind_sets": [["image", "audio"]],
                    "min": 2,
                    "max": 2,
                    "per_kind_max": {"image": 1, "audio": 1},
                },
                {
                    "prompt": {"state": "SUPPORTED", "required": False},
                    "provider_options": {
                        "state": "SUPPORTED",
                        "providers": {
                            "vendor": {"temperature": {"type": "number", "min": 0, "max": 1}}
                        },
                    },
                },
            )
        },
    }
    facts = tuple(
        replace(fact, value=shapes) if fact.key == REQUEST_SHAPES_KEY else fact
        for fact in model.evidence_facts
    )
    model = replace(model, evidence_facts=facts)
    request = GenerationRequest(
        model.model_id,
        None,
        InferenceMethod.AVATAR_AUDIO,
        generate_audio=None,
        input_references=InputReferenceCollection(
            (
                InputReference(InputReferenceKind.IMAGE, "https://example.com/avatar.png"),
                InputReference(InputReferenceKind.AUDIO, "https://example.com/voice.wav"),
            )
        ),
        provider_options=(ProviderOption("vendor", "temperature", 0.5),),
    )
    validator = RequestValidator()
    validator.validate_shape(request)
    validator.validate_capabilities(request, model)
    wire = cast(dict[str, Any], request.to_openrouter_payload())
    assert wire["provider"]["options"] == {"vendor": {"temperature": 0.5}}
    invalid = replace(request, provider_options=(ProviderOption("vendor", "unreviewed", 0.5),))
    with pytest.raises(ProductFailureError):
        validator.validate_capabilities(invalid, model)


def test_witness_finds_upscale_seed_and_avatar_audio_shapes() -> None:
    model = _profile()
    upscale = request_witness(model, InferenceMethod.V2V_UPSCALE)
    avatar = request_witness(model, InferenceMethod.AVATAR_AUDIO)
    assert upscale is not None and upscale.upscale_factor == 1.5 and upscale.creativity == 0
    assert upscale.seed == 4 and upscale.source_video is not None
    assert avatar is not None and avatar.prompt is None
    assert avatar.input_references is not None
    assert {reference.kind for reference in avatar.input_references.references} == {
        InputReferenceKind.IMAGE,
        InputReferenceKind.AUDIO,
    }
