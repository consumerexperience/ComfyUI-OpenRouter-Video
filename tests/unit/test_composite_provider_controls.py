"""Reviewed composite controls: real Core validation and exact wire, no submission."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.capabilities import RequestValidator, request_witness
from openrouter_video.client import _parse_capability
from openrouter_video.configuration import project_semantic_values
from openrouter_video.errors import ProductFailureError
from openrouter_video.evidence_registry import enrich_capabilities
from openrouter_video.models import (
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ProviderOption,
)

RAW = json.loads(
    (Path(__file__).parents[1] / "fixtures/op07-full-catalogue.json").read_text(encoding="utf8")
)["data"]


def checked(mid: str, method: InferenceMethod, *options: ProviderOption) -> dict[str, Any]:
    model = enrich_capabilities(_parse_capability(next(row for row in RAW if row["id"] == mid)))
    base = request_witness(model, method)
    assert base is not None
    request = replace(base, provider_options=base.provider_options + options)
    RequestValidator().validate_capabilities(request, model)
    return request.to_openrouter_payload()


def heygen(key: str, value: str | bool | int | float, *path: str) -> ProviderOption:
    return ProviderOption("heygen", key, value, path=path)


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("color", "value", "#123456"),
        ("image", "url", "https://example.test/bg.png"),
        ("image", "asset_id", "TEST_ONLY_ASSET"),
    ],
)
def test_avatar_background_variants_exact_wire(kind: str, field: str, value: str) -> None:
    wire = checked(
        "heygen/avatar-iv",
        InferenceMethod.IR2V,
        heygen("background", kind, "type"),
        heygen("background", value, field),
    )
    assert wire["provider"]["options"]["heygen"]["background"] == {"type": kind, field: value}


@pytest.mark.parametrize(
    "options",
    [
        (heygen("background", "color", "type"),),
        (heygen("background", "image", "type"),),
        (
            heygen("background", "image", "type"),
            heygen("background", "url", "url"),
            heygen("background", "asset", "asset_id"),
        ),
        (heygen("background", "color", "type"), heygen("background", "", "value")),
        (
            heygen("voice_settings", "starfish", "engine_settings", "engine_type"),
            heygen("voice_settings", 0.5, "engine_settings", "stability"),
        ),
        (
            heygen("voice_settings", "fish", "engine_settings", "engine_type"),
            heygen("voice_settings", "eleven_v3", "engine_settings", "model"),
        ),
        (heygen("voice_settings", 0.5, "engine_settings", "stability"),),
        (heygen("caption", "vtt", "file_format"),),
    ],
)
def test_avatar_invalid_composite_combinations_fail_before_submit(
    options: tuple[ProviderOption, ...],
) -> None:
    with pytest.raises(ProductFailureError):
        checked("heygen/avatar-iv", InferenceMethod.IR2V, *options)


@pytest.mark.parametrize(
    "name,value,valid",
    [
        ("speed", 0.5, True),
        ("speed", 1.5, True),
        ("speed", 0.49, False),
        ("speed", 1.51, False),
        ("pitch", -50, True),
        ("pitch", 50, True),
        ("pitch", -51, False),
        ("pitch", 51, False),
        ("volume", 0, True),
        ("volume", 1, True),
        ("volume", -0.01, False),
        ("volume", 1.01, False),
    ],
)
def test_avatar_voice_documented_inclusive_domains(name: str, value: float, valid: bool) -> None:
    if valid:
        wire = checked(
            "heygen/avatar-iv", InferenceMethod.IR2V, heygen("voice_settings", value, name)
        )
        assert wire["provider"]["options"]["heygen"]["voice_settings"][name] == value
    else:
        with pytest.raises(ProductFailureError):
            checked("heygen/avatar-iv", InferenceMethod.IR2V, heygen("voice_settings", value, name))


@pytest.mark.parametrize(
    "engine,models",
    [
        (
            "elevenlabs",
            [
                "eleven_multilingual_v2",
                "eleven_turbo_v2_5",
                "eleven_flash_v2_5",
                "eleven_v3",
                "eleven_v4",
            ],
        ),
        ("fish", ["s1", "s2-pro", "s2.1-pro"]),
        ("starfish", []),
        ("heygen_voice", []),
        ("orca", []),
    ],
)
def test_avatar_all_documented_voice_engine_variants(engine: str, models: list[str]) -> None:
    versions: list[str | None] = list(models) if models else [None]
    for version in versions:
        options = [heygen("voice_settings", engine, "engine_settings", "engine_type")]
        if version:
            options.append(heygen("voice_settings", version, "engine_settings", "model"))
        checked("heygen/avatar-iv", InferenceMethod.IR2V, *options)


def keyframe(index: int, field: str, value: str | int | float, *nested: str) -> ProviderOption:
    return ProviderOption("runway", "keyframes", value, path=(index, field, *nested))


@pytest.mark.parametrize("count", range(1, 6))
def test_aleph_full_keyframe_count_domain_and_ordered_wire(count: int) -> None:
    options = tuple(
        option
        for index in range(count)
        for option in (
            keyframe(index, "uri", f"https://example.test/{index}.png"),
            keyframe(index, "seconds", index * 5),
        )
    )
    wire = checked("runway/aleph-2", InferenceMethod.V2V_EDIT, *options)
    assert wire["provider"]["options"]["runway"]["keyframes"] == [
        {"uri": f"https://example.test/{index}.png", "seconds": index * 5} for index in range(count)
    ]


@pytest.mark.parametrize(
    "extra",
    [
        (keyframe(0, "at", 0.5),),
        (keyframe(0, "range", 5, "start_seconds"),),
        (keyframe(0, "range", 5, "start_seconds"), keyframe(0, "range", 5, "end_seconds")),
        (
            keyframe(0, "range", 0, "start_seconds"),
            keyframe(0, "range", 5, "end_seconds"),
            keyframe(1, "uri", "https://example.test/1.png"),
            keyframe(1, "at", 1),
        ),
    ],
)
def test_aleph_invalid_time_and_range_relations_fail(extra: tuple[ProviderOption, ...]) -> None:
    with pytest.raises(ProductFailureError):
        checked(
            "runway/aleph-2",
            InferenceMethod.V2V_EDIT,
            keyframe(0, "uri", "https://example.test/0.png"),
            keyframe(0, "seconds", 0),
            *extra,
        )


@pytest.mark.parametrize("method", [InferenceMethod.T2V, InferenceMethod.I2V])
@pytest.mark.parametrize("shot", ["single", "multi"])
def test_wan26_shot_type_requires_effective_expansion(method: InferenceMethod, shot: str) -> None:
    checked("alibaba/wan-2.6", method, ProviderOption("atlas-cloud", "shot_type", shot))
    checked(
        "alibaba/wan-2.6",
        method,
        ProviderOption("atlas-cloud", "shot_type", shot),
        ProviderOption("atlas-cloud", "enable_prompt_expansion", True),
    )
    with pytest.raises(ProductFailureError):
        checked(
            "alibaba/wan-2.6",
            method,
            ProviderOption("atlas-cloud", "shot_type", shot),
            ProviderOption("atlas-cloud", "enable_prompt_expansion", False),
        )


@pytest.mark.parametrize(
    "mid,method",
    [
        ("alibaba/wan-2.6", InferenceMethod.T2V),
        ("alibaba/wan-2.6", InferenceMethod.I2V),
        ("alibaba/wan-2.7", InferenceMethod.T2V),
        ("alibaba/wan-2.7", InferenceMethod.I2V),
        ("alibaba/wan-2.7", InferenceMethod.FLF2V),
    ],
)
def test_wan_audio_and_negative_prompt_exact_provider_wire(
    mid: str, method: InferenceMethod
) -> None:
    wire = checked(
        mid,
        method,
        ProviderOption("atlas-cloud", "audio", "https://example.test/voice.wav"),
        ProviderOption("atlas-cloud", "negative_prompt", "blur"),
    )
    assert wire["provider"]["options"]["atlas-cloud"] == {
        "audio": "https://example.test/voice.wav",
        "negative_prompt": "blur",
    }
    if mid.endswith("2.7"):
        checked(
            mid,
            method,
            ProviderOption("atlas-cloud", "negative_prompt", "x" * 500),
            ProviderOption("atlas-cloud", "prompt_extend", False),
        )
        with pytest.raises(ProductFailureError):
            checked(mid, method, ProviderOption("atlas-cloud", "negative_prompt", "x" * 501))


@pytest.mark.parametrize(
    "method", [InferenceMethod.T2V, InferenceMethod.I2V, InferenceMethod.FLF2V]
)
def test_flux_draft_omits_unproven_geometry_mapping_and_preserves_optional_version(
    method: InferenceMethod,
) -> None:
    model = enrich_capabilities(
        _parse_capability(next(row for row in RAW if row["id"] == "black-forest-labs/flux-3-video"))
    )
    base = request_witness(model, method)
    assert base is not None
    options = (
        ProviderOption("black-forest-labs", "draft", True),
        ProviderOption("black-forest-labs", "version", "latest"),
    )
    values = project_semantic_values(
        model,
        method.value,
        {"prompt": base.prompt, "resolution": "1080p", "size": None, "provider_options": options},
    )
    assert values["resolution"] is values["size"] is None
    request = replace(base, resolution=None, size=None, provider_options=options)
    RequestValidator().validate_capabilities(request, model)
    wire = request.to_openrouter_payload()
    assert "resolution" not in wire and "size" not in wire
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(replace(request, resolution="1080p"), model)
    with pytest.raises(ProductFailureError):
        checked(
            model.model_id,
            method,
            ProviderOption("black-forest-labs", "version", "invented-version"),
        )


@pytest.mark.parametrize("count", range(1, 6))
def test_wan27_reference_image_methods_cover_full_five_subject_domain(count: int) -> None:
    model = enrich_capabilities(
        _parse_capability(next(row for row in RAW if row["id"] == "alibaba/wan-2.7"))
    )
    method = InferenceMethod.IR2V if count == 1 else InferenceMethod.MI2V
    base = request_witness(model, method)
    assert base is not None
    references = InputReferenceCollection(
        tuple(
            InputReference(InputReferenceKind.IMAGE, f"https://example.test/subject{index}.png")
            for index in range(count)
        )
    )
    request = replace(base, input_references=references)
    RequestValidator().validate_capabilities(request, model)
    wire = request.to_openrouter_payload()
    assert len(wire["input_references"]) == count  # type: ignore[arg-type]
    assert "frame_images" not in wire and "provider" not in wire
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(request, input_references=InputReferenceCollection(references.references * 6)),
            model,
        )


@pytest.mark.parametrize(
    "size",
    [
        "1280*720",
        "720*1280",
        "960*960",
        "1088*832",
        "832*1088",
        "1920*1080",
        "1080*1920",
        "1440*1440",
        "1632*1248",
        "1248*1632",
    ],
)
def test_wan26_passthrough_full_native_size_domain_without_competing_geometry(size: str) -> None:
    model = enrich_capabilities(
        _parse_capability(next(row for row in RAW if row["id"] == "alibaba/wan-2.6"))
    )
    base = request_witness(model, InferenceMethod.T2V)
    assert base is not None
    options = (ProviderOption("atlas-cloud", "size", size),)
    projected = project_semantic_values(
        model,
        "T2V",
        {
            "prompt": base.prompt,
            "resolution": "1080p",
            "aspect_ratio": "16:9",
            "size": None,
            "provider_options": options,
        },
    )
    assert projected["resolution"] is projected["aspect_ratio"] is projected["size"] is None
    request = replace(base, resolution=None, aspect_ratio=None, size=None, provider_options=options)
    RequestValidator().validate_capabilities(request, model)
    wire = request.to_openrouter_payload()
    assert not {"resolution", "aspect_ratio", "size"} & wire.keys()
    assert wire["provider"] == {"options": {"atlas-cloud": {"size": size}}}


def test_avatar_supplied_audio_is_a_separate_typed_path_without_script_or_tts() -> None:
    model = enrich_capabilities(
        _parse_capability(next(row for row in RAW if row["id"] == "heygen/avatar-iv"))
    )
    request = request_witness(model, InferenceMethod.AVATAR_AUDIO)
    assert request is not None and request.prompt is None and request.input_references is not None
    assert [r.kind for r in request.input_references.references] == [
        InputReferenceKind.IMAGE,
        InputReferenceKind.AUDIO,
    ]
    wire = request.to_openrouter_payload()
    assert "prompt" not in wire and "provider" not in wire
    references = wire["input_references"]
    assert isinstance(references, list)
    assert [item["type"] for item in references] == ["image_url", "audio_url"]
    for options in [
        (heygen("voice_id", "TEST_ONLY_VOICE"),),
        (heygen("voice_settings", 1, "speed"),),
    ]:
        with pytest.raises(ProductFailureError):
            RequestValidator().validate_capabilities(
                replace(request, provider_options=options), model
            )
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(request, prompt="conflicting script"), model
        )
    with pytest.raises(ProductFailureError):
        RequestValidator().validate_capabilities(
            replace(
                request,
                input_references=InputReferenceCollection(request.input_references.references[:1]),
            ),
            model,
        )
