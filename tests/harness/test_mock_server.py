"""Self-tests for the local mock/fault harness."""

from __future__ import annotations

import asyncio
import http.client

import httpx
import pytest

from openrouter_video.policy import Operation
from tests.harness.mock_server import LocalFaultServer, ResponsePlan
from tests.harness.scenario import RequestLedger, Scenario, ScenarioStep


def test_server_binds_only_to_loopback_and_records_sanitized_request() -> None:
    with LocalFaultServer([ResponsePlan(status=202, body=b'{"id":"test-only"}')]) as server:
        host, port = server.address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            "/synthetic",
            body=b"fixture",
            headers={"Authorization": "TEST_ONLY_NOT_A_SECRET"},
        )
        response = connection.getresponse()
        assert response.status == 202
        assert response.read() == b'{"id":"test-only"}'
        connection.close()

        assert host == "127.0.0.1"
        assert server.post_count == 1
        assert server.requests[0].path == "/synthetic"
        assert server.requests[0].headers["Authorization"] == "[REDACTED]"


def test_server_can_emit_malformed_payload_and_redirect_without_following_it() -> None:
    plans = [
        ResponsePlan(body=b"{malformed"),
        ResponsePlan(status=302, headers={"Location": "https://invalid.example/blocked"}, body=b""),
    ]
    with LocalFaultServer(plans) as server:
        host, port = server.address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/malformed")
        first = connection.getresponse()
        assert first.read() == b"{malformed"
        connection.request("GET", "/redirect")
        second = connection.getresponse()
        assert second.status == 302
        assert second.getheader("Location") == "https://invalid.example/blocked"
        connection.close()

        assert [request.path for request in server] == ["/malformed", "/redirect"]


def test_server_can_drop_connection_after_receiving_a_request() -> None:
    with LocalFaultServer([ResponsePlan(disconnect_after_request=True)]) as server:
        host, port = server.address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("POST", "/disconnect", body=b"synthetic")
        with pytest.raises(http.client.RemoteDisconnected):
            connection.getresponse()
        connection.close()
        assert server.post_count == 1


def test_scenario_enforces_order_and_ledger_counts_generation_submit() -> None:
    scenario = Scenario(
        "ordered",
        [
            ScenarioStep(
                Operation.SUBMIT,
                "POST",
                "/api/v1/videos",
                status=202,
                json_body={"id": "job-1", "status": "pending"},
            ),
            ScenarioStep(
                Operation.POLL,
                "GET",
                "/api/v1/videos/job-1",
                json_body={"id": "job-1", "status": "completed"},
            ),
        ],
    )

    async def run() -> None:
        async with httpx.AsyncClient(transport=scenario.transport()) as client:
            await client.post("https://openrouter.ai/api/v1/videos", json={"synthetic": True})
            await client.get("https://openrouter.ai/api/v1/videos/job-1")

    asyncio.run(run())
    scenario.assert_complete()
    assert scenario.ledger.total_requests == 2
    assert scenario.ledger.count_by_operation(Operation.POLL) == 1
    assert scenario.ledger.count_by_job_id("job-1") == 1
    scenario.ledger.assert_generation_submit_count(1)


def test_scenario_rejects_unexpected_request_and_unconsumed_step() -> None:
    scenario = Scenario(
        "strict",
        [ScenarioStep(Operation.POLL, "GET", "/api/v1/videos/job-1")],
    )

    async def wrong() -> None:
        async with httpx.AsyncClient(transport=scenario.transport()) as client:
            await client.get("https://openrouter.ai/api/v1/videos/job-2")

    with pytest.raises(AssertionError, match="expected path"):
        asyncio.run(wrong())
    with pytest.raises(AssertionError, match="unconsumed"):
        scenario.assert_complete()


def test_request_ledger_safe_repr_hides_body_and_authorization() -> None:
    ledger = RequestLedger()
    request = httpx.Request(
        "POST",
        "https://openrouter.ai/api/v1/videos",
        headers={"Authorization": "Bearer SYNTHETIC_SECRET"},
        json={"prompt": "PROMPT_CANARY"},
    )
    captured = ledger.record(request)
    rendered = repr(captured)
    assert captured.authorization_present
    assert "SYNTHETIC_SECRET" not in rendered
    assert "PROMPT_CANARY" not in rendered


def test_local_fault_server_strictly_matches_and_counts_generation_endpoint() -> None:
    plan = ResponsePlan(
        status=202,
        body=b"{}",
        expected_method="POST",
        expected_path="/api/v1/videos",
    )
    with LocalFaultServer([plan]) as server:
        host, port = server.address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("POST", "/api/v1/videos", body=b"{}")
        response = connection.getresponse()
        assert response.status == 202
        response.read()
        connection.close()
        assert server.wait_until_request_received()
        assert server.generation_submit_count == 1
