"""Offline guardrails for the isolated X2 manual probe."""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx
import pytest

from tests.manual import x2_video_data_url_probe as probe


def _key_data(**changes: object) -> dict[str, object]:
    data: dict[str, object] = {
        "is_management_key": False,
        "is_provisioning_key": False,
        "limit": 2,
        "limit_remaining": 2,
        "limit_reset": None,
        "usage": 0,
    }
    data.update(changes)
    return {"data": data}


def test_dry_run_has_exact_body_and_no_secret_or_media_in_evidence() -> None:
    wire, evidence = probe.build_request()
    body = json.loads(wire)
    assert body == {
        "model": "bytedance/seedance-2.5",
        "prompt": body["prompt"],
        "input_references": [
            {
                "type": "video_url",
                "video_url": {"url": body["input_references"][0]["video_url"]["url"]},
            }
        ],
        "duration": 4,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
    }
    assert body["input_references"][0]["video_url"]["url"].startswith("data:video/mp4;base64,")
    assert evidence["SOURCE_VIDEO_BYTES"] == 394_950
    assert evidence["BASE64_CHARACTERS"] == 526_600
    assert evidence["FINAL_JSON_UTF8_BYTES"] == len(wire) == 527_087
    assert "data:video" not in json.dumps(evidence)
    assert "Authorization" not in json.dumps(evidence)


def test_key_preflight_accepts_only_unused_dedicated_two_dollar_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url == probe.KEY_ENDPOINT
        return httpx.Response(200, json=_key_data())

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        result = probe.check_key(client, "synthetic-test-key")
    assert result == {
        "KEY_PREFLIGHT": "VALID",
        "LIMIT_USD": "2",
        "LIMIT_REMAINING_USD": "2",
        "CURRENT_USAGE_USD": "0",
        "LIMIT_RESET": "none",
    }


@pytest.mark.parametrize(
    "key",
    [
        "sk-or-v1-6...1",
        "sk-or-v1-" + "a" * 64 + " ",
        "Bearer sk-or-v1-" + "a" * 64,
        "sk-or-v1-" + "a" * 64 + "\n",
    ],
)
def test_key_input_mistakes_block_before_get(key: str) -> None:
    with pytest.raises(probe.PreflightError):
        probe._validate_key_text(key)


def test_http_400_reports_only_safe_response_class() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 400, "message": "secret-marker"}})

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(probe.PreflightError, match="key_get_http_400_json_error_code_400") as exc,
    ):
        probe.check_key(client, "synthetic-test-key")
    assert "secret-marker" not in str(exc.value)


@pytest.mark.parametrize(
    "changes",
    [
        {"limit": None},
        {"limit": 3},
        {"limit_remaining": 1.99},
        {"usage": 0.01},
        {"limit_reset": "daily"},
        {"is_management_key": True},
        {"is_provisioning_key": True},
    ],
)
def test_key_preflight_fails_closed(changes: dict[str, object]) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_key_data(**changes))

    with (
        httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client,
        pytest.raises(probe.PreflightError),
    ):
        probe.check_key(client, "synthetic-test-key")


@pytest.mark.parametrize(
    ("status", "result"),
    [
        (400, "DEFINITE_REJECTION"),
        (429, "SUBMISSION_UNKNOWN"),
        (500, "SUBMISSION_UNKNOWN"),
        (302, "SUBMISSION_UNKNOWN"),
    ],
)
def test_one_post_no_redirect_or_retry(status: int, result: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, headers={"Location": "https://example.com/unsafe"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        actual = probe.post_once(client, "synthetic-test-key", b"{}")
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url == probe.ENDPOINT
    assert actual["RESULT"] == result
    assert actual["POST_ATTEMPT_COUNT"] == 1


def test_accepted_job_id_and_network_ambiguity() -> None:
    def accepted(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"id": "gen-vid-test_123", "polling_url": "ignored"})

    with httpx.Client(transport=httpx.MockTransport(accepted)) as client:
        result = probe.post_once(client, "synthetic-test-key", b"{}")
    assert result == {
        "RESULT": "ACCEPTED",
        "HTTP_STATUS": 202,
        "JOB_ID": "gen-vid-test_123",
        "POST_ATTEMPT_COUNT": 1,
    }

    attempts = 0

    def broken(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(broken)) as client:
        result = probe.post_once(client, "synthetic-test-key", b"{}")
    assert attempts == 1
    assert result == {"RESULT": "SUBMISSION_UNKNOWN", "POST_ATTEMPT_COUNT": 1}


def test_local_error_reports_safe_stage_without_request_body(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["x2_video_data_url_probe.py", "--key-preflight"])

    def broken_request() -> tuple[bytes, dict[str, object]]:
        raise OSError("private path that must not be printed")

    monkeypatch.setattr(probe, "build_request", broken_request)
    assert probe.main() == 1
    output: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert output == {
        "POST_ATTEMPT_COUNT": 0,
        "REASON": "local_request_local_error",
        "RESULT": "PREFLIGHT_BLOCKED",
    }
