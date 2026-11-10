from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from openrouter_video.models import (
    GenerationRequest,
    ProviderOption,
    request_fingerprint_v3,
    request_fingerprint_v4,
)

PREVIOUS_JOB = "gen-vid-1789493115-a1B2c3D4e5F6g7H8i9J0"


def test_extended_fields_serialize_only_when_present() -> None:
    legacy = GenerationRequest("vendor/model", "prompt")
    assert legacy.to_openrouter_payload() == {
        "model": "vendor/model",
        "prompt": "prompt",
        "generate_audio": False,
    }

    request = GenerationRequest(
        "vendor/model",
        "prompt",
        previous_job_id=PREVIOUS_JOB,
        upscale_factor=2,
        creativity=1,
        provider_options=(
            ProviderOption("google", "motion_strength", 0.5),
            ProviderOption("google", "style", "cinematic"),
            ProviderOption("kwaivgi", "audio", True),
            ProviderOption("google", "seed", 7, container="parameters"),
        ),
    )
    payload = request.to_openrouter_payload()
    assert payload["previous_job_id"] == PREVIOUS_JOB
    assert payload["upscale_factor"] == 2
    assert payload["creativity"] == 1
    assert payload["provider"] == {
        "options": {
            "google": {
                "motion_strength": 0.5,
                "style": "cinematic",
                "parameters": {"seed": 7},
            },
            "kwaivgi": {"audio": True},
        }
    }
    assert "inference_method" not in payload
    assert "source_video" not in payload


@pytest.mark.parametrize(
    "kwargs",
    [
        {"previous_job_id": "job-123"},
        {"upscale_factor": 0},
        {"upscale_factor": float("nan")},
        {"upscale_factor": True},
        {"creativity": True},
        {"provider_options": [ProviderOption("google", "style", "private")]},
        {
            "provider_options": (
                ProviderOption("google", "style", "first"),
                ProviderOption("google", "style", "second"),
            )
        },
        {
            "provider_options": (
                ProviderOption("google", "parameters", "direct"),
                ProviderOption("google", "seed", 1, container="parameters"),
            )
        },
    ],
)
def test_invalid_extension_shapes_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        GenerationRequest("vendor/model", "prompt", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "provider,key,value",
    [
        ("Google", "style", "x"),
        ("google/path", "style", "x"),
        ("google", "bad key", "x"),
        ("google", "style", {"nested": "not allowed"}),
        ("google", "style", float("inf")),
    ],
)
def test_provider_options_reject_unbounded_or_malformed_values(
    provider: str, key: str, value: object
) -> None:
    with pytest.raises(ValueError):
        ProviderOption(provider, key, value)  # type: ignore[arg-type]


def test_provider_option_rejects_unreviewed_container() -> None:
    with pytest.raises(ValueError):
        ProviderOption("google", "seed", 1, container="arbitrary")


def test_provider_option_is_frozen_and_repr_hides_string_value() -> None:
    option = ProviderOption("google", "token_like_value", "sensitive-option-value")
    request = GenerationRequest("vendor/model", "prompt", provider_options=(option,))
    assert "sensitive-option-value" not in repr(option)
    assert "sensitive-option-value" not in repr(request)
    with pytest.raises(FrozenInstanceError):
        option.value = "changed"  # type: ignore[misc]


def test_v4_preserves_legacy_fingerprint_and_binds_extensions_safely() -> None:
    legacy = GenerationRequest("vendor/model", "private prompt")
    assert request_fingerprint_v4(legacy) == request_fingerprint_v3(legacy)

    request = GenerationRequest(
        "vendor/model",
        "private prompt",
        previous_job_id=PREVIOUS_JOB,
        provider_options=(ProviderOption("google", "style", "private provider string"),),
    )
    fingerprint = request_fingerprint_v4(request)
    assert fingerprint.startswith("v4:")
    assert PREVIOUS_JOB not in fingerprint
    assert "private provider string" not in fingerprint
    assert request_fingerprint_v4(
        GenerationRequest(
            "vendor/model",
            "private prompt",
            previous_job_id=PREVIOUS_JOB,
            provider_options=(ProviderOption("google", "style", "different private string"),),
        )
    ) == fingerprint
    assert request_fingerprint_v4(
        GenerationRequest(
            "vendor/model",
            "private prompt",
            previous_job_id="gen-vid-1789493115-z1Y2x3W4v5U6t7S8r9Q0",
        )
    ) != fingerprint

    for change in (
        {"upscale_factor": 2},
        {"creativity": 1},
        {"provider_options": (ProviderOption("google", "style", True),)},
    ):
        assert request_fingerprint_v4(GenerationRequest("vendor/model", "p", **change)) != (
            request_fingerprint_v4(GenerationRequest("vendor/model", "p"))
        )
