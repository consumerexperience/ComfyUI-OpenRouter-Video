"""Observable HTTPX transport security and lifetime contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any, cast

import httpx
import pytest

from openrouter_video.errors import RequestPolicyError, TransportError
from openrouter_video.policy import Operation
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport
from tests.fixtures.identity import TEST_APP_IDENTITY

CANARY = "TEST_ONLY_OPENROUTER_KEY_CANARY"


class StaticSecretProvider:
    def get_openrouter_api_key(self) -> str:
        return CANARY


def _request_policy() -> OpenRouterRequestPolicy:
    return OpenRouterRequestPolicy(
        identity=TEST_APP_IDENTITY,
        secret_provider=StaticSecretProvider(),
    )


@pytest.mark.parametrize("status", [302, 307, 308])
def test_redirect_is_returned_without_following_or_external_leakage(status: int) -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            status,
            headers={"Location": "https://evil.example/video"},
            request=request,
        )

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            response = await transport.send(_request_policy().prepare(Operation.DISCOVERY))
            assert response.status_code == status

    asyncio.run(scenario())
    assert len(observed) == 1
    assert observed[0].url.host == "openrouter.ai"
    assert observed[0].headers["Authorization"] == f"Bearer {CANARY}"
    assert observed[0].headers["HTTP-Referer"] == TEST_APP_IDENTITY.referer


def test_defensive_revalidation_rejects_forged_external_destination() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    prepared = _request_policy().prepare(Operation.DISCOVERY)
    forged = replace(prepared, url=httpx.URL("https://evil.example/api/v1/videos/models"))

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            with pytest.raises(RequestPolicyError, match="outside canonical policy"):
                await transport.send(forged)

    asyncio.run(scenario())
    assert calls == 0


def test_defensive_revalidation_rejects_duplicate_security_header() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    prepared = _request_policy().prepare(Operation.DISCOVERY)
    forged = replace(
        prepared,
        _headers=prepared._headers + (("Authorization", "Bearer alternate"),),
    )

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            with pytest.raises(RequestPolicyError, match="headers violate"):
                await transport.send(forged)

    asyncio.run(scenario())
    assert calls == 0


def test_defensive_revalidation_rejects_wrong_canonical_path() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, request=request)

    prepared = _request_policy().prepare(Operation.DISCOVERY)
    forged = replace(prepared, url=httpx.URL("https://openrouter.ai/api/v1/keys"))

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            with pytest.raises(RequestPolicyError, match="path violates"):
                await transport.send(forged)

    asyncio.run(scenario())
    assert calls == 0


def test_transport_attempts_a_connection_failure_once_and_redacts_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError(f"synthetic failure {CANARY}", request=request)

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            with pytest.raises(TransportError) as caught:
                await transport.send(_request_policy().prepare(Operation.SUBMIT, json_body={}))
            assert str(caught.value) == "OpenRouter transport failed"
            assert CANARY not in repr(caught.value)
            assert caught.value.__cause__ is None

    asyncio.run(scenario())
    assert calls == 1


def test_operation_timeout_reaches_httpx_request() -> None:
    observed_timeout: dict[str, float] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        timeout = request.extensions["timeout"]
        assert isinstance(timeout, dict)
        observed_timeout.update(timeout)
        return httpx.Response(200, request=request)

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            await transport.send(_request_policy().prepare(Operation.SUBMIT, json_body={}))

    asyncio.run(scenario())
    assert observed_timeout == {"connect": 10.0, "read": 60.0, "write": 30.0, "pool": 10.0}


def test_streaming_transport_uses_one_canonical_request_and_closes_response() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, content=b"streamed", request=request)

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            prepared = _request_policy().prepare(Operation.CONTENT, job_id="job-1")
            async with transport.stream(prepared) as response:
                assert await response.aread() == b"streamed"
            assert response.is_closed

    asyncio.run(scenario())
    assert len(observed) == 1
    assert observed[0].url.raw_path == b"/api/v1/videos/job-1/content?index=0"


def test_production_factory_sets_explicit_safe_httpx_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_transport: dict[str, Any] = {}
    captured_client: dict[str, Any] = {}
    mock_transport = httpx.MockTransport(lambda request: httpx.Response(200, request=request))
    real_async_client = httpx.AsyncClient

    def fake_transport(**kwargs: Any) -> httpx.AsyncBaseTransport:
        captured_transport.update(kwargs)
        return mock_transport

    def fake_client(**kwargs: Any) -> httpx.AsyncClient:
        captured_client.update(kwargs)
        return real_async_client(**kwargs)

    monkeypatch.setattr("openrouter_video.transport.httpx.AsyncHTTPTransport", fake_transport)
    monkeypatch.setattr("openrouter_video.transport.httpx.AsyncClient", fake_client)

    async def scenario() -> None:
        transport = HttpxTransport.create()
        await transport.aclose()

    asyncio.run(scenario())
    assert captured_transport["verify"] is True
    assert captured_transport["trust_env"] is False
    assert captured_transport["retries"] == 0
    limits = captured_transport["limits"]
    assert isinstance(limits, httpx.Limits)
    assert limits.max_connections == 10
    assert limits.max_keepalive_connections == 5
    assert captured_client["follow_redirects"] is False
    assert captured_client["trust_env"] is False
    assert "base_url" not in captured_client


def test_transport_surface_does_not_accept_arbitrary_request_parts() -> None:
    send_parameters = tuple(__import__("inspect").signature(HttpxTransport.send).parameters)
    assert send_parameters == ("self", "request")
    assert not any(
        name in send_parameters for name in ("url", "base_url", "headers", "api_key", "referer")
    )
    with pytest.raises(TypeError, match="create.*for_test"):
        HttpxTransport(cast(httpx.AsyncClient, object()), _capability=object())
