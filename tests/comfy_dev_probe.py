"""Pinned ComfyUI DEV compatibility probe; run with its own CPU interpreter."""

# mypy: ignore-errors

from __future__ import annotations

import asyncio
import copy
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
    image_schema = adapter_nodes.OpenRouterVideoImageReference.define_schema()
    video_schema = adapter_nodes.OpenRouterVideoVideoReference.define_schema()
    collection_schema = adapter_nodes.OpenRouterVideoReferenceCollection.define_schema()
    assert generate_schema.node_id == "OpenRouterVideoGenerate"
    assert resume_schema.node_id == "OpenRouterVideoResume"
    assert image_schema.node_id == "OpenRouterVideoImageReference"
    assert video_schema.node_id == "OpenRouterVideoVideoReference"
    assert collection_schema.node_id == "OpenRouterVideoReferenceCollection"
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
            "image_reference": adapter_nodes.OpenRouterVideoImageReference.GET_NODE_INFO_V1(),
            "video_reference": adapter_nodes.OpenRouterVideoVideoReference.GET_NODE_INFO_V1(),
            "reference_collection": (
                adapter_nodes.OpenRouterVideoReferenceCollection.GET_NODE_INFO_V1()
            ),
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
            self.requests: list[Any] = []

        async def generate(self, request: Any, node_id: str | None) -> GenerationResult:
            del node_id
            self.generate_calls += 1
            self.requests.append(request)
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
    comfy_nodes.NODE_CLASS_MAPPINGS["OpenRouterVideoImageReference"] = (
        adapter_nodes.OpenRouterVideoImageReference
    )
    comfy_nodes.NODE_CLASS_MAPPINGS["OpenRouterVideoVideoReference"] = (
        adapter_nodes.OpenRouterVideoVideoReference
    )
    comfy_nodes.NODE_CLASS_MAPPINGS["OpenRouterVideoReferenceCollection"] = (
        adapter_nodes.OpenRouterVideoReferenceCollection
    )
    validation_prompt = _prompt(
        "OpenRouterVideoGenerate",
        {
            "model": "vendor/model",
            "prompt": "test-only prompt",
            "duration": 0,
            "resolution": "",
            "aspect_ratio": "",
            "size": "",
            "seed": "",
            "generate_audio": False,
            "first_frame_url": "",
            "last_frame_url": "",
        },
    )
    invalid = asyncio.run(execution.validate_inputs("validation-empty", validation_prompt, "1", {}))
    assert invalid[0] is False
    assert any(error["type"] == "value_not_in_list" for error in invalid[1])
    compat.cache_model_options(("vendor/model",))
    valid = asyncio.run(
        execution.validate_inputs("validation-catalogue", validation_prompt, "1", {})
    )
    assert valid[0] is True, valid[1]
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

    reference_prompt = {
        "1": {
            "class_type": "OpenRouterVideoImageReference",
            "inputs": {"url": "https://assets.example/a.png"},
        },
        "2": {
            "class_type": "OpenRouterVideoVideoReference",
            "inputs": {"url": "https://assets.example/b.mp4"},
        },
        "3": {
            "class_type": "OpenRouterVideoReferenceCollection",
            "inputs": {
                "references.reference_2": ["2", 0],
                "references.reference_0": ["1", 0],
                "references.reference_1": ["1", 0],
            },
        },
        "4": {
            "class_type": "OpenRouterVideoGenerate",
            "inputs": {
                "model": "vendor/model",
                "prompt": "test-only prompt",
                "duration": 0,
                "resolution": "",
                "aspect_ratio": "",
                "size": "",
                "seed": "",
                "generate_audio": False,
                "first_frame_url": "",
                "last_frame_url": "",
                "input_references": ["3", 0],
            },
        },
    }
    valid_references = asyncio.run(
        execution.validate_inputs("validation-references", copy.deepcopy(reference_prompt), "4", {})
    )
    assert valid_references[0] is True, valid_references[1]
    for prompt_id in ("references-1", "references-2"):
        executor.execute(copy.deepcopy(reference_prompt), prompt_id, {}, ["4"])
        assert executor.success
    reference_requests = mock_runtime.requests[2:]
    assert len(reference_requests) == 2, len(reference_requests)
    for request in reference_requests:
        assert request.input_references is not None
        assert [reference.kind.value for reference in request.input_references.references] == [
            "image",
            "image",
            "video",
        ]
        assert request.input_references.references[0] is request.input_references.references[1]

    one_reference_prompt = copy.deepcopy(reference_prompt)
    del one_reference_prompt["1"]
    one_reference_prompt["3"]["inputs"] = {"references.reference_0": ["2", 0]}
    one_valid = asyncio.run(
        execution.validate_inputs(
            "validation-one-reference", copy.deepcopy(one_reference_prompt), "4", {}
        )
    )
    assert one_valid[0] is True, one_valid[1]
    executor.execute(copy.deepcopy(one_reference_prompt), "references-one", {}, ["4"])
    assert executor.success
    one_collection = mock_runtime.requests[-1].input_references
    assert one_collection is not None
    assert [reference.kind.value for reference in one_collection.references] == ["video"]

    empty_collection_prompt = {
        "3": {
            "class_type": "OpenRouterVideoReferenceCollection",
            "inputs": {},
        },
        "4": {
            "class_type": "OpenRouterVideoGenerate",
            "inputs": {
                "model": "vendor/model",
                "prompt": "test-only prompt",
                "duration": 0,
                "resolution": "",
                "aspect_ratio": "",
                "size": "",
                "seed": "",
                "generate_audio": False,
                "first_frame_url": "",
                "last_frame_url": "",
                "input_references": ["3", 0],
            },
        },
    }
    empty_valid = asyncio.run(
        execution.validate_inputs(
            "validation-empty-collection", copy.deepcopy(empty_collection_prompt), "4", {}
        )
    )
    assert empty_valid[0] is True, empty_valid[1]
    executor.execute(copy.deepcopy(empty_collection_prompt), "references-empty", {}, ["4"])
    assert executor.success
    assert mock_runtime.requests[-1].input_references.references == ()

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
