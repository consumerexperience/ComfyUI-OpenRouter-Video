from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from openrouter_video.application import GenerateService
from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.client import OpenRouterVideoClient
from openrouter_video.media import DownloadService
from openrouter_video.models import FrameReference, FrameType, GenerationRequest, GenerationResult
from openrouter_video.persistence import JobStore
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport
from tests.fixtures.identity import TEST_APP_IDENTITY

API_KEY_CANARY = "PHASE5_API_KEY_CANARY"
PROMPT_CANARY = "PHASE5_PRIVATE_PROMPT_CANARY"
FIRST_URL_CANARY = "https://assets.example/PHASE5_FIRST_FRAME_CANARY.png"
LAST_URL_CANARY = "https://assets.example/PHASE5_LAST_FRAME_CANARY.png"
REQUEST_BODY_CANARY = "PHASE5_REQUEST_BODY_CANARY"
RESPONSE_BODY_CANARY = "PHASE5_RESPONSE_BODY_CANARY"
OPERATION_ID = "phase5-operation-id"
NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


class CanarySecretProvider:
    def get_openrouter_api_key(self) -> str:
        return API_KEY_CANARY


async def _no_sleep(_: float) -> None:
    return None


def test_sensitive_generation_data_never_persists_or_leaks_to_diagnostics(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
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
                            "supported_frame_images": ["first_frame", "last_frame"],
                            "catalog_additive": RESPONSE_BODY_CANARY,
                        }
                    ]
                },
                request=request,
            )
        if request.method == "POST":
            assert PROMPT_CANARY.encode() in request.content
            assert FIRST_URL_CANARY.encode() in request.content
            assert LAST_URL_CANARY.encode() in request.content
            return httpx.Response(
                202,
                json={
                    "id": "job-1",
                    "status": "pending",
                    "ignored_echo": REQUEST_BODY_CANARY,
                },
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "id": "job-1",
                "status": "failed",
                "error": RESPONSE_BODY_CANARY,
            },
            request=request,
        )

    async def scenario() -> GenerationResult:
        async with HttpxTransport.for_test(httpx.MockTransport(handler)) as transport:
            client = OpenRouterVideoClient(
                request_policy=OpenRouterRequestPolicy(
                    identity=TEST_APP_IDENTITY,
                    secret_provider=CanarySecretProvider(),
                ),
                transport=transport,
            )
            store = JobStore(tmp_path / "state" / "jobs.sqlite3")
            capabilities = CapabilityService(
                client=client,
                store=store,
                sleep=_no_sleep,
                now=lambda: NOW,
                jitter=lambda value: value,
            )
            service = GenerateService(
                capabilities=capabilities,
                validator=RequestValidator(),
                store=store,
                submit_client=client,
                observation_client=client,
                downloader=DownloadService(
                    client=client,
                    output_root=tmp_path / "output",
                    sleep=_no_sleep,
                ),
                sleep=_no_sleep,
                now=lambda: NOW,
                monotonic=lambda: 0.0,
            )
            request = GenerationRequest(
                "vendor/model",
                PROMPT_CANARY,
                first_frame=FrameReference(FrameType.FIRST, FIRST_URL_CANARY),
                last_frame=FrameReference(FrameType.LAST, LAST_URL_CANARY),
            )
            return await service.generate(OPERATION_ID, request)

    result = asyncio.run(scenario())
    assert result.error is not None
    assert RESPONSE_BODY_CANARY not in repr(result)
    assert REQUEST_BODY_CANARY not in repr(result)
    assert PROMPT_CANARY not in repr(result)
    assert caplog.text == ""
    assert sum(request.method == "POST" for request in requests) == 1
    submitted = next(request for request in requests if request.method == "POST")
    assert submitted.headers["Authorization"] == f"Bearer {API_KEY_CANARY}"
    assert OPERATION_ID.encode() not in submitted.content
    assert b"request_fingerprint" not in submitted.content

    forbidden = (
        API_KEY_CANARY,
        f"Bearer {API_KEY_CANARY}",
        PROMPT_CANARY,
        FIRST_URL_CANARY,
        LAST_URL_CANARY,
        REQUEST_BODY_CANARY,
        RESPONSE_BODY_CANARY,
    )
    persisted = b"".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    for canary in forbidden:
        assert canary.encode() not in persisted
