"""Happy-path contract harness flow through the real Phase-5 Core."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from openrouter_video.models import GenerationRequest, LocalLifecycleState
from openrouter_video.policy import Operation
from tests.harness.core import core_harness
from tests.harness.scenario import Scenario, ScenarioStep

FIXTURES = Path(__file__).parents[1] / "fixtures" / "openrouter_video"
MP4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


def _json(relative: str) -> object:
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def test_real_core_happy_path_is_one_submit_one_job_and_durable_artifact(tmp_path: Path) -> None:
    scenario = Scenario(
        "real-core-happy",
        [
            ScenarioStep(
                Operation.DISCOVERY,
                "GET",
                "/api/v1/videos/models",
                json_body=_json("discovery/catalog.json"),
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
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/in_progress.json"),
            ),
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job_123",
                json_body=_json("poll/completed_cost.json"),
            ),
            ScenarioStep(
                Operation.CONTENT,
                "GET",
                "/api/v1/videos/job_123/content?index=0",
                headers={"Content-Type": "video/mp4"},
                body=MP4,
            ),
        ],
    )

    async def run() -> None:
        async with core_harness(scenario, tmp_path) as core:
            result = await core.generate.generate(
                "operation-happy",
                GenerationRequest("test/video-alpha", "synthetic private prompt", duration=4),
            )
            assert result.state is LocalLifecycleState.DONE
            assert result.job_id == "job_123"
            assert result.actual_cost_usd == Decimal("0.123456")
            assert result.artifact is not None and result.artifact.path.read_bytes() == MP4
            assert core.clock.delays == [30.0, 30.0]
            stored = core.store.get_by_job_id("job_123")
            assert stored is not None and stored.output_relpath == result.artifact.path.name

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)
    assert scenario.ledger.count_by_job_id("job_123") == 4
    assert scenario.ledger.content_request_count == 1
