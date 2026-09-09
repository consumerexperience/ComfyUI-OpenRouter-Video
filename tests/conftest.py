"""Suite-wide deterministic external-network guard."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Generator
from typing import Any

import pytest


def _require_loopback(address: object) -> None:
    if not isinstance(address, tuple) or not address:
        raise AssertionError(f"real socket destination is not a loopback tuple: {address!r}")
    host = address[0]
    if not isinstance(host, str):
        raise AssertionError("real socket host is not a string")
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = host.lower() == "localhost"
    if not is_loopback:
        raise AssertionError(f"external network is forbidden in tests: {host}")


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Allow MockTransport and real loopback sockets, reject other socket destinations."""

    original_create = socket.create_connection
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def guarded_create(address: tuple[str, int], *args: Any, **kwargs: Any) -> socket.socket:
        _require_loopback(address)
        return original_create(address, *args, **kwargs)

    def guarded_connect(instance: socket.socket, address: object) -> Any:
        _require_loopback(address)
        return original_connect(instance, address)  # type: ignore[arg-type]

    def guarded_connect_ex(instance: socket.socket, address: object) -> int:
        _require_loopback(address)
        return original_connect_ex(instance, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "create_connection", guarded_create)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
