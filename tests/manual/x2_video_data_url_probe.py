"""Isolated X2 Video data-URL contract probe. Default: offline dry-run.

Owner-only network modes use a masked, interactive dedicated inference key.
No product Core or ComfyUI runtime path is involved. Never run --post-once
without a new, immediate Product Owner authorization for exactly this request.
"""

# ruff: noqa: T201 - this manual probe emits sanitized evidence to stdout

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

ENDPOINT = "https://openrouter.ai/api/v1/videos"
KEY_ENDPOINT = "https://openrouter.ai/api/v1/key"
MODEL = "bytedance/seedance-2.5"
FIXTURE = Path(__file__).resolve().parents[1] / "live/fixtures/phase9/motion-reference.mp4"
PROMPT = Path(__file__).resolve().parents[1] / "live/fixtures/phase9/prompts/video-reference.txt"
FIXTURE_SHA256 = "e6009ff03feb01893c4dcc5a77d564e6af23066c4305dea1460d48696f8f448b"
PROMPT_SHA256 = "3ba07d4f36cb4ba7a1b75d0b9367a7e61c623aea20a94d7d420ed28bd1083181"
FIXTURE_BYTES = 394_950
KEY_LIMIT_USD = Decimal("2.00")
JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class PreflightError(Exception):
    """Local or read-only financial preflight did not pass."""


def _checked_bytes(path: Path, expected_hash: str, expected_size: int | None = None) -> bytes:
    data = path.read_bytes()
    if expected_size is not None and len(data) != expected_size:
        raise PreflightError("fixture_size_drift")
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise PreflightError(
            "fixture_hash_drift" if expected_size is not None else "prompt_hash_drift"
        )
    return data


def build_request() -> tuple[bytes, dict[str, object]]:
    source = _checked_bytes(FIXTURE, FIXTURE_SHA256, FIXTURE_BYTES)
    prompt = _checked_bytes(PROMPT, PROMPT_SHA256).decode("utf-8").strip()
    if not prompt:
        raise PreflightError("prompt_empty")
    encoded = base64.b64encode(source).decode("ascii")
    data_url = "data:video/mp4;base64," + encoded
    body = {
        "model": MODEL,
        "prompt": prompt,
        "input_references": [{"type": "video_url", "video_url": {"url": data_url}}],
        "duration": 4,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
    }
    wire = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    evidence: dict[str, object] = {
        "ENDPOINT": f"POST {ENDPOINT}",
        "MODEL": MODEL,
        "INTENT_LOCAL_ONLY": "VR2V",
        "DURATION_SECONDS": 4,
        "RESOLUTION": "480p",
        "ASPECT_RATIO": "16:9",
        "GENERATE_AUDIO": False,
        "REFERENCE_COUNT": 1,
        "REFERENCE_TYPE": "VIDEO",
        "DATA_URL_MIME": "video/mp4",
        "FIXTURE_SHA256": FIXTURE_SHA256,
        "SOURCE_VIDEO_BYTES": len(source),
        "BASE64_CHARACTERS": len(encoded),
        "DATA_URL_CHARACTERS": len(data_url),
        "FINAL_JSON_UTF8_BYTES": len(wire),
        "PROMPT_SHA256": PROMPT_SHA256,
    }
    return wire, evidence


def _usd(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PreflightError("key_limit_fields_missing_or_invalid")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise PreflightError("key_limit_fields_missing_or_invalid") from exc
    if not result.is_finite():
        raise PreflightError("key_limit_fields_missing_or_invalid")
    return result


def _validate_key_text(key: str) -> None:
    # Check only a recognizable prefix and input corruption, not secret length or mask.
    if not key.startswith("sk-or-") or key in {"sk-or-", "sk-or-v1-"}:
        raise PreflightError("key_input_shape_invalid")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in key):
        raise PreflightError("key_input_contains_whitespace_or_control")


def _dashboard_x2_evidence() -> dict[str, object]:
    """Record Owner attestation; never infer key identity from its dashboard mask."""
    return {
        "KEY_GUARDRAIL": "OWNER_DASHBOARD_ATTESTED",
        "KEY_NAME": "OPENROUTER[Test]",
        "OWNER_DASHBOARD_LIMIT_USD": "5",
        "OWNER_DASHBOARD_USAGE_USD": "0.000",
    }


