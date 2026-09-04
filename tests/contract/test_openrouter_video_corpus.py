"""Executable assumptions against the reviewed OpenRouter Video contract corpus."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import pytest

from openrouter_video.client import OpenRouterVideoClient
from openrouter_video.errors import MalformedOpenRouterResponseError
from openrouter_video.models import FrameReference, FrameType, GenerationRequest
from openrouter_video.policy import Operation
from openrouter_video.request_policy import OpenRouterRequestPolicy
from openrouter_video.transport import HttpxTransport
from tests.fixtures.identity import EXPECTED_RELEASE_IDENTITY
from tests.harness.scenario import Scenario, ScenarioStep

FIXTURES = Path(__file__).parents[1] / "fixtures" / "openrouter_video"
SYNTHETIC_SECRET = "SYNTHETIC_CONTRACT_KEY"  # noqa: S105 - test-only canary


class ContractSecretProvider:
    def get_openrouter_api_key(self) -> str:
        return SYNTHETIC_SECRET


def _json(relative: str) -> object:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


@asynccontextmanager
async def _client(scenario: Scenario) -> AsyncIterator[OpenRouterVideoClient]:
    async with HttpxTransport.for_test(scenario.transport()) as transport:
        yield OpenRouterVideoClient(
            request_policy=OpenRouterRequestPolicy(
                identity=EXPECTED_RELEASE_IDENTITY,
                secret_provider=ContractSecretProvider(),
            ),
            transport=transport,
        )


def test_discovery_contract_is_model_agnostic_and_tolerant_of_additions() -> None:
    scenario = Scenario(
        "discovery-catalog",
        [
            ScenarioStep(
                Operation.DISCOVERY,
                "GET",
                "/api/v1/videos/models",
                json_body=_json("discovery/catalog.json"),
            )
        ],
    )

    async def run() -> None:
        async with _client(scenario) as client:
            models = await client.list_video_models()
            assert [model.model_id for model in models] == ["test/video-alpha", "test/video-beta"]
            assert models[0].supported_durations == (4, 8)
            assert models[0].supported_frame_types == frozenset({FrameType.FIRST})
            assert models[1].supported_frame_types == frozenset({FrameType.FIRST, FrameType.LAST})
            assert models[1].generate_audio is True

    asyncio.run(run())
    scenario.assert_complete()


@pytest.mark.parametrize(
    "fixture",
    ["discovery/malformed_missing_id.json", "discovery/malformed_data_type.json"],
)
def test_malformed_discovery_contract_fails_controlled(fixture: str) -> None:
    scenario = Scenario(
        fixture,
        [
            ScenarioStep(
                Operation.DISCOVERY, "GET", "/api/v1/videos/models", json_body=_json(fixture)
            )
        ],
    )

    async def run() -> None:
        async with _client(scenario) as client:
            with pytest.raises(MalformedOpenRouterResponseError):
                await client.list_video_models()

    asyncio.run(run())
    scenario.assert_complete()


def test_submit_writer_is_strict_and_returned_urls_are_non_authoritative() -> None:
    request = GenerationRequest(
        "test/video-beta",
        "SYNTHETIC_PROMPT_CANARY",
        duration=6,
        resolution="1080p",
        generate_audio=True,
        first_frame=FrameReference(FrameType.FIRST, "https://assets.example/frame-1.png"),
        last_frame=FrameReference(FrameType.LAST, "https://assets.example/frame-2.png"),
    )
    expected = request.to_openrouter_payload()
    scenario = Scenario(
        "submit",
        [
            ScenarioStep(
                Operation.SUBMIT,
                "POST",
                "/api/v1/videos",
                status=202,
                json_body=_json("submit/accepted.json"),
                expected_json=expected,
            ),
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/completed_cost.json"),
            ),
        ],
    )

    async def run() -> None:
        async with _client(scenario) as client:
            submitted = await client.submit_video(request)
            assert submitted.job_id == "job_123"
            observed = await client.get_job(submitted.job_id)
            assert observed.usage.actual_cost_usd == Decimal("0.123456")

    asyncio.run(run())
    scenario.assert_complete()
    written = scenario.ledger.requests[0].parsed_json
    assert isinstance(written, dict)
    forbidden = {
        "input_references",
        "provider",
        "callback_url",
        "base_url",
        "api_key",
        "headers",
        "operation_id",
        "user_id",
        "device_id",
        "workflow_id",
        "session_id",
    }
    assert forbidden.isdisjoint(written)
    assert scenario.ledger.requests[1].canonical_path == "/api/v1/videos/job_123"
    scenario.ledger.assert_generation_submit_count(1)


@pytest.mark.parametrize(
    ("fixture", "expected_cost"),
    [
        ("poll/completed_cost.json", Decimal("0.123456")),
        ("poll/completed_no_cost.json", None),
    ],
)
def test_usage_cost_is_exact_and_absence_is_none(
    fixture: str, expected_cost: Decimal | None
) -> None:
    scenario = Scenario(
        fixture,
        [ScenarioStep(Operation.POLL, "GET", "/api/v1/videos/job_123", json_body=_json(fixture))],
    )

    async def run() -> None:
        async with _client(scenario) as client:
            snapshot = await client.get_job("job_123")
            assert snapshot.usage.actual_cost_usd == expected_cost

    asyncio.run(run())
    scenario.assert_complete()


@pytest.mark.parametrize("body", [b"", b"{invalid", b"[]", b'"string"'])
def test_malformed_json_corpus_fails_controlled(body: bytes) -> None:
    scenario = Scenario(
        "malformed-job",
        [ScenarioStep(Operation.POLL, "GET", "/api/v1/videos/job_123", body=body)],
    )

    async def run() -> None:
        async with _client(scenario) as client:
            with pytest.raises(MalformedOpenRouterResponseError):
                await client.get_job("job_123")

    asyncio.run(run())
    scenario.assert_complete()


def test_all_canonical_operations_have_exact_policy_owned_attribution() -> None:
    scenario = Scenario(
        "headers",
        [
            ScenarioStep(
                Operation.DISCOVERY, "GET", "/api/v1/videos/models", json_body={"data": []}
            ),
            ScenarioStep(
                Operation.SUBMIT,
                "POST",
                "/api/v1/videos",
                status=202,
                json_body=_json("submit/accepted.json"),
            ),
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/pending.json"),
            ),
            ScenarioStep(
                Operation.CONTENT, "GET", "/api/v1/videos/job_123/content?index=0", body=b"video"
            ),
        ],
    )

    async def run() -> None:
        async with _client(scenario) as client:
            await client.list_video_models()
            await client.submit_video(GenerationRequest("test/video-alpha", "prompt"))
            await client.get_job("job_123")
            async with client.stream_content("job_123") as response:
                await response.aread()

    asyncio.run(run())
    scenario.assert_complete()
    expected = {
        "HTTP-Referer": "https://github.com/consumerexperience/ComfyUI-OpenRouter-Video",
        "X-OpenRouter-Title": "OpenRouter Video for ComfyUI",
        "X-OpenRouter-Categories": "video-gen",
    }
    assert all(item.authorization_present for item in scenario.ledger.requests)
    assert all(item.attribution == expected for item in scenario.ledger.requests)
