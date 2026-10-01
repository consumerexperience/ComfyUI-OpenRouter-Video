"""Host-independent acceptance tests for the thin ComfyUI adapter."""

# mypy: disable-error-code="arg-type,attr-defined"

from __future__ import annotations

import asyncio
import json
import sys
import threading
import types
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest


class _Field:
    def __init__(self, name: str | None = None, **options: object) -> None:
        self.name = name
        self.options = options


class _RemoteOptions:
    def __init__(self, *, route: str, refresh_button: bool, control_after_refresh: str) -> None:
        self.route = route
        self.refresh_button = refresh_button
        self.control_after_refresh = control_after_refresh


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
    class Autogrow:
        class TemplatePrefix:
            def __init__(self, *, input: object, prefix: str, min: int, max: int) -> None:
                self.input = input
                self.prefix = prefix
                self.min = min
                self.max = max

        Input = _Field

    def custom(_: str) -> object:
        return types.SimpleNamespace(Input=_Field, Output=_Field)

    io = types.SimpleNamespace(
        ComfyNode=_ComfyNode,
        Schema=_Schema,
        NodeOutput=_NodeOutput,
        RemoteOptions=_RemoteOptions,
        Hidden=types.SimpleNamespace(unique_id="UNIQUE_ID"),
        Combo=types.SimpleNamespace(Input=_Field),
        String=types.SimpleNamespace(Input=_Field, Output=_Field),
        Int=types.SimpleNamespace(Input=_Field),
        ControlAfterGenerate=types.SimpleNamespace(
            fixed="fixed", increment="increment", decrement="decrement", randomize="randomize"
        ),
        NumberDisplay=types.SimpleNamespace(number="number", slider="slider"),
        Boolean=types.SimpleNamespace(Input=_Field),
        Video=types.SimpleNamespace(Output=_Field),
        Autogrow=Autogrow,
        Custom=custom,
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
from openrouter_video.comfy.extension import OpenRouterVideoExtension  # noqa: E402
from openrouter_video.comfy.video import VideoBridgeError, to_native_video  # noqa: E402
from openrouter_video.errors import RequestPolicyError  # noqa: E402
from openrouter_video.execution_hooks import ExecutionPhase  # noqa: E402
from openrouter_video.models import (  # noqa: E402
    FrameType,
    GenerationResult,
    InputReference,
    InputReferenceCapabilities,
    InputReferenceCollection,
    InputReferenceKind,
    LocalLifecycleState,
    ModelCapabilities,
    PricingEvidence,
    PricingSku,
    VideoArtifact,
)
from openrouter_video.pricing import EstimateAvailability, EstimateResult  # noqa: E402


def _schema_inputs(schema: _Schema) -> dict[str, _Field]:
    return {field.name: field for field in schema.inputs}


def test_generate_resume_v3_schemas_and_privacy_surface() -> None:
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
        "inference_method",
        "prompt",
        "resolution",
        "aspect_ratio",
        "duration",
        "size",
        "seed",
        "generate_audio",
        "first_frame_url",
        "last_frame_url",
        "first_frame",
        "last_frame",
        "source_video",
        "direct_references",
        "input_references",
    ]
    assert [item.name for item in resume.inputs] == ["job_id"]
    assert generate.hidden == resume.hidden == ["UNIQUE_ID"]
    first_token = nodes.OpenRouterVideoGenerate.fingerprint_inputs()
    second_token = nodes.OpenRouterVideoResume.fingerprint_inputs()
    assert isinstance(first_token, int)
    assert second_token == first_token + 1
    assert json.loads(json.dumps({"is_changed": second_token})) == {"is_changed": second_token}

    fields = _schema_inputs(generate)
    assert fields["model"].options["options"] == ["SELECT MODEL"]
    assert fields["model"].options["default"] == "SELECT MODEL"
    assert "remote" not in fields["model"].options
    assert fields["prompt"].options["multiline"] is True
    assert fields["duration"].options["default"] == 0
    assert fields["seed"].options["default"] == -1
    assert fields["seed"].options["control_after_generate"] == "randomize"
    assert fields["generate_audio"].options["default"] is False
    direct = fields["direct_references"]
    assert direct.options["optional"] is True
    assert direct.options["template"].min == 0
    assert direct.options["template"].max == 100
    assert fields["input_references"].options["advanced"] is True
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


