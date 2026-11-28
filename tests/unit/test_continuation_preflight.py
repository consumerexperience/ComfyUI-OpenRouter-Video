"""Continuation reads status before a single paid capability is claimed; mocks only."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from openrouter_video.capabilities import CapabilityService
from openrouter_video.models import (
    BillingContext,
    GenerationRequest,
    InferenceMethod,
    LocalLifecycleState,
    ModelCapabilities,
    RemoteJobSnapshot,
)
from tests.unit.test_application import ScenarioClient, _generate_service
from tests.unit.test_full_catalogue_coverage import model, witness

PREVIOUS = "gen-vid-1234567890-12345678901234567890"


@pytest.mark.parametrize("canonical_present", [False, True])
@pytest.mark.parametrize(
    "state,prior_model,valid",
    [
        ("completed", "google/gemini-omni-1.2-flash", True),
        ("in_progress", "google/gemini-omni-1.2-flash", False),
        ("completed", "other/model", False),
        ("completed", None, False),
    ],
)
def test_previous_job_preflight_prevents_unsafe_submit(
    tmp_path: Path, state: str, prior_model: str | None, valid: bool, canonical_present: bool
) -> None:
    m = model("google/gemini-omni-1.2-flash")
    if not canonical_present:
        m = replace(m, canonical_slug=None)
    req = replace(witness(m, InferenceMethod.V2V_EDIT), source_video=None, previous_job_id=PREVIOUS)

    class Client(ScenarioClient):
        previous_reads = 0

        async def get_job(self, job_id: str) -> RemoteJobSnapshot:
            if job_id == PREVIOUS:
                self.previous_reads += 1
                return RemoteJobSnapshot(PREVIOUS, state, model=prior_model)
            return await super().get_job(job_id)

        async def submit_video(self, request: GenerationRequest) -> RemoteJobSnapshot:
            self.submit_calls += 1
            assert request.previous_job_id == PREVIOUS
            assert isinstance(self.submit_outcome, RemoteJobSnapshot)
            return self.submit_outcome

    client = Client(
        submit=RemoteJobSnapshot("job-1", "completed", model=m.model_id),
        polls=[RemoteJobSnapshot("job-1", "completed", model=m.model_id)],
    )
    service, store = _generate_service(tmp_path, client)

    class Discovery:
        async def list_video_models(self) -> tuple[ModelCapabilities, ...]:
            return (m,)

    service._capabilities = CapabilityService(client=Discovery(), store=store)
    result = asyncio.run(service.generate("TEST_ONLY_CONTINUATION", req))
    assert client.previous_reads == 1
    assert client.submit_calls == int(valid)
    if valid:
        again = asyncio.run(service.generate("TEST_ONLY_CONTINUATION", req))
        assert client.submit_calls == 1
        assert client.previous_reads == 1
        assert again.state is result.state
    else:
        assert result.state is LocalLifecycleState.NOT_SUBMITTED
        assert result.error is not None
        assert result.error.billing_context is BillingContext.NO_SUBMIT
