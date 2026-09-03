"""Self-tests for the local mock/fault harness."""

from __future__ import annotations

import http.client

import pytest

from tests.harness.mock_server import LocalFaultServer, ResponsePlan


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