def test_extension_registers_exact_phase8_node_set() -> None:
    registered = asyncio.run(OpenRouterVideoExtension().get_node_list())

    assert registered == [
        nodes.OpenRouterVideoImageReference,
        nodes.OpenRouterVideoVideoReference,
        nodes.OpenRouterVideoAudioReference,
        nodes.OpenRouterVideoReferenceCollection,
        nodes.OpenRouterVideoGenerate,
        nodes.OpenRouterVideoResume,
    ]


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
    assert request.input_references is None
    assert output.values == (
        "native-video",
        "job-1",
        "vendor/model",
        "0.2500",
        "DONE",
    )


def test_native_video_and_done_progress_are_truthful_and_ordered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phases: list[tuple[ExecutionPhase, str | None]] = []

    async def report(phase: ExecutionPhase, node_id: str | None) -> None:
        phases.append((phase, node_id))

    monkeypatch.setattr(compat, "report_phase", report)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "native-video")
    result = GenerationResult(
        LocalLifecycleState.DONE,
        "job-progress",
        artifact=VideoArtifact(Path("ignored.mp4"), "video/mp4", 10),
    )

    output = asyncio.run(nodes._node_output(result, "node-progress"))

    assert output.values[0] == "native-video"
    assert phases == [
        (ExecutionPhase.NATIVE_VIDEO, "node-progress"),
        (ExecutionPhase.DONE, "node-progress"),
    ]


def test_reference_nodes_preserve_autogrow_positions_and_duplicates() -> None:
    image = nodes.OpenRouterVideoImageReference.execute(" https://assets.example/a.png ")
    video = nodes.OpenRouterVideoVideoReference.execute(" https://assets.example/b.mp4 ")
    image_reference = image.values[0]
    video_reference = video.values[0]

    assert image_reference == InputReference(
        InputReferenceKind.IMAGE, "https://assets.example/a.png"
    )
    assert video_reference == InputReference(
        InputReferenceKind.VIDEO, "https://assets.example/b.mp4"
    )
    output = nodes.OpenRouterVideoReferenceCollection.execute(
        {
            "reference_2": video_reference,
            "reference_0": image_reference,
            "reference_1": image_reference,
        }
    )
    assert output.values == (
        InputReferenceCollection((image_reference, image_reference, video_reference)),
    )

    schema = nodes.OpenRouterVideoReferenceCollection.define_schema()
    field = schema.inputs[0]
    template = field.options["template"]
    assert field.name == "references"
    assert field.options["optional"] is True
    assert template.min == 0
    assert template.max == 100


def test_generate_bridges_typed_reference_collection(monkeypatch: pytest.MonkeyPatch) -> None:
    collection = InputReferenceCollection(
        (InputReference(InputReferenceKind.VIDEO, "https://assets.example/reference.mp4"),)
    )
    captured: list[object] = []

    class Runtime:
        async def generate(self, request: object, _: str | None) -> GenerationResult:
            captured.append(request)
            return GenerationResult(
                LocalLifecycleState.DONE,
                "job-reference",
                artifact=VideoArtifact(Path("ignored.mp4"), "video/mp4", 10),
            )

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "native-video")
    asyncio.run(
        nodes.OpenRouterVideoGenerate.execute("vendor/model", "prompt", input_references=collection)
    )
    assert captured[0].input_references is collection


