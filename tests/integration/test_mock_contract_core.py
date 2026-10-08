"""Happy-path contract harness flow through the real Phase-5 Core."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from openrouter_video.models import (
    GenerationRequest,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    LocalLifecycleState,
)
from openrouter_video.policy import Operation
from tests.fixtures.golden_pack import load_default_pack
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


@pytest.mark.parametrize(
    "references, method",
    [
        (
            (
                InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png"),
                InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png"),
            ),
            InferenceMethod.MI2V,
        ),
        (
            (InputReference(InputReferenceKind.VIDEO, "https://assets.example/b.mp4"),),
            InferenceMethod.VR2V,
        ),
    ],
    ids=("multi-image", "video"),
)
def test_seedance_overlay_reference_modes_use_the_existing_generate_lifecycle(
    tmp_path: Path,
    references: tuple[InputReference, ...],
    method: InferenceMethod,
) -> None:
    prompt = "REFERENCE_PROMPT_CANARY"
    request = GenerationRequest(
        "bytedance/seedance-2.5",
        prompt,
        inference_method=method,
        input_references=InputReferenceCollection(references),
    )
    expected_references = [
        {
            "type": f"{reference.kind.value}_url",
            f"{reference.kind.value}_url": {"url": reference.url},
        }
        for reference in references
    ]
    scenario = Scenario(
        "seedance-reference-overlay",
        [
            ScenarioStep(
                Operation.DISCOVERY,
                "GET",
                "/api/v1/videos/models",
                json_body={"data": [{"id": "bytedance/seedance-2.5"}]},
            ),
            ScenarioStep(
                Operation.SUBMIT,
                "POST",
                "/api/v1/videos",
                status=202,
                json_body=_json("submit/accepted.json"),
                expected_json={
                    "model": "bytedance/seedance-2.5",
                    "generate_audio": False,
                    "prompt": prompt,
                    "input_references": expected_references,
                },
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
            result = await core.generate.generate("operation-reference", request)
            assert result.state is LocalLifecycleState.DONE
            assert result.artifact is not None and result.artifact.path.read_bytes() == MP4

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)
    database_bytes = (tmp_path / "jobs.sqlite3").read_bytes()
    for sensitive in (prompt, *(reference.url for reference in references)):
        assert sensitive.encode() not in database_bytes


def test_default_golden_pack_multimodal_order_uses_mocked_generate_lifecycle(
    tmp_path: Path,
) -> None:
    pack = load_default_pack()
    ordered_assets = pack.canonical_references
    references = tuple(
        InputReference(
            InputReferenceKind[asset["type"]],
            f"https://golden-pack.invalid/{asset['sha256']}/{asset['local_filename']}",
        )
        for asset in ordered_assets
    )
    expected_references = [
        {
            "type": asset["transport"]["wire_type"],
            asset["transport"]["wire_type"]: {"url": reference.url},
        }
        for asset, reference in zip(ordered_assets, references, strict=True)
    ]
    assert [reference.kind for reference in references] == [
        InputReferenceKind.IMAGE,
        InputReferenceKind.IMAGE,
        InputReferenceKind.VIDEO,
        InputReferenceKind.AUDIO,
    ]

    prompt = "DEFAULT_GOLDEN_PACK_MMR2V_MOCK_CANARY"
    request = GenerationRequest(
        "bytedance/seedance-2.5",
        prompt,
        duration=5,
        inference_method=InferenceMethod.MMR2V,
        input_references=InputReferenceCollection(references),
    )
    scenario = Scenario(
        "default-golden-pack-mmr2v",
        [
            ScenarioStep(
                Operation.DISCOVERY,
                "GET",
                "/api/v1/videos/models",
                json_body={"data": [{"id": "bytedance/seedance-2.5"}]},
            ),
            ScenarioStep(
                Operation.SUBMIT,
                "POST",
                "/api/v1/videos",
                status=202,
                json_body=_json("submit/accepted.json"),
                expected_json={
                    "model": "bytedance/seedance-2.5",
                    "generate_audio": False,
                    "duration": 5,
                    "prompt": prompt,
                    "input_references": expected_references,
                },
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
            result = await core.generate.generate("operation-golden-mmr2v", request)
            assert result.state is LocalLifecycleState.DONE
            assert result.artifact is not None and result.artifact.path.read_bytes() == MP4

    asyncio.run(run())
    scenario.assert_complete()
    scenario.ledger.assert_generation_submit_count(1)
