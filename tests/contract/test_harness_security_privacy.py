"""Security and privacy regression checks exercised through the real Core."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from openrouter_video.models import FrameReference, FrameType, GenerationRequest, ProductErrorCode
from openrouter_video.policy import Operation
from tests.harness.core import SYNTHETIC_API_TOKEN, core_harness
from tests.harness.scenario import Scenario, ScenarioStep

FIXTURES = Path(__file__).parents[1] / "fixtures" / "openrouter_video"


def _json(relative: str) -> object:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def test_secret_prompt_and_frame_canaries_never_persist_or_render(tmp_path: Path) -> None:
    prompt = "UNIQUE_SYNTHETIC_PROMPT_CANARY"
    first_url = "https://assets.example/UNIQUE_FIRST_FRAME_CANARY.png"
    last_url = "https://assets.example/UNIQUE_LAST_FRAME_CANARY.png"
    request = GenerationRequest(
        "test/video-beta",
        prompt,
        duration=6,
        resolution="1080p",
        generate_audio=True,
        first_frame=FrameReference(FrameType.FIRST, first_url),
        last_frame=FrameReference(FrameType.LAST, last_url),
    )
    scenario = Scenario(
        "privacy-submit-rejection",
        [
            ScenarioStep(
                Operation.DISCOVERY,
                "GET",
                "/api/v1/videos/models",
                json_body=_json("discovery/catalog.json"),
            ),
            ScenarioStep(Operation.SUBMIT, "POST", "/api/v1/videos", status=429),
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-privacy", request)
            assert result.error is not None
            assert result.error.code is ProductErrorCode.RATE_LIMITED_SUBMIT
            rendered = repr(result) + repr(result.error) + repr(scenario.ledger.requests)
            for canary in (SYNTHETIC_API_TOKEN, prompt, first_url, last_url):
                assert canary not in rendered

    asyncio.run(run())
    scenario.assert_complete()
    database_bytes = (tmp_path / "jobs.sqlite3").read_bytes()
    output_bytes = b"".join(
        path.read_bytes() for path in (tmp_path / "output").glob("*") if path.is_file()
    )
    for canary in (SYNTHETIC_API_TOKEN, prompt, first_url, last_url):
        encoded = canary.encode("utf-8")
        assert encoded not in database_bytes
        assert encoded not in output_bytes


@pytest.mark.parametrize(
    "generation_request",
    [
        GenerationRequest(
            "test/video-alpha",
            "prompt",
            size="1280x720",
            resolution="720p",
        ),
        GenerationRequest(
            "test/video-alpha",
            "prompt",
            first_frame=FrameReference(FrameType.FIRST, "http://assets.example/frame.png"),
        ),
    ],
)
def test_invalid_shape_is_rejected_before_discovery_or_submit(
    generation_request: GenerationRequest, tmp_path: Path
) -> None:
    scenario = Scenario("invalid-shape", [])

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-invalid", generation_request)
            assert result.error is not None

    asyncio.run(run())
    scenario.assert_complete()
    assert scenario.ledger.total_requests == 0
    scenario.ledger.assert_generation_submit_count(0)


@pytest.mark.parametrize(
    "generation_request",
    [
        GenerationRequest("test/video-alpha", "prompt", generate_audio=True),
        GenerationRequest(
            "test/video-alpha",
            "prompt",
            last_frame=FrameReference(FrameType.LAST, "https://assets.example/frame.png"),
        ),
        GenerationRequest("test/video-alpha", "prompt", duration=6),
    ],
)
def test_unsupported_explicit_intent_is_rejected_before_submit(
    generation_request: GenerationRequest, tmp_path: Path
) -> None:
    scenario = Scenario(
        "unsupported-capability",
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
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate("operation-unsupported", generation_request)
            assert result.error is not None
            assert result.error.code is ProductErrorCode.UNSUPPORTED_PARAMETER

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(0)
