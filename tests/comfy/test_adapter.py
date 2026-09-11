"""Host-independent acceptance tests for the thin ComfyUI adapter."""

# mypy: disable-error-code="arg-type,attr-defined"

from __future__ import annotations

import asyncio
import json
import sys
import threading
import types
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest


class _Field:
    def __init__(self, name: str | None = None, **options: object) -> None:
        self.name = name
        self.options = options


class _RemoteOptions:
    def __init__(self, *, route: str, refresh_button: bool) -> None:
        self.route = route
        self.refresh_button = refresh_button


class _Schema:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class _NodeOutput:
    def __init__(self, *values: object) -> None:
        self.values = values


class _ComfyNode:
    hidden: object | None = None


class _ComfyExtension:
    pass


class _ComfyAPI:
    VERSION = "0.0.2"


class _InputImpl:
    @staticmethod
    def VideoFromFile(path: str) -> tuple[str, str]:  # noqa: N802 - pinned host name
        return ("video", path)


def _install_fake_numbered_api() -> None:
    io = types.SimpleNamespace(
        ComfyNode=_ComfyNode,
        Schema=_Schema,
        NodeOutput=_NodeOutput,
        RemoteOptions=_RemoteOptions,
        Hidden=types.SimpleNamespace(unique_id="UNIQUE_ID"),
        Combo=types.SimpleNamespace(Input=_Field),
        String=types.SimpleNamespace(Input=_Field, Output=_Field),
        Int=types.SimpleNamespace(Input=_Field),
        Boolean=types.SimpleNamespace(Input=_Field),
        Video=types.SimpleNamespace(Output=_Field),
    )
    numbered = types.ModuleType("comfy_api.v0_0_2")
    numbered.ComfyAPI = _ComfyAPI
    numbered.ComfyExtension = _ComfyExtension
    numbered.IO = io
    numbered.InputImpl = _InputImpl
    package = types.ModuleType("comfy_api")
    package.v0_0_2 = numbered
    sys.modules.setdefault("comfy_api", package)
    sys.modules.setdefault("comfy_api.v0_0_2", numbered)


_install_fake_numbered_api()

from openrouter_video.comfy import compat, nodes, routes  # noqa: E402
from openrouter_video.comfy.video import VideoBridgeError, to_native_video  # noqa: E402
from openrouter_video.errors import RequestPolicyError  # noqa: E402
from openrouter_video.models import (  # noqa: E402
    GenerationResult,
    LocalLifecycleState,
    ModelCapabilities,
    VideoArtifact,
)


def _schema_inputs(schema: _Schema) -> dict[str, _Field]:
    return {field.name: field for field in schema.inputs}


def test_exact_two_independent_v3_schemas_and_privacy_surface() -> None:
    generate = nodes.OpenRouterVideoGenerate.define_schema()
    resume = nodes.OpenRouterVideoResume.define_schema()

    assert generate.node_id == "OpenRouterVideoGenerate"
    assert generate.display_name == "OpenRouter Video Generate"
    assert resume.node_id == "OpenRouterVideoResume"
    assert resume.display_name == "OpenRouter Video Resume"
    assert generate.category == resume.category == "OpenRouter/Video"
    assert generate.not_idempotent is resume.not_idempotent is True
    assert generate.outputs is not resume.outputs
    assert [item.name for item in generate.outputs] == [
        "VIDEO",
        "JOB_ID",
        "MODEL",
        "ACTUAL_COST_USD",
        "STATUS",
    ]
    assert [item.name for item in resume.outputs] == [
        "VIDEO",
        "JOB_ID",
        "MODEL",
        "ACTUAL_COST_USD",
        "STATUS",
    ]
    assert [item.name for item in generate.inputs] == [
        "model",
        "prompt",
        "duration",
        "resolution",
        "aspect_ratio",
        "size",
        "seed",
        "generate_audio",
        "first_frame_url",
        "last_frame_url",
    ]
    assert [item.name for item in resume.inputs] == ["job_id"]
    assert generate.hidden == resume.hidden == ["UNIQUE_ID"]
    first_token = nodes.OpenRouterVideoGenerate.fingerprint_inputs()
    second_token = nodes.OpenRouterVideoResume.fingerprint_inputs()
    assert isinstance(first_token, int)
    assert second_token == first_token + 1
    assert json.loads(json.dumps({"is_changed": second_token})) == {"is_changed": second_token}

    fields = _schema_inputs(generate)
    assert fields["model"].options["options"] == []
    remote = fields["model"].options["remote"]
    assert remote.route == "/openrouter-video/v1/models"
    assert remote.refresh_button is True
    assert fields["prompt"].options["multiline"] is True
    assert fields["duration"].options["default"] == 0
    assert fields["generate_audio"].options["default"] is False
    serialized = repr((generate.__dict__, resume.__dict__)).lower()
    for forbidden in (
        "api_key",
        "authorization",
        "base_url",
        "referer",
        "arbitrary",
        "operation_id",
        "workflow_id",
        "session_id",
        "user_id",
    ):
        assert forbidden not in serialized


