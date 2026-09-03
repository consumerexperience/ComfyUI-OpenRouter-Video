"""Origin, operation, attribution, and request-capability contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from inspect import signature

import httpx
import pytest

import openrouter_video.request_policy as request_policy_module
from openrouter_video.app_identity import AppIdentity
from openrouter_video.errors import RequestPolicyError
from openrouter_video.policy import Operation, TimeoutPolicy
from openrouter_video.request_policy import (
    OpenRouterRequestPolicy,
    _PreparedOpenRouterRequest,
    _validate_canonical_destination,
)
from tests.fixtures.identity import TEST_APP_IDENTITY

CANARY = "TEST_ONLY_OPENROUTER_KEY_CANARY"


class RecordingSecretProvider:
    def __init__(self, value: str = CANARY) -> None:
        self.value = value
        self.calls = 0

    def get_openrouter_api_key(self) -> str:
        self.calls += 1
        return self.value


def _policy(provider: RecordingSecretProvider | None = None) -> OpenRouterRequestPolicy:
    return OpenRouterRequestPolicy(
        identity=TEST_APP_IDENTITY,
        secret_provider=provider or RecordingSecretProvider(),
    )


def _headers(request: _PreparedOpenRouterRequest) -> dict[str, str]:
    return dict(request._headers)


def test_exact_operation_paths_methods_and_headers() -> None:
    cases = (
        (
            _policy().prepare(Operation.DISCOVERY),
            "GET",
            "https://openrouter.ai/api/v1/videos/models",
        ),
        (
            _policy().prepare(Operation.SUBMIT, json_body={"synthetic": True}),
            "POST",
            "https://openrouter.ai/api/v1/videos",
        ),
        (
            _policy().prepare(Operation.POLL, job_id="job/one"),
            "GET",
            "https://openrouter.ai/api/v1/videos/job%2Fone",
        ),
        (
            _policy().prepare(Operation.CONTENT, job_id="job-one"),
            "GET",
            "https://openrouter.ai/api/v1/videos/job-one/content?index=0",
        ),
    )

    for prepared, method, expected_url in cases:
        headers = _headers(prepared)
        assert prepared.method == method
        assert str(prepared.url) == expected_url
        assert headers["Authorization"] == f"Bearer {CANARY}"
        assert headers["HTTP-Referer"] == TEST_APP_IDENTITY.referer
        assert headers["X-OpenRouter-Title"] == "OpenRouter Video for ComfyUI"
        assert headers["X-OpenRouter-Categories"] == "video-gen"
        assert "X-Title" not in headers
        assert headers["Accept"] == (
            "video/*" if prepared.operation is Operation.CONTENT else "application/json"
        )
        assert ("Content-Type" in headers) is (prepared.operation is not Operation.CONTENT)


def test_prepared_request_is_immutable_internal_and_repr_safe() -> None:
    prepared = _policy().prepare(Operation.DISCOVERY)

    with pytest.raises(FrozenInstanceError):
        prepared.method = "POST"  # type: ignore[misc]

    representation = repr(prepared)
    assert CANARY not in representation
    assert "Authorization" not in representation
    assert "_PreparedOpenRouterRequest" in representation

    with pytest.raises(RequestPolicyError):
        _PreparedOpenRouterRequest(
            operation=Operation.DISCOVERY,
            method="GET",
            url=httpx.URL("https://openrouter.ai/api/v1/videos/models"),
            timeout=TimeoutPolicy(10, 10, 30, 10),
            wall_clock_seconds=None,
            _headers=(),
            _body=None,
            _capability=object(),
        )


def test_destination_and_identity_are_validated_before_secret_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = RecordingSecretProvider()
    policy = _policy(provider)

    def reject_destination(destination: str | httpx.URL) -> httpx.URL:
        del destination
        raise RequestPolicyError("synthetic destination rejection")

    monkeypatch.setattr(
        request_policy_module, "_validate_canonical_destination", reject_destination
    )
    with pytest.raises(RequestPolicyError, match="synthetic destination rejection"):
        policy.prepare(Operation.DISCOVERY)
    assert provider.calls == 0


def test_invalid_identity_fails_before_secret_resolution() -> None:
    provider = RecordingSecretProvider()
    policy = OpenRouterRequestPolicy(
        identity=AppIdentity(
            referer="https://user@openrouter.ai/identity",
            title="OpenRouter Video for ComfyUI",
            categories=("video-gen",),
        ),
        secret_provider=provider,
    )

    with pytest.raises(RequestPolicyError, match="Application identity is invalid"):
        policy.prepare(Operation.DISCOVERY)
    assert provider.calls == 0


@pytest.mark.parametrize(
    "destination",
    [
        "http://openrouter.ai/api/v1/videos",
        "https://openrouter.ai:444/api/v1/videos",
        "https://evil.example/api/v1/videos",
        "https://openrouter.ai.evil.example/api/v1/videos",
        "https://evil.example/openrouter.ai/api/v1/videos",
        "https://user@openrouter.ai/api/v1/videos",
        "https://openrouter.ai/api/v1/videos#fragment",
        "https://openrouter.ai.evil.example:443/api/v1/videos",
        "https://[invalid/api/v1/videos",
    ],
)
def test_noncanonical_destinations_are_rejected(destination: str) -> None:
    with pytest.raises(RequestPolicyError):
        _validate_canonical_destination(destination)


@pytest.mark.parametrize(
    "destination",
    [
        "https://openrouter.ai/api/v1/videos",
        "https://openrouter.ai:443/api/v1/videos",
    ],
)
def test_default_and_explicit_https_port_are_canonical(destination: str) -> None:
    assert _validate_canonical_destination(destination).host == "openrouter.ai"


@pytest.mark.parametrize("job_id", [None, "", "   ", "job\nheader"])
def test_invalid_job_identifiers_fail_locally(job_id: str | None) -> None:
    with pytest.raises(RequestPolicyError, match="job identifier"):
        _policy().prepare(Operation.POLL, job_id=job_id)


def test_operation_inputs_cannot_be_used_as_escape_hatches() -> None:
    policy = _policy()
    with pytest.raises(RequestPolicyError, match="does not accept a job identifier"):
        policy.prepare(Operation.DISCOVERY, job_id="unexpected")
    with pytest.raises(RequestPolicyError, match="does not accept a JSON body"):
        policy.prepare(Operation.POLL, job_id="job", json_body={"unexpected": True})
    with pytest.raises(RequestPolicyError, match="requires a JSON body"):
        policy.prepare(Operation.SUBMIT)

    prepare_parameters = tuple(signature(OpenRouterRequestPolicy.prepare).parameters)
    assert prepare_parameters == ("self", "operation", "job_id", "json_body")
    assert not any(
        name in prepare_parameters
        for name in ("method", "url", "base_url", "headers", "api_key", "referer")
    )
