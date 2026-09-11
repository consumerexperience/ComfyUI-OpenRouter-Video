"""Pinned ComfyUI DEV compatibility probe; run with its own CPU interpreter."""

# mypy: ignore-errors

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


class _Server:
    client_id: str | None = None
    last_node_id: str | None = None

    def send_sync(self, *_: object, **__: object) -> None:
        return None


def _write_video(path: Path, *, container_format: str, codec: str) -> None:
    import av
    import numpy as np

    container = av.open(str(path), "w", format=container_format)
    stream = container.add_stream(codec, rate=1)
    stream.width = 16
    stream.height = 16
    stream.pix_fmt = "yuv420p"
    frame = av.VideoFrame.from_ndarray(
        np.zeros((16, 16, 3), dtype=np.uint8),
        format="rgb24",
    )
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _prompt(node_type: str, inputs: dict[str, object]) -> dict[str, object]:
    return {"1": {"class_type": node_type, "inputs": inputs}}


def main() -> None:
    import comfy.options

    comfy.options.enable_args_parsing()

    import execution
    import nodes as comfy_nodes
    from comfy_api.v0_0_2 import ComfyAPI, InputImpl
    from comfy_extras.nodes_video import GetVideoComponents

    from openrouter_video.comfy import compat
    from openrouter_video.comfy import nodes as adapter_nodes
    from openrouter_video.comfy.video import VideoBridgeError, to_native_video
    from openrouter_video.models import (
        GenerationResult,
        LocalLifecycleState,
        VideoArtifact,
    )

    assert ComfyAPI.VERSION == "0.0.2"
    compat.validate_host_api()
    generate_schema = adapter_nodes.OpenRouterVideoGenerate.define_schema()
    resume_schema = adapter_nodes.OpenRouterVideoResume.define_schema()
    assert generate_schema.node_id == "OpenRouterVideoGenerate"
    assert resume_schema.node_id == "OpenRouterVideoResume"
    assert generate_schema.outputs is not resume_schema.outputs
    assert [value.id for value in generate_schema.outputs] == [
        "VIDEO",
        "JOB_ID",
        "MODEL",
        "ACTUAL_COST_USD",
        "STATUS",
    ]

    metadata = json.dumps(
        {
            "generate": adapter_nodes.OpenRouterVideoGenerate.GET_NODE_INFO_V1(),
            "resume": adapter_nodes.OpenRouterVideoResume.GET_NODE_INFO_V1(),
        },
        allow_nan=False,
    ).lower()
    for forbidden in (
        "api_key",
        "authorization",
        "operation_id",
        "workflow_id",
        "session_id",
        "referer",
    ):
        assert forbidden not in metadata

    class MockRuntime:
        def __init__(self) -> None:
            self.generate_calls = 0
            self.resume_calls = 0

        async def generate(self, request: Any, node_id: str | None) -> GenerationResult:
            del node_id
            self.generate_calls += 1
            return GenerationResult(
                LocalLifecycleState.DONE,
                f"job-{self.generate_calls}",
                model=request.model,
                artifact=VideoArtifact(Path("mock.mp4"), "video/mp4", 1),
            )

        async def resume(self, job_id: str, node_id: str | None) -> GenerationResult:
            del node_id
            self.resume_calls += 1
            return GenerationResult(
                LocalLifecycleState.DONE,
                job_id,
                artifact=VideoArtifact(Path("mock.mp4"), "video/mp4", 1),
            )

    mock_runtime = MockRuntime()
    adapter_nodes.get_runtime = lambda: mock_runtime
    adapter_nodes.to_native_video = lambda _: object()
    comfy_nodes.NODE_CLASS_MAPPINGS["OpenRouterVideoGenerate"] = (
        adapter_nodes.OpenRouterVideoGenerate
    )
    comfy_nodes.NODE_CLASS_MAPPINGS["OpenRouterVideoResume"] = adapter_nodes.OpenRouterVideoResume
    executor = execution.PromptExecutor(
        _Server(),
        cache_type=False,
        cache_args={"lru": 0, "ram": 0.0, "ram_inactive": 0.0},
    )
    for prompt_id in ("generate-1", "generate-2"):
        executor.execute(
            _prompt(
                "OpenRouterVideoGenerate",
                {"model": "vendor/model", "prompt": "test-only prompt"},
            ),
            prompt_id,
            {},
            ["1"],
        )
        assert executor.success
    assert mock_runtime.generate_calls == 2

    for prompt_id in ("resume-1", "resume-2"):
        executor.execute(
            _prompt("OpenRouterVideoResume", {"job_id": "job-existing"}),
            prompt_id,
            {},
            ["1"],
        )
        assert executor.success
    assert mock_runtime.resume_calls == 2

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        compat.output_directory = lambda: root
        for name, container_format, codec, media_type in (
            ("tiny.mp4", "mp4", "mpeg4", "video/mp4"),
            ("tiny.webm", "webm", "libvpx", "video/webm"),
        ):
            path = root / name
            _write_video(path, container_format=container_format, codec=codec)
            artifact = VideoArtifact(path, media_type, path.stat().st_size)
            native = to_native_video(artifact)
            assert isinstance(native, InputImpl.VideoFromFile)
            components = GetVideoComponents.execute(native).result
            assert components[0].shape == (1, 16, 16, 3)
            path.unlink()
            try:
                to_native_video(artifact)
            except VideoBridgeError as error:
                assert str(error) == "Generated video artifact is unavailable."
            else:
                raise AssertionError("deleted artifact must fail closed")


if __name__ == "__main__":
    main()