def _response_kind(response: httpx.Response) -> str:
    if not response.content:
        return "empty"
    if (
        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        return "non_json"
    try:
        value = response.json()
    except ValueError:
        return "invalid_json"
    if not isinstance(value, dict):
        return "json_other"
    error = value.get("error")
    if not isinstance(error, dict):
        return "json_other"
    code = error.get("code")
    if type(code) is int and 100 <= code <= 599:
        return f"json_error_code_{code}"
    return "json_error_no_numeric_code"


def check_key(client: httpx.Client, key: str) -> dict[str, object]:
    try:
        response = client.get(KEY_ENDPOINT, headers={"Authorization": f"Bearer {key}"})
    except httpx.RequestError as exc:
        raise PreflightError("key_get_network_error") from exc
    if response.status_code != 200:
        raise PreflightError(f"key_get_http_{response.status_code}_{_response_kind(response)}")
    try:
        outer = response.json()
    except ValueError as exc:
        raise PreflightError("key_get_invalid_json") from exc
    data = outer.get("data") if isinstance(outer, dict) else None
    if not isinstance(data, dict):
        raise PreflightError("key_get_missing_data")
    if data.get("is_management_key") is not False or data.get("is_provisioning_key") is not False:
        raise PreflightError("not_dedicated_inference_key")
    limit = _usd(data.get("limit"))
    remaining = _usd(data.get("limit_remaining"))
    usage = _usd(data.get("usage"))
    if "limit_reset" not in data or data["limit_reset"] is not None:
        raise PreflightError("key_limit_resets_or_unknown")
    if limit != KEY_LIMIT_USD or remaining < KEY_LIMIT_USD or usage != 0:
        raise PreflightError("key_limit_or_usage_mismatch")
    return {
        "KEY_PREFLIGHT": "VALID",
        "LIMIT_USD": str(limit),
        "LIMIT_REMAINING_USD": str(remaining),
        "CURRENT_USAGE_USD": str(usage),
        "LIMIT_RESET": "none",
    }


def post_once(client: httpx.Client, key: str, wire: bytes) -> dict[str, object]:
    # Deliberately one POST call, no loop, no retry, and no redirect follow.
    try:
        response = client.post(
            ENDPOINT,
            content=wire,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
    except httpx.RequestError:
        return {"RESULT": "SUBMISSION_UNKNOWN", "POST_ATTEMPT_COUNT": 1}
    if response.status_code == 202:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        job_id = payload.get("id") if isinstance(payload, dict) else None
        if isinstance(job_id, str) and JOB_ID.fullmatch(job_id):
            return {
                "RESULT": "ACCEPTED",
                "HTTP_STATUS": 202,
                "JOB_ID": job_id,
                "POST_ATTEMPT_COUNT": 1,
            }
        return {"RESULT": "SUBMISSION_UNKNOWN", "HTTP_STATUS": 202, "POST_ATTEMPT_COUNT": 1}
    if 400 <= response.status_code < 500 and response.status_code != 429:
        return {
            "RESULT": "DEFINITE_REJECTION",
            "HTTP_STATUS": response.status_code,
            "POST_ATTEMPT_COUNT": 1,
        }
    return {
        "RESULT": "SUBMISSION_UNKNOWN",
        "HTTP_STATUS": response.status_code,
        "POST_ATTEMPT_COUNT": 1,
    }


def _print_evidence(value: dict[str, object]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="X2 VIDEO transport probe; offline dry-run by default"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="offline, no key and no network (default)"
    )
    mode.add_argument("--key-preflight", action="store_true", help="read-only GET /api/v1/key")
    mode.add_argument(
        "--post-once", action="store_true", help="one paid POST; requires new Owner approval"
    )
    parser.add_argument(
        "--dashboard-attested-5usd",
        action="store_true",
        help="use Owner-confirmed OPENROUTER[Test] $5 TOTAL cap for the one X2 POST",
    )
    args = parser.parse_args()
    stage = "local_request"
    try:
        if args.post_once and not args.dashboard_attested_5usd:
            raise PreflightError("dashboard_attestation_required_for_post")
        if args.dashboard_attested_5usd and not args.post_once:
            raise PreflightError("dashboard_attestation_only_for_post")
        wire, evidence = build_request()
        if not args.key_preflight and not args.post_once:
            _print_evidence({**evidence, "MODE": "DRY_RUN", "POST_ATTEMPT_COUNT": 0})
            return 0
        stage = "secure_key_input"
        key = os.environ.get("OPENROUTER_X2_KEY")
        if key is None:
            if not sys.stdin.isatty():
                raise PreflightError("interactive_key_entry_required")
            key = getpass.getpass("Dedicated X2 inference key (hidden): ")
        _validate_key_text(key)
        key_evidence = _dashboard_x2_evidence() if args.dashboard_attested_5usd else {}
        stage = "http_client_setup"
        transport = httpx.HTTPTransport(retries=0, trust_env=False)
        with httpx.Client(
            transport=transport,
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(30.0),
        ) as client:
            if args.key_preflight:
                stage = "key_get"
                key_evidence = check_key(client, key)
                _print_evidence({**key_evidence, "POST_ATTEMPT_COUNT": 0})
                return 0
            stage = "post_once"
            result = post_once(client, key, wire)
        _print_evidence({**evidence, **key_evidence, **result})
        return 0 if result["RESULT"] == "ACCEPTED" else 1
    except (OSError, UnicodeError, EOFError, PreflightError) as exc:
        reason = str(exc) if isinstance(exc, PreflightError) else f"{stage}_local_error"
        attempted = 1 if stage == "post_once" else 0
        status = "SUBMISSION_UNKNOWN" if attempted else "PREFLIGHT_BLOCKED"
        _print_evidence({"RESULT": status, "REASON": reason, "POST_ATTEMPT_COUNT": attempted})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
