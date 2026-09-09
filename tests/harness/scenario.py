"""Deterministic semantic and loopback transports for the contract harness."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from openrouter_video.policy import Operation

_ATTRIBUTION_HEADERS = (
    "HTTP-Referer",
    "X-OpenRouter-Title",
    "X-OpenRouter-Categories",
)


def _canonical_path(request: httpx.Request) -> str:
    return request.url.raw_path.decode("ascii")


def _classify(method: str, path: str) -> tuple[Operation | None, str | None, int | None]:
    split = urlsplit(path)
    segments = split.path.strip("/").split("/")
    if method == "GET" and split.path == "/api/v1/videos/models":
        return Operation.DISCOVERY, None, None
    if method == "POST" and split.path == "/api/v1/videos":
        return Operation.SUBMIT, None, None
    if method == "GET" and len(segments) == 4 and segments[:3] == ["api", "v1", "videos"]:
        return Operation.POLL, segments[3], None
    if (
        method == "GET"
        and len(segments) == 5
        and segments[:3] == ["api", "v1", "videos"]
        and segments[4] == "content"
    ):
        index = int(dict(item.split("=", 1) for item in split.query.split("&"))["index"])
        return Operation.CONTENT, segments[3], index
    return None, None, None


@dataclass(frozen=True, slots=True)
class CapturedRequest:
    """Structured in-memory request evidence with a deliberately safe repr."""

    method: str
    canonical_path: str
    operation: Operation | None
    job_id: str | None
    content_index: int | None
    authorization_present: bool
    attribution: Mapping[str, str]
    parsed_json: object | None = field(repr=False)


class RequestLedger:
    """Canonical request ledger with first-class paid-submit assertions."""

    def __init__(self) -> None:
        self._requests: list[CapturedRequest] = []

    @property
    def requests(self) -> tuple[CapturedRequest, ...]:
        return tuple(self._requests)

    @property
    def total_requests(self) -> int:
        return len(self._requests)

    @property
    def generation_submit_count(self) -> int:
        return sum(
            item.method == "POST" and item.canonical_path == "/api/v1/videos"
            for item in self._requests
        )

    @property
    def content_request_count(self) -> int:
        return sum(item.operation is Operation.CONTENT for item in self._requests)

    def record(self, request: httpx.Request) -> CapturedRequest:
        path = _canonical_path(request)
        operation, job_id, content_index = _classify(request.method, path)
        parsed_json: object | None = None
        if request.content:
            try:
                parsed_json = json.loads(request.content)
            except (json.JSONDecodeError, UnicodeError):
                parsed_json = None
        captured = CapturedRequest(
            method=request.method,
            canonical_path=path,
            operation=operation,
            job_id=job_id,
            content_index=content_index,
            authorization_present="Authorization" in request.headers,
            attribution={
                name: request.headers[name]
                for name in _ATTRIBUTION_HEADERS
                if name in request.headers
            },
            parsed_json=parsed_json,
        )
        self._requests.append(captured)
        return captured

    def count_by_method(self, method: str) -> int:
        return Counter(item.method for item in self._requests)[method.upper()]

    def count_by_operation(self, operation: Operation) -> int:
        return sum(item.operation is operation for item in self._requests)

    def count_by_path(self, path: str) -> int:
        return sum(item.canonical_path == path for item in self._requests)

    def count_by_job_id(self, job_id: str) -> int:
        return sum(item.job_id == job_id for item in self._requests)

    def assert_generation_submit_count(self, expected: int) -> None:
        actual = self.generation_submit_count
        assert actual == expected, (
            f"generation submit count: expected {expected}, observed {actual}"
        )

    def assert_no_additional_generation_submit(self, baseline: int) -> None:
        self.assert_generation_submit_count(baseline)

    def assert_resume_submits_zero(self, baseline: int = 0) -> None:
        self.assert_no_additional_generation_submit(baseline)


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    """One expected operation and deterministic response or transport exception."""

    operation: Operation
    method: str
    path: str
    status: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)
    json_body: object | None = None
    body: bytes | None = None
    exception: httpx.HTTPError | None = field(default=None, repr=False)
    expected_json: Mapping[str, object] | None = field(default=None, repr=False)
    entered_event: asyncio.Event | None = field(default=None, repr=False, compare=False)
    release_event: asyncio.Event | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.json_body is not None and self.body is not None:
            raise ValueError("Scenario step cannot define both JSON and byte bodies")


class Scenario:
    """Small strict ordered scenario used by ``httpx.MockTransport``."""

    def __init__(self, name: str, steps: list[ScenarioStep]) -> None:
        self.name = name
        self._steps = tuple(steps)
        self._next = 0
        self.ledger = RequestLedger()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        captured = self.ledger.record(request)
        if self._next >= len(self._steps):
            raise AssertionError(
                f"scenario {self.name!r} received unexpected {request.method} "
                f"{captured.canonical_path}"
            )
        step = self._steps[self._next]
        assert captured.operation is step.operation, (
            f"scenario {self.name!r} step {self._next}: expected operation "
            f"{step.operation.value}, observed {captured.operation}"
        )
        assert request.method == step.method, (
            f"scenario {self.name!r} step {self._next}: expected method "
            f"{step.method}, observed {request.method}"
        )
        assert captured.canonical_path == step.path, (
            f"scenario {self.name!r} step {self._next}: expected path "
            f"{step.path}, observed {captured.canonical_path}"
        )
        if step.expected_json is not None:
            assert captured.parsed_json == step.expected_json, (
                f"scenario {self.name!r} step {self._next}: submit JSON shape differed"
            )
        self._next += 1
        if step.entered_event is not None:
            step.entered_event.set()
        if step.release_event is not None:
            await step.release_event.wait()
        if step.exception is not None:
            raise step.exception
        if step.json_body is not None:
            return httpx.Response(
                step.status, json=step.json_body, headers=step.headers, request=request
            )
        return httpx.Response(
            step.status,
            content=step.body if step.body is not None else b"{}",
            headers=step.headers,
            request=request,
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def assert_complete(self) -> None:
        remaining = len(self._steps) - self._next
        assert remaining == 0, f"scenario {self.name!r} has {remaining} unconsumed step(s)"


class LoopbackRewriteTransport(httpx.AsyncBaseTransport):
    """Test-only byte transport mapping canonical requests to one loopback server."""

    def __init__(self, host: str, port: int) -> None:
        if host not in {"127.0.0.1", "::1"}:
            raise ValueError("Loopback transport requires a loopback literal")
        self._origin = f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"
        self._transport = httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https" and request.url.host == "openrouter.ai"
        body = await request.aread()
        rewritten = httpx.Request(
            request.method,
            f"{self._origin}{_canonical_path(request)}",
            headers=request.headers,
            content=body,
        )
        return await self._transport.handle_async_request(rewritten)

    async def aclose(self) -> None:
        await self._transport.aclose()


__all__ = (
    "CapturedRequest",
    "LoopbackRewriteTransport",
    "RequestLedger",
    "Scenario",
    "ScenarioStep",
)
