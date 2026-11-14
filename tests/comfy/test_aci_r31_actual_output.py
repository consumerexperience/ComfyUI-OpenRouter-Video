"""R3.1 execution-local ACTUAL metadata; no host execution or billing operations."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from openrouter_video.comfy import compat, nodes
from openrouter_video.execution_hooks import ExecutionPhase
from openrouter_video.models import (
    BillingContext,
    GenerationResult,
    LocalLifecycleState,
    ProductError,
    ProductErrorCode,
    VideoArtifact,
)


def completed(cost: Decimal | None = Decimal("2.3100")) -> GenerationResult:
    return GenerationResult(
        LocalLifecycleState.DONE,
        "fixture-job",
        model="fixture/model",
        actual_cost_usd=cost,
        artifact=VideoArtifact(Path("not-read.mp4"), "video/mp4", 1),
    )


@pytest.fixture
def bridge(monkeypatch: pytest.MonkeyPatch) -> list[ExecutionPhase]:
    phases: list[ExecutionPhase] = []

    async def report(phase: ExecutionPhase, node_id: str | None) -> None:
        phases.append(phase)

    monkeypatch.setattr(compat, "report_phase", report)
    monkeypatch.setattr(nodes, "to_native_video", lambda artifact: "native-video")
    monkeypatch.setattr(nodes, "to_native_last_frame", lambda artifact: "native-last-frame")
    return phases


@pytest.mark.parametrize(
    "cost,wire", [(Decimal("2.3100"), "2.3100"), (Decimal("0.000"), "0.000"), (None, None)]
)
def test_terminal_actual_metadata_preserves_exact_cost_and_six_outputs(
    bridge: list[ExecutionPhase],
    cost: Decimal | None,
    wire: str | None,
) -> None:
    output: Any = asyncio.run(
        nodes._node_output(completed(cost), "fixture-node", operation_kind="GENERATE")
    )
    assert output.values == (
        "native-video",
        "fixture-job",
        "fixture/model",
        wire or "",
        "DONE",
        "native-last-frame",
    )
    assert output.ui == {
        "orv_actual_v1": [
            dict(
                schema_version=1,
                job_id="fixture-job",
                model="fixture/model",
                amount_usd=wire,
                state="DONE",
                operation_kind="GENERATE",
            )
        ]
    }
    assert bridge == [ExecutionPhase.NATIVE_VIDEO, ExecutionPhase.DONE]


def test_resume_ui_requires_the_normalized_actual_input_job_and_never_submits(
    monkeypatch: pytest.MonkeyPatch,
    bridge: list[ExecutionPhase],
) -> None:
    calls: list[str] = []

    class Runtime:
        async def resume(self, job_id: str, node_id: str | None) -> GenerationResult:
            calls.append(job_id)
            return completed(Decimal("0"))

    monkeypatch.setattr(nodes, "get_runtime", lambda: Runtime())
    output: Any = asyncio.run(nodes.OpenRouterVideoResume.execute("  fixture-job  "))
    assert calls == ["fixture-job"]
    row = output.ui["orv_actual_v1"][0]
    assert row["expected_job_id"] == row["job_id"] == "fixture-job"
    assert row["operation_kind"] == "RESUME" and row["amount_usd"] == "0"
    assert len(output.values) == 6


@pytest.mark.parametrize("expected", [None, "other-job"])
def test_resume_mismatch_suppresses_only_auxiliary_ui(
    bridge: list[ExecutionPhase],
    expected: str | None,
) -> None:
    output: Any = asyncio.run(
        nodes._node_output(completed(), "node", operation_kind="RESUME", expected_job_id=expected)
    )
    assert output.ui is None
    assert output.values[0] == "native-video" and len(output.values) == 6
    assert output.values[3] == "2.3100"


@pytest.mark.parametrize(
    "state",
    [
        LocalLifecycleState.COMPLETED,
        LocalLifecycleState.FAILED,
        LocalLifecycleState.SUBMISSION_UNKNOWN,
    ],
)
def test_nonterminal_or_unsuccessful_result_never_fabricates_completed_actual(
    bridge: list[ExecutionPhase],
    state: LocalLifecycleState,
) -> None:
    result = replace(completed(), state=state)
    assert nodes._actual_ui_metadata(result, operation_kind="GENERATE") is None


@pytest.mark.parametrize(
    "job,model",
    [
        ("", "fixture/model"),
        (None, "fixture/model"),
        ("fixture-job", None),
        ("bad\njob", "fixture/model"),
    ],
)
def test_unusable_receipt_identity_keeps_video_outputs_without_broadcast(
    bridge: list[ExecutionPhase],
    job: str | None,
    model: str | None,
) -> None:
    output: Any = asyncio.run(
        nodes._node_output(replace(completed(), job_id=job, model=model), "node")
    )
    assert output.ui is None and len(output.values) == 6
    assert output.values[0] == "native-video"


def test_error_path_cannot_emit_actual_or_reach_native_bridge(bridge: list[ExecutionPhase]) -> None:
    result = replace(
        completed(),
        error=ProductError(
            ProductErrorCode.GENERATION_FAILED, "fixture failure", BillingContext.KNOWN_JOB_EXISTS
        ),
    )
    with pytest.raises(nodes.AdapterExecutionError):
        asyncio.run(nodes._node_output(result, "node"))
    assert bridge == []


def test_actual_payload_has_only_execution_receipt_fields(bridge: list[ExecutionPhase]) -> None:
    ui = nodes._actual_ui_metadata(completed(), operation_kind="GENERATE")
    assert ui is not None
    row: Any = ui["orv_actual_v1"][0]  # type: ignore[index]
    assert set(row) == {
        "schema_version",
        "job_id",
        "model",
        "amount_usd",
        "state",
        "operation_kind",
    }
    assert not set(row) & {
        "prompt",
        "path",
        "url",
        "api_key",
        "estimate",
        "planning",
        "node_id",
        "user_id",
    }