def test_audio_helper_and_v2v_source_role_bridge_to_core(monkeypatch: pytest.MonkeyPatch) -> None:
    source = nodes.OpenRouterVideoVideoReference.execute(
        "https://assets.example/source.mp4"
    ).values[0]
    audio = nodes.OpenRouterVideoAudioReference.execute("https://assets.example/guide.mp3").values[
        0
    ]
    captured: list[object] = []

    class Runtime:
        async def generate(self, request: object, _: str | None) -> GenerationResult:
            captured.append(request)
            return GenerationResult(
                LocalLifecycleState.DONE,
                "job-v2v",
                artifact=VideoArtifact(Path("ignored.mp4"), "video/mp4", 10),
            )

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "native-video")
    asyncio.run(
        nodes.OpenRouterVideoGenerate.execute(
            "vendor/model",
            "prompt",
            inference_method="V2V_EDIT",
            source_video=source,
            direct_references={"reference_0": audio},
        )
    )

    assert captured[0].inference_method.value == "V2V_EDIT"
    assert captured[0].source_video == source
    assert captured[0].input_references == InputReferenceCollection((audio,))


def test_generate_bridges_direct_ordered_references_and_rejects_mixed_topologies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = InputReference(InputReferenceKind.IMAGE, "https://assets.example/a.png")
    video = InputReference(InputReferenceKind.VIDEO, "https://assets.example/b.mp4")
    captured: list[object] = []

    class Runtime:
        async def generate(self, request: object, _: str | None) -> GenerationResult:
            captured.append(request)
            return GenerationResult(
                LocalLifecycleState.DONE,
                "job-direct-references",
                artifact=VideoArtifact(Path("ignored.mp4"), "video/mp4", 10),
            )

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    monkeypatch.setattr(nodes, "to_native_video", lambda _: "native-video")
    asyncio.run(
        nodes.OpenRouterVideoGenerate.execute(
            "vendor/model",
            "prompt",
            direct_references={
                "reference_2": video,
                "reference_0": image,
                "reference_1": image,
            },
        )
    )
    assert captured[0].input_references == InputReferenceCollection((image, image, video))

    with pytest.raises(nodes.AdapterExecutionError, match="not both"):
        asyncio.run(
            nodes.OpenRouterVideoGenerate.execute(
                "vendor/model",
                "prompt",
                direct_references={"reference_0": image},
                input_references=InputReferenceCollection((video,)),
            )
        )


def test_native_image_normalizes_into_existing_frame_and_ordered_reference_roles(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    native = object()
    data_url = "data:image/png;base64,private-image-canary"
    monkeypatch.setattr(
        nodes, "to_image_data_url", lambda value: data_url if value is native else ""
    )
    captured: list[object] = []

    class Runtime:
        async def generate(self, request: object, _: str | None) -> GenerationResult:
            captured.append(request)
            return GenerationResult(LocalLifecycleState.DONE, "job-native-image")

    monkeypatch.setattr(nodes, "get_runtime", Runtime)
    with pytest.raises(nodes.AdapterExecutionError):
        asyncio.run(
            nodes.OpenRouterVideoGenerate.execute(
                "vendor/model",
                "prompt",
                inference_method="FLF2V",
                first_frame=native,
                last_frame=InputReference(
                    InputReferenceKind.IMAGE, "https://assets.example/last.png"
                ),
            )
        )
    assert captured[0].first_frame.url == data_url
    assert captured[0].last_frame.url == "https://assets.example/last.png"

    with pytest.raises(nodes.AdapterExecutionError):
        asyncio.run(
            nodes.OpenRouterVideoGenerate.execute(
                "vendor/model",
                "prompt",
                inference_method="MI2V",
                direct_references={
                    "reference_2": native,
                    "reference_0": InputReference(
                        InputReferenceKind.IMAGE, "https://assets.example/first.png"
                    ),
                    "reference_1": native,
                },
            )
        )
    assert [item.url for item in captured[1].input_references.references] == [
        "https://assets.example/first.png",
        data_url,
        data_url,
    ]
    assert data_url not in caplog.text
    assert "api_key" not in caplog.text.lower()


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


def test_unresolved_model_is_rejected_before_runtime_and_seed_omission_migrates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        nodes,
        "get_runtime",
        lambda: pytest.fail("unresolved model must not create the runtime"),
    )
    with pytest.raises(nodes.AdapterExecutionError, match="select a model"):
        asyncio.run(nodes.OpenRouterVideoGenerate.execute("SELECT MODEL", "prompt"))

    assert nodes._seed(-1) is None
    assert nodes._seed(42) == 42
    assert nodes._seed("42") == 42
    result = nodes.OpenRouterVideoGenerate.validate_inputs("SELECT MODEL")
    assert isinstance(result, str)
    assert nodes.OpenRouterVideoGenerate.validate_inputs("vendor/model") is True


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


