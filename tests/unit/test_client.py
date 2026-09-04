from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from openrouter_video.client import OpenRouterVideoClient
from openrouter_video.errors import MalformedOpenRouterResponseError, OpenRouterHTTPError
from openrouter_video.models import FrameReference, FrameType, GenerationRequest
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport
from tests.fixtures.identity import TEST_APP_IDENTITY


class StaticSecretProvider:
    def get_openrouter_api_key(self) -> str:
        return "TEST_ONLY_KEY"


def _policy() -> OpenRouterRequestPolicy:
    return OpenRouterRequestPolicy(
        identity=TEST_APP_IDENTITY,
        secret_provider=StaticSecretProvider(),
    )


def test_client_maps_exact_endpoints_and_tolerates_additive_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "vendor/model",
                            "canonical_slug": "vendor/model",
                            "supported_durations": [5, 8],
                            "supported_frame_images": ["first_frame", "future_frame"],
                            "generate_audio": True,
                            "future_additive_field": {"ignored": True},
                        }
                    ],
                    "future_envelope_field": True,
                },
                request=request,
            )
        if request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "id": "job-1",
                    "status": "pending",
                    "polling_url": "https://evil.example/steal",
                },
                request=request,
            )
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=b"video", request=request)
        return httpx.Response(
            200,
            json={
                "id": "job-1",
                "status": "completed",
                "polling_url": "https://evil.example/steal",
                "unsigned_urls": ["https://evil.example/steal.mp4"],
                "usage": {"cost": "0.125"},
            },
            request=request,
        )

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            models = await client.list_video_models()
            assert models[0].supported_frame_types == frozenset({FrameType.FIRST})
            request = GenerationRequest(
                model="vendor/model",
                prompt="private prompt",
                duration=5,
                first_frame=FrameReference(FrameType.FIRST, "https://assets.example/frame.png"),
            )
            submitted = await client.submit_video(request)
            assert submitted.job_id == "job-1"
            observed = await client.get_job("job-1")
            assert observed.usage.actual_cost_usd == Decimal("0.125")
            async with client.stream_content("job-1") as response:
                assert await response.aread() == b"video"

    asyncio.run(scenario())
    assert [request.method for request in requests] == ["GET", "POST", "GET", "GET"]
    assert [request.url.raw_path.decode() for request in requests] == [
        "/api/v1/videos/models",
        "/api/v1/videos",
        "/api/v1/videos/job-1",
        "/api/v1/videos/job-1/content?index=0",
    ]
    submitted_body = json.loads(requests[1].content)
    assert submitted_body == {
        "model": "vendor/model",
        "prompt": "private prompt",
        "duration": 5,
        "generate_audio": False,
        "frame_images": [{"frame_type": "first_frame", "url": "https://assets.example/frame.png"}],
    }
    assert all(request.url.host == "openrouter.ai" for request in requests)


def test_client_rejects_malformed_successful_submit_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"status": "pending"}, request=request)

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            with pytest.raises(MalformedOpenRouterResponseError):
                await client.submit_video(GenerationRequest("vendor/model", "prompt"))

    asyncio.run(scenario())


def test_client_exposes_status_without_response_body() -> None:
    canary = "PRIVATE_RESPONSE_BODY_CANARY"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text=canary, request=request)

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            with pytest.raises(OpenRouterHTTPError) as caught:
                await client.submit_video(GenerationRequest("vendor/model", "prompt"))
            assert caught.value.status_code == 402
            assert canary not in str(caught.value)
            assert canary not in repr(caught.value)

    asyncio.run(scenario())


def test_client_exposes_only_bounded_numeric_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"}, request=request)

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            with pytest.raises(OpenRouterHTTPError) as caught:
                await client.list_video_models()
            assert caught.value.retry_after_seconds == 12.0

    asyncio.run(scenario())


def test_client_preserves_exact_numeric_usage_cost() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                b'{"id":"job-1","status":"completed","usage":'
                b'{"cost":0.1234567890123456789012345678}}'
            ),
            headers={"Content-Type": "application/json"},
            request=request,
        )

    async def scenario() -> None:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(request_policy=_policy(), transport=transport)
            snapshot = await client.get_job("job-1")
            assert snapshot.usage.actual_cost_usd == Decimal("0.1234567890123456789012345678")

    asyncio.run(scenario())


def test_client_constructor_and_methods_have_no_policy_escape_hatches() -> None:
    import inspect

    forbidden = {"headers", "base_url", "api_key", "referer", "title", "categories"}
    for method in (
        OpenRouterVideoClient.__init__,
        OpenRouterVideoClient.list_video_models,
        OpenRouterVideoClient.submit_video,
        OpenRouterVideoClient.get_job,
        OpenRouterVideoClient.stream_content,
    ):
        assert forbidden.isdisjoint(inspect.signature(method).parameters)
