"""Minimal numbered Comfy API surface for repository-local adapter tests."""

# mypy: disable-error-code="attr-defined"

from __future__ import annotations

import sys
import types
from typing import Any


class _Field:
    def __init__(self, name: str | None = None, **options: object) -> None:
        self.name = name
        self.options = options


class _Schema:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class _NodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class _InputImpl:
    @staticmethod
    def VideoFromFile(path: str) -> tuple[str, str]:  # noqa: N802 - pinned host name
        return ("video", path)


def _install() -> None:
    if "comfy_api.v0_0_2" in sys.modules:
        return

    class RemoteOptions:
        def __init__(self, *, route: str, refresh_button: bool) -> None:
            self.route = route
            self.refresh_button = refresh_button

    class ComfyNode:
        hidden: object | None = None

    class ComfyExtension:
        pass

    class ComfyAPI:
        VERSION = "0.0.2"

    io = types.SimpleNamespace(
        ComfyNode=ComfyNode,
        Schema=_Schema,
        NodeOutput=_NodeOutput,
        RemoteOptions=RemoteOptions,
        Hidden=types.SimpleNamespace(unique_id="UNIQUE_ID"),
        Combo=types.SimpleNamespace(Input=_Field),
        String=types.SimpleNamespace(Input=_Field, Output=_Field),
        Int=types.SimpleNamespace(Input=_Field),
        Boolean=types.SimpleNamespace(Input=_Field),
        Video=types.SimpleNamespace(Output=_Field),
    )
    numbered = types.ModuleType("comfy_api.v0_0_2")
    numbered.ComfyAPI = ComfyAPI
    numbered.ComfyExtension = ComfyExtension
    numbered.IO = io
    numbered.InputImpl = _InputImpl
    package = types.ModuleType("comfy_api")
    package.v0_0_2 = numbered
    sys.modules["comfy_api"] = package
    sys.modules["comfy_api.v0_0_2"] = numbered


_install()