def test_generate_normalizes_once_and_returns_exact_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, str | None]] = []

    class Runtime:
        async def generate(self, request: object, node_id: str | None) -> GenerationResult:
            calls.append((request, node_id))
            return GenerationResult(
                LocalLifecycleState.DONE,
                "job-1",
                model="vendor/model",
                actual_cost_usd=Decimal("0.2500"),
                artifact=VideoArtifact(Path("ignored.mp4"), "video/mp4", 10),
            )

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "native-video")
    nodes.OpenRouterVideoGenerate.hidden = types.SimpleNamespace(unique_id="node-7")

    output = asyncio.run(
        nodes.OpenRouterVideoGenerate.execute(
            " vendor/model ",
            "private prompt",
            duration=5,
            resolution=" 720p ",
            aspect_ratio=" ",
            size=" 1280x720 ",
            seed=" 42 ",
            generate_audio=True,
            first_frame_url=" https://example.invalid/first.png ",
            last_frame_url=" ",
        )
    )

    assert len(calls) == 1
    request, node_id = calls[0]
    assert node_id == "node-7"
    assert request.model == "vendor/model"
    assert request.duration == 5
    assert request.resolution == "720p"
    assert request.aspect_ratio is None
    assert request.size == "1280x720"
    assert request.seed == 42
    assert request.generate_audio is True
    assert request.first_frame is not None
    assert request.first_frame.url == "https://example.invalid/first.png"
    assert request.last_frame is None
    assert output.values == (
        "native-video",
        "job-1",
        "vendor/model",
        "0.2500",
        "DONE",
    )


@pytest.mark.parametrize("duration", (-1, True, 1.5))
def test_generate_rejects_invalid_duration_without_runtime_call(
    duration: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        nodes,
        "get_runtime",
        lambda: pytest.fail("runtime must not be created for invalid duration"),
    )
    with pytest.raises(nodes.AdapterExecutionError, match="UNSUPPORTED_PARAMETER"):
        asyncio.run(nodes.OpenRouterVideoGenerate.execute("vendor/model", "prompt", duration))


@pytest.mark.parametrize("seed", ("1.2", "not-a-number"))
def test_generate_rejects_invalid_seed(seed: str) -> None:
    with pytest.raises(nodes.AdapterExecutionError, match="UNSUPPORTED_PARAMETER"):
        asyncio.run(nodes.OpenRouterVideoGenerate.execute("vendor/model", "prompt", seed=seed))


def test_resume_strips_job_id_and_has_no_submit_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Runtime:
        async def resume(self, job_id: str, _: str | None) -> GenerationResult:
            calls.append(job_id)
            return GenerationResult(
                LocalLifecycleState.DONE,
                job_id,
                artifact=VideoArtifact(Path("ignored.webm"), "video/webm", 10),
            )

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "native-video")
    output = asyncio.run(nodes.OpenRouterVideoResume.execute(" job-9 "))

    assert calls == ["job-9"]
    assert output.values == ("native-video", "job-9", "", "", "DONE")
    with pytest.raises(nodes.AdapterExecutionError, match="job_id"):
        asyncio.run(nodes.OpenRouterVideoResume.execute("   "))


def test_video_bridge_rejects_missing_and_outside_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    artifact_path = output / "video.mp4"
    artifact_path.write_bytes(b"video")
    monkeypatch.setattr(compat, "output_directory", lambda: output)
    monkeypatch.setattr(compat, "video_from_file", lambda path: ("native", path))

    artifact = VideoArtifact(artifact_path, "video/mp4", 5)
    assert to_native_video(artifact) == ("native", artifact_path)
    artifact_path.unlink()
    with pytest.raises(VideoBridgeError, match="unavailable"):
        to_native_video(artifact)

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    with pytest.raises(VideoBridgeError, match="unavailable"):
        to_native_video(VideoArtifact(outside, "video/mp4", 5))


def test_route_registration_is_thread_safe_lazy_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple[str, object]] = []

    class RouteTable:
        def get(self, path: str) -> Any:
            def decorator(handler: object) -> object:
                registered.append((path, handler))
                return handler

            return decorator

    server = types.SimpleNamespace(routes=RouteTable())
    monkeypatch.setattr(compat, "prompt_server", lambda: server)
    monkeypatch.setattr(
        routes,
        "get_runtime",
        lambda: pytest.fail("registration must stay lazy"),
    )

    threads = [threading.Thread(target=routes.register_routes) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert registered == [("/openrouter-video/v1/models", routes._models_handler)]


def test_models_route_returns_only_sorted_valid_ids_and_sanitized_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[tuple[object, int]] = []

    def response(payload: object, *, status: int) -> tuple[object, int]:
        responses.append((payload, status))
        return payload, status

    class Runtime:
        async def catalog(self) -> object:
            return types.SimpleNamespace(
                models=(
                    ModelCapabilities("z/model"),
                    ModelCapabilities("a/model"),
                )
            )

    monkeypatch.setattr(compat, "json_response", response)
    monkeypatch.setattr(routes, "get_runtime", Runtime)
    assert asyncio.run(routes._models_handler(None)) == (["a/model", "z/model"], 200)

    class InvalidRuntime:
        async def catalog(self) -> object:
            return types.SimpleNamespace(models=(ModelCapabilities(""),))

    monkeypatch.setattr(routes, "get_runtime", InvalidRuntime)
    assert asyncio.run(routes._models_handler(None)) == (
        {"error": "model_catalog_internal_error"},
        500,
    )

    class FailedRuntime:
        async def catalog(self) -> object:
            raise RequestPolicyError("secret prompt and headers")

    monkeypatch.setattr(routes, "get_runtime", FailedRuntime)
    assert asyncio.run(routes._models_handler(None)) == (
        {"error": "model_catalog_unavailable"},
        503,
    )
    assert "secret" not in repr(responses[-1])
