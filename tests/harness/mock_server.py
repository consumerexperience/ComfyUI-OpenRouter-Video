"""Localhost-only scripted HTTP server for testing future transport boundaries."""

from __future__ import annotations

import queue
import socket
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import cast

_REDACTED_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})
_MAX_REQUEST_BODY = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    """One deterministic response or connection fault."""

    status: int = 200
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b"{}"
    disconnect_after_request: bool = False
    disconnect_after_headers: bool = False
    disconnect_after_body_bytes: int | None = None
    delay_seconds: float = 0.0
    expected_method: str | None = None
    expected_path: str | None = None


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """A sanitized request captured by the local harness."""

    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes = field(repr=False)


class _HarnessState:
    def __init__(self, plans: list[ResponsePlan]) -> None:
        self.plans: queue.Queue[ResponsePlan] = queue.Queue()
        for plan in plans:
            self.plans.put(plan)
        self.requests: list[RequestRecord] = []
        self.errors: list[str] = []
        self.lock = threading.Lock()
        self.request_received = threading.Event()

    def next_plan(self, request: RequestRecord) -> ResponsePlan:
        try:
            plan = self.plans.get_nowait()
        except queue.Empty:
            self.errors.append(f"unexpected request: {request.method} {request.path}")
            return ResponsePlan(status=500, body=b"unexpected request")
        if plan.expected_method is not None and request.method != plan.expected_method:
            self.errors.append(f"expected method {plan.expected_method}, observed {request.method}")
        if plan.expected_path is not None and request.path != plan.expected_path:
            self.errors.append(f"expected path {plan.expected_path}, observed {request.path}")
        return plan

    def record(self, request: RequestRecord) -> None:
        with self.lock:
            self.requests.append(request)
        self.request_received.set()


class _HarnessHandler(BaseHTTPRequestHandler):
    server: _HarnessHttpServer

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request()

    def do_POST(self) -> None:  # noqa: N802
        self._handle_request()

    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _handle_request(self) -> None:
        length = min(int(self.headers.get("Content-Length", "0")), _MAX_REQUEST_BODY)
        body = self.rfile.read(length) if length else b""
        headers = {
            key: "[REDACTED]" if key.lower() in _REDACTED_HEADERS else value
            for key, value in self.headers.items()
        }
        request = RequestRecord(method=self.command, path=self.path, headers=headers, body=body)
        self.server.state.record(request)
        plan = self.server.state.next_plan(request)
        if plan.delay_seconds:
            time.sleep(plan.delay_seconds)
        if plan.disconnect_after_request:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.send_response(plan.status)
        for key, value in plan.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(plan.body)))
        self.end_headers()
        if plan.disconnect_after_headers:
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        if plan.disconnect_after_body_bytes is not None:
            self.wfile.write(plan.body[: plan.disconnect_after_body_bytes])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        self.wfile.write(plan.body)


class _HarnessHttpServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def __init__(self, state: _HarnessState) -> None:
        super().__init__(("127.0.0.1", 0), _HarnessHandler)
        self.state = state


class LocalFaultServer:
    """Context-managed localhost server with a scripted response queue."""

    def __init__(self, plans: list[ResponsePlan] | None = None) -> None:
        self._state = _HarnessState(plans or [])
        self._server: _HarnessHttpServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        """Return the bound loopback host and ephemeral port."""
        if self._server is None:
            raise RuntimeError("Harness server is not running")
        host, port = cast(tuple[str, int], self._server.server_address)
        return str(host), int(port)

    @property
    def requests(self) -> tuple[RequestRecord, ...]:
        """Return an immutable snapshot of sanitized requests."""
        with self._state.lock:
            return tuple(self._state.requests)

    @property
    def post_count(self) -> int:
        """Count simulated POST observations without assigning product semantics."""
        return sum(request.method == "POST" for request in self.requests)

    @property
    def generation_submit_count(self) -> int:
        """Count only simulated paid-generation endpoint observations."""
        return sum(
            request.method == "POST" and request.path == "/api/v1/videos"
            for request in self.requests
        )

    def wait_until_request_received(self, timeout: float = 2.0) -> bool:
        """Synchronize deterministically with the first fully captured request."""
        return self._state.request_received.wait(timeout)

    def assert_complete(self) -> None:
        """Fail for mismatches, unexpected calls, or unconsumed response plans."""
        errors = tuple(self._state.errors)
        remaining = self._state.plans.qsize()
        assert not errors, "; ".join(errors)
        assert remaining == 0, f"LocalFaultServer has {remaining} unconsumed response plan(s)"

    def __enter__(self) -> LocalFaultServer:
        self._server = _HarnessHttpServer(self._state)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        had_exception = exc_type is not None
        del exc_value, traceback
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        if not had_exception:
            self.assert_complete()

    def __iter__(self) -> Iterator[RequestRecord]:
        return iter(self.requests)