def test_comfy_owned_state_and_output_paths_are_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "user"
    output = tmp_path / "output"
    folder_paths = types.SimpleNamespace(
        get_user_directory=lambda: str(user),
        get_output_directory=lambda: str(output),
    )
    monkeypatch.setitem(sys.modules, "folder_paths", folder_paths)

    assert compat.state_database_path() == user / "openrouter-video" / "state" / "jobs.sqlite3"
    assert compat.output_directory() == output / "openrouter-video"


def test_route_registration_is_thread_safe_lazy_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[tuple[str, object]] = []

    class RouteTable:
        def _register(self, method: str, path: str) -> Any:
            def decorator(handler: object) -> object:
                registered.append((f"{method} {path}", handler))
                return handler

            return decorator

        def get(self, path: str) -> Any:
            return self._register("GET", path)

        def post(self, path: str) -> Any:
            return self._register("POST", path)

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

    assert registered == [
        ("GET /openrouter-video/v1/health", routes._health_handler),
        ("GET /openrouter-video/v1/models", routes._models_handler),
        ("GET /openrouter-video/v1/ui-capabilities", routes._ui_capabilities_handler),
        ("POST /openrouter-video/v1/cost-estimate", routes._cost_estimate_handler),
    ]


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
    assert asyncio.run(routes._models_handler(None)) == (
        ["SELECT MODEL", "a/model", "z/model"],
        200,
    )
    generate = nodes.OpenRouterVideoGenerate.define_schema()
    assert _schema_inputs(generate)["model"].options["options"] == ["SELECT MODEL"]

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


def test_ui_capabilities_route_is_capability_only_and_preserves_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = datetime(2026, 9, 26, 19, 54, 44, tzinfo=timezone.utc)

    class Runtime:
        async def effective_catalog(self) -> object:
            return types.SimpleNamespace(
                observed_at=observed,
                models=(
                    ModelCapabilities(
                        "vendor/model",
                        name="Model",
                        supported_durations=(4, 5, 8),
                        supported_resolutions=("480p", "768p"),
                        supported_aspect_ratios=("16:9", "5:4"),
                        supported_frame_types=frozenset({FrameType.FIRST}),
                        supports_seed=None,
                        generate_audio=False,
                        input_reference_capabilities=InputReferenceCapabilities(
                            reference_kinds=frozenset(
                                {InputReferenceKind.IMAGE, InputReferenceKind.VIDEO}
                            ),
                            max_reference_count=50,
                            mixed_reference_kinds=True,
                        ),
                        pricing_evidence=PricingEvidence(
                            (PricingSku("generate", Decimal("0.42")),)
                        ),
                    ),
                ),
            )

    monkeypatch.setattr(routes, "get_runtime", Runtime)
    monkeypatch.setattr(
        compat,
        "json_response",
        lambda payload, *, status: (payload, status),
    )

    payload, status = asyncio.run(routes._ui_capabilities_handler(None))

    assert status == 200
    assert payload["observed_at"] == observed.isoformat()
    assert payload["ui_contract_version"] == 4
    assert len(payload["catalogue_revision"]) == 64
    generate = nodes.OpenRouterVideoGenerate.define_schema()
    assert _schema_inputs(generate)["model"].options["options"] == ["SELECT MODEL"]
    projected = payload["models"][0]
    assert projected["supported_resolutions"] == ("480p", "768p")
    assert projected["supported_aspect_ratios"] == ("16:9", "5:4")
    assert projected["supports_seed"] is None
    assert projected["supported_reference_kinds"] == ("image", "video")
    assert projected["max_reference_count"] == 50
    assert projected["mixed_reference_kinds"] is True
    assert projected["supported_inference_methods"] == (
        "T2V",
        "I2V",
        "IR2V",
        "MI2V",
        "VR2V",
        "MMR2V",
    )
    serialized = repr(payload).lower()
    assert "pricing" not in serialized
    assert "0.42" not in serialized


