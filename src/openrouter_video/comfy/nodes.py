"""The bounded Phase-8 ComfyUI V3 adapter nodes."""

from __future__ import annotations

from collections.abc import Mapping

from openrouter_video.application import OperationInterrupted
from openrouter_video.capabilities import infer_legacy_inference_method
from openrouter_video.execution_hooks import ExecutionPhase
from openrouter_video.local_media import NativeMediaError
from openrouter_video.models import (
    FrameReference,
    FrameType,
    GenerationRequest,
    GenerationResult,
    InferenceMethod,
    InputReference,
    InputReferenceCollection,
    InputReferenceKind,
    ProductErrorCode,
)

from . import compat
from .image import ImageBridgeError, to_image_data_url
from .native_media import native_reference
from .runtime import get_runtime
from .video import VideoBridgeError, to_native_video


class AdapterExecutionError(RuntimeError):
    """A sanitized user-facing adapter failure."""


def _optional_text(value: str) -> str | None:
    normalized = value.strip()
    if normalized == compat.AUTO_MODEL_DEFAULT:
        return None
    return normalized or None


def _duration(value: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdapterExecutionError(
            "UNSUPPORTED_PARAMETER: duration must be zero or a positive integer."
        )
    return value or None


def _model(value: object) -> str:
    if not isinstance(value, str):
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: select a model before Generate.")
    normalized = value.strip()
    if not normalized or normalized == compat.MODEL_UNRESOLVED:
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: select a model before Generate.")
    return normalized


def _seed(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: seed must be an integer.")
    if isinstance(value, int):
        if value == -1:
            return None
        if value < -1:
            raise AdapterExecutionError("UNSUPPORTED_PARAMETER: seed must be non-negative.")
        return value
    if not isinstance(value, str):
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: seed must be an integer.")
    normalized = value.strip()
    if not normalized:
        return None
    try:
        parsed = int(normalized, 10)
    except ValueError:
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: seed must be an integer.") from None
    if parsed == -1:
        return None
    if parsed < -1:
        raise AdapterExecutionError("UNSUPPORTED_PARAMETER: seed must be non-negative.")
    return parsed


def _safe_job_id(value: str | None) -> str | None:
    if value is None or len(value) > 512:
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    return value


def _frame_reference(
    reference: InputReference | object | None,
    legacy_url: str,
    frame_type: FrameType,
) -> FrameReference | None:
    normalized_url = _optional_text(legacy_url)
    if reference is not None and normalized_url is not None:
        raise AdapterExecutionError(
            "UNSUPPORTED_PARAMETER: use the typed frame socket or the legacy URL, not both."
        )
    if reference is not None:
        if not isinstance(reference, InputReference):
            reference = _image_or_reference(reference)
        if reference.kind is not InputReferenceKind.IMAGE:
            raise AdapterExecutionError(
                "UNSUPPORTED_PARAMETER: First and Last Frame require IMAGE inputs."
            )
        normalized_url = reference.url
    return FrameReference(frame_type, normalized_url) if normalized_url is not None else None


def _raise_product_error(result: GenerationResult) -> None:
    error = result.error
    if error is None:
        return
    message = f"{error.code.value}: {error.message}"
    job_id = _safe_job_id(result.job_id)
    if job_id is not None:
        message += f" Job ID: {job_id}."
    if error.code is ProductErrorCode.SUBMISSION_UNKNOWN:
        message += " Do not run Generate automatically as recovery."
    raise AdapterExecutionError(message)


async def _node_output(result: GenerationResult, node_id: str | None) -> object:
    _raise_product_error(result)
    if result.artifact is None:
        raise AdapterExecutionError(
            "INVALID_VIDEO_RESPONSE: no durable video artifact is available."
        )
    try:
        await compat.report_phase(ExecutionPhase.NATIVE_VIDEO, node_id)
        video = to_native_video(result.artifact)
    except VideoBridgeError as exc:
        raise AdapterExecutionError(str(exc)) from None
    cost = format(result.actual_cost_usd, "f") if result.actual_cost_usd is not None else ""
    output = compat.IO.NodeOutput(
        video,
        result.job_id or "",
        result.model or "",
        cost,
        result.state.value,
    )
    await compat.report_phase(ExecutionPhase.DONE, node_id)
    return output


def _outputs() -> list[object]:
    return [
        compat.IO.Video.Output("VIDEO"),
        compat.IO.String.Output("JOB_ID"),
        compat.IO.String.Output("MODEL"),
        compat.IO.String.Output("ACTUAL_COST_USD"),
        compat.IO.String.Output("STATUS"),
    ]


class OpenRouterVideoImageReference(compat.IO.ComfyNode):
    """Create one transient typed image reference from a public URL."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoImageReference",
            display_name="OpenRouter Video · Public Image URL",
            category="OpenRouter/Video/References",
            description=(
                "Creates an ordered image reference from a public HTTPS URL. "
                "Local IMAGE upload is not claimed by the current OpenRouter Video contract."
            ),
            inputs=[
                compat.IO.String.Input(
                    "url",
                    display_name="PUBLIC HTTPS IMAGE URL",
                    default="",
                    tooltip="Publicly retrievable HTTPS image URL.",
                )
            ],
            outputs=[compat.INPUT_REFERENCE_IO.Output("REFERENCE")],
        )

    @classmethod
    def execute(cls, url: str) -> object:
        return compat.IO.NodeOutput(InputReference(InputReferenceKind.IMAGE, url.strip()))


class OpenRouterVideoVideoReference(compat.IO.ComfyNode):
    """Create one transient typed video reference without edit semantics."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoVideoReference",
            display_name="OpenRouter Video · Public Video URL",
            category="OpenRouter/Video/References",
            description=(
                "Creates an ordered video reference from a public HTTPS URL. "
                "Local VIDEO upload is not claimed by the current OpenRouter Video contract."
            ),
            inputs=[
                compat.IO.String.Input(
                    "url",
                    display_name="PUBLIC HTTPS VIDEO URL",
                    default="",
                    tooltip="Publicly retrievable HTTPS video URL.",
                )
            ],
            outputs=[compat.INPUT_REFERENCE_IO.Output("REFERENCE")],
        )

    @classmethod
    def execute(cls, url: str) -> object:
        return compat.IO.NodeOutput(InputReference(InputReferenceKind.VIDEO, url.strip()))


class OpenRouterVideoAudioReference(compat.IO.ComfyNode):
    """Create one transient typed audio reference from a public URL."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoAudioReference",
            display_name="OpenRouter Video · Public Audio URL",
            category="OpenRouter/Video/References",
            description=(
                "Creates an ordered audio reference from a public HTTPS URL. "
                "Local AUDIO upload is not claimed by the current OpenRouter Video contract."
            ),
            inputs=[
                compat.IO.String.Input(
                    "url",
                    display_name="PUBLIC HTTPS AUDIO URL",
                    default="",
                    tooltip="Publicly retrievable HTTPS audio URL.",
                )
            ],
            outputs=[compat.INPUT_REFERENCE_IO.Output("REFERENCE")],
        )

    @classmethod
    def execute(cls, url: str) -> object:
        return compat.IO.NodeOutput(InputReference(InputReferenceKind.AUDIO, url.strip()))


class OpenRouterVideoReferenceCollection(compat.IO.ComfyNode):
    """Legacy Phase-8 collection node retained only for workflow compatibility."""

    @classmethod
    def define_schema(cls) -> object:
        template = compat.IO.Autogrow.TemplatePrefix(
            input=compat.INPUT_REFERENCE_IO.Input("reference"),
            prefix="reference_",
            min=0,
            max=100,
        )
        return compat.IO.Schema(
            node_id="OpenRouterVideoReferenceCollection",
            display_name="OpenRouter Video · Legacy Reference Collection",
            category="OpenRouter/Video/References",
            description=(
                "Phase-8 compatibility node. New workflows connect ordered URL reference "
                "nodes directly to OpenRouter Video Generate."
            ),
            inputs=[compat.IO.Autogrow.Input("references", template=template, optional=True)],
            outputs=[compat.INPUT_REFERENCE_COLLECTION_IO.Output("INPUT_REFERENCES")],
        )

    @classmethod
    def execute(cls, references: dict[str, InputReference] | None = None) -> object:
        return compat.IO.NodeOutput(_reference_collection(references))


def _reference_collection(
    references: Mapping[str, object] | None,
) -> InputReferenceCollection:
    """Preserve autogrow positions, duplicates and heterogeneous order exactly."""

    indexed: list[tuple[int, InputReference]] = []
    for name, reference in (references or {}).items():
        prefix, separator, suffix = name.rpartition("_")
        if prefix != "reference" or not separator or not suffix.isdigit():
            raise AdapterExecutionError("UNSUPPORTED_PARAMETER: invalid reference position.")
        indexed.append((int(suffix), _media_or_reference(reference)))
    indexed.sort(key=lambda item: item[0])
    return InputReferenceCollection(tuple(reference for _, reference in indexed))


def _media_or_reference(value: object) -> InputReference:
    if isinstance(value, InputReference):
        return value
    if isinstance(value, dict) or callable(getattr(value, "save_to", None)):
        try:
            return native_reference(value)
        except NativeMediaError as exc:
            raise AdapterExecutionError(str(exc)) from None
    return _image_or_reference(value)


def _image_or_reference(value: InputReference | object) -> InputReference:
    if isinstance(value, InputReference):
        return value
    try:
        return InputReference(InputReferenceKind.IMAGE, to_image_data_url(value))
    except ImageBridgeError as exc:
        raise AdapterExecutionError(str(exc)) from None


class OpenRouterVideoGenerate(compat.IO.ComfyNode):
    """Map one intentional queue execution to one Core Generate operation."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoGenerate",
            display_name="OpenRouter Video Generate",
            category="OpenRouter/Video",
            not_idempotent=True,
            inputs=[
                compat.model_input(),
                compat.IO.Combo.Input(
                    "inference_method",
                    options=[method.value for method in InferenceMethod],
                    default=InferenceMethod.T2V.value,
                    tooltip="Local product intent. Never sent as an OpenRouter field.",
                ),
                compat.IO.String.Input("prompt", display_name="Prompt", default="", multiline=True),
                compat.IO.String.Input("resolution", default=""),
                compat.IO.String.Input("aspect_ratio", default=""),
                compat.IO.Int.Input("duration", default=0, min=0, step=1),
                compat.IO.String.Input("size", default="", advanced=True),
                compat.IO.Int.Input(
                    "seed",
                    default=-1,
                    min=-1,
                    max=(1 << 63) - 1,
                    step=1,
                    control_after_generate=compat.IO.ControlAfterGenerate.randomize,
                    display_mode=compat.IO.NumberDisplay.number,
                ),
                compat.IO.Boolean.Input("generate_audio", default=False),
                compat.IO.String.Input(
                    "first_frame_url",
                    display_name="first_frame",
                    default="",
                    advanced=True,
                ),
                compat.IO.String.Input(
                    "last_frame_url",
                    display_name="last_frame",
                    default="",
                    advanced=True,
                ),
                compat.IMAGE_OR_REFERENCE_IO.Input(
                    "first_frame",
                    display_name="first_frame",
                    optional=True,
                ),
                compat.IMAGE_OR_REFERENCE_IO.Input(
                    "last_frame",
                    display_name="last_frame",
                    optional=True,
                ),
                compat.VIDEO_OR_REFERENCE_IO.Input(
                    "source_video",
                    display_name="source_video",
                    optional=True,
                    advanced=True,
                ),
                compat.IO.Autogrow.Input(
                    "direct_references",
                    display_name="ORDERED REFERENCES",
                    template=compat.IO.Autogrow.TemplatePrefix(
                        input=compat.MEDIA_OR_REFERENCE_IO.Input("reference"),
                        prefix="reference_",
                        min=0,
                        max=100,
                    ),
                    optional=True,
                    tooltip=(
                        "Connect Load Image, Load Video, Load Audio or typed references in order. "
                        "The UI enforces the selected model's effective count and kinds; "
                        "Core validates again before submit."
                    ),
                ),
                compat.INPUT_REFERENCE_COLLECTION_IO.Input(
                    "input_references",
                    display_name="LEGACY PHASE-8 REFERENCES",
                    optional=True,
                    advanced=True,
                ),
            ],
            outputs=_outputs(),
            hidden=[compat.IO.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> int:
        """Work around the proven pinned PromptExecutor cross-queue cache regression."""

        return compat.next_cache_token()

    @classmethod
    def validate_inputs(
        cls, model: str, direct_references: Mapping[str, object] | None = None
    ) -> bool | str:
        """Let Core authorize availability; accept host-reconstructed Autogrow input."""

        del direct_references

        if (
            not isinstance(model, str)
            or not model
            or model == compat.MODEL_UNRESOLVED
            or model != model.strip()
            or len(model) > 512
            or any(ord(character) < 32 or ord(character) == 127 for character in model)
        ):
            return "Select a current OpenRouter video model before queueing."
        return True

    @classmethod
    async def execute(
        cls,
        model: str,
        prompt: str,
        duration: int = 0,
        resolution: str = "",
        aspect_ratio: str = "",
        size: str = "",
        seed: int | str | None = -1,
        generate_audio: bool = False,
        first_frame_url: str = "",
        last_frame_url: str = "",
        first_frame: InputReference | object | None = None,
        last_frame: InputReference | object | None = None,
        source_video: InputReference | object | None = None,
        direct_references: Mapping[str, object] | None = None,
        input_references: InputReferenceCollection | None = None,
        inference_method: str = "",
    ) -> object:
        if direct_references and input_references is not None:
            raise AdapterExecutionError(
                "UNSUPPORTED_PARAMETER: use direct ordered references or the legacy "
                "Phase-8 collection, not both."
            )
        direct_collection = _reference_collection(direct_references)
        effective_references = (
            direct_collection if direct_collection.references else input_references
        )
        first_reference = _frame_reference(first_frame, first_frame_url, FrameType.FIRST)
        last_reference = _frame_reference(last_frame, last_frame_url, FrameType.LAST)
        references = effective_references.references if effective_references is not None else ()
        try:
            method = InferenceMethod(inference_method)
        except (TypeError, ValueError):
            method = infer_legacy_inference_method(
                first_frame=first_reference,
                last_frame=last_reference,
                references=references,
            )
        request = GenerationRequest(
            model=_model(model),
            prompt=prompt if prompt.strip() else None,
            inference_method=method,
            duration=_duration(duration),
            resolution=_optional_text(resolution),
            aspect_ratio=_optional_text(aspect_ratio),
            size=_optional_text(size),
            seed=_seed(seed),
            generate_audio=generate_audio,
            first_frame=first_reference,
            last_frame=last_reference,
            source_video=_media_or_reference(source_video) if source_video is not None else None,
            input_references=effective_references,
        )
        node_id = compat.current_node_id(cls)
        try:
            result = await get_runtime().generate(request, node_id)
        except OperationInterrupted:
            compat.raise_host_interrupt()
        return await _node_output(result, node_id)


class OpenRouterVideoResume(compat.IO.ComfyNode):
    """Observe and download an existing job without a submit capability."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoResume",
            display_name="OpenRouter Video Resume",
            category="OpenRouter/Video",
            not_idempotent=True,
            inputs=[compat.IO.String.Input("job_id", default="")],
            outputs=_outputs(),
            hidden=[compat.IO.Hidden.unique_id],
        )

    @classmethod
    def fingerprint_inputs(cls, **_: object) -> int:
        """Prevent stale durable observation output across separate Queue actions."""

        return compat.next_cache_token()

    @classmethod
    async def execute(cls, job_id: str) -> object:
        normalized = job_id.strip()
        if not normalized:
            raise AdapterExecutionError("JOB_NOT_FOUND: job_id must not be empty.")
        node_id = compat.current_node_id(cls)
        try:
            result = await get_runtime().resume(normalized, node_id)
        except OperationInterrupted:
            compat.raise_host_interrupt()
        return await _node_output(result, node_id)


__all__ = (
    "AdapterExecutionError",
    "OpenRouterVideoGenerate",
    "OpenRouterVideoAudioReference",
    "OpenRouterVideoImageReference",
    "OpenRouterVideoReferenceCollection",
    "OpenRouterVideoResume",
    "OpenRouterVideoVideoReference",
)