def test_empty_catalogue_is_not_misclassified_as_ui_desync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = datetime(2026, 9, 26, 19, 54, 44, tzinfo=timezone.utc)

    class Runtime:
        async def effective_catalog(self) -> object:
            return types.SimpleNamespace(observed_at=observed, models=())

    monkeypatch.setattr(routes, "get_runtime", Runtime)
    monkeypatch.setattr(
        compat,
        "json_response",
        lambda payload, *, status: (payload, status),
    )

    payload, status = asyncio.run(routes._ui_capabilities_handler(None))

    assert status == 200
    assert payload["models"] == []
    assert compat.catalogue_health_snapshot()["catalogue_state"] == "EMPTY"


def test_health_route_is_pure_local_sanitized_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "get_runtime",
        lambda: pytest.fail("health must not initialize runtime or perform upstream work"),
    )
    monkeypatch.setattr(
        routes,
        "local_runtime_health",
        lambda: {"runtime_state": "READY", "database_state": "READY"},
    )
    monkeypatch.setattr(routes, "openrouter_credential_state", lambda: "PRESENT")
    monkeypatch.setattr(
        compat,
        "catalogue_health_snapshot",
        lambda: {
            "catalogue_state": "FRESH",
            "catalogue_model_count": 30,
            "catalogue_revision": "a" * 64,
        },
    )
    monkeypatch.setattr(compat, "json_response", lambda payload, *, status: (payload, status))

    payload, status = asyncio.run(routes._health_handler(None))

    assert status == 200
    assert payload == {
        "schema_version": 1,
        "plugin_loaded": True,
        "runtime_state": "READY",
        "database_state": "READY",
        "credential_state": "PRESENT",
        "catalogue_state": "FRESH",
        "catalogue_model_count": 30,
        "catalogue_revision": "a" * 64,
        "plugin_version": "0.1.0",
        "ui_contract_version": 4,
    }
    assert "key" not in repr(payload).lower()
    assert "authorization" not in repr(payload).lower()


def test_cost_estimate_route_returns_prepared_result_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = datetime(2026, 9, 26, 19, 54, 44, tzinfo=timezone.utc)
    captured: list[object] = []

    class Request:
        async def json(self) -> object:
            return {
                "model_id": "vendor/model",
                "duration": 4,
                "resolution": "480p",
                "aspect_ratio": "16:9",
                "generate_audio": False,
                "inference_method": "I2V",
                "reference_kinds": [],
                "reference_count": 0,
                "source_video_present": False,
            }

    class Runtime:
        async def estimate_cost(self, inputs: object) -> EstimateResult:
            captured.append(inputs)
            return EstimateResult(
                EstimateAvailability.AVAILABLE,
                observed,
                estimated_cost_usd=Decimal("0.140"),
                provenance="catalogue pricing_skus.per-video-second-480p × duration",
                applied_skus=("per-video-second-480p",),
            )

    monkeypatch.setattr(routes, "get_runtime", Runtime)
    monkeypatch.setattr(
        compat,
        "json_response",
        lambda payload, *, status: (payload, status),
    )

    payload, status = asyncio.run(routes._cost_estimate_handler(Request()))

    assert status == 200
    assert captured[0].model_id == "vendor/model"
    assert captured[0].inference_method.value == "I2V"
    assert payload == {
        "availability": "AVAILABLE",
        "observed_at": observed.isoformat(),
        "applied_skus": ("per-video-second-480p",),
        "estimated_cost_usd": "0.140",
        "provenance": "catalogue pricing_skus.per-video-second-480p × duration",
    }
