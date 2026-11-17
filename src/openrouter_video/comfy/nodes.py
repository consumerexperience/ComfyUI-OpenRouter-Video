"""The bounded Phase-8 ComfyUI V3 adapter nodes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal

from openrouter_video.application import OperationInterrupted
from openrouter_video.capabilities import infer_legacy_inference_method
from openrouter_video.configuration import project_method, project_semantic_values
from openrouter_video.evidence_registry import load_manifest
from openrouter_video.execution_hooks import ExecutionPhase
from openrouter_video.geometry import wire_geometry
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
    LocalLifecycleState,
    ModelCapabilities,
    ProductErrorCode,
    ProviderOption,
)

from . import compat
from .image import ImageBridgeError, to_image_data_url
from .native_media import native_reference
from .runtime import get_runtime
from .video import VideoBridgeError, to_native_last_frame, to_native_video


class AdapterExecutionError(RuntimeError):
    """A sanitized user-facing adapter failure."""


def _optional_text(value: str) -> str | None:
    normalized = value.strip()
    if normalized == compat.AUTO_MODEL_DEFAULT:
        return None
    return normalized or None


def _duration(value: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < -1:
        raise AdapterExecutionError(
            "UNSUPPORTED_PARAMETER: duration must be -1, zero, or a positive integer."
        )
    return None if value == 0 else value


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


def _actual_ui_metadata(
    result: GenerationResult,
    *,
    operation_kind: str,
    expected_job_id: str | None = None,
) -> dict[str, object] | None:
    """Execution-local receipt only; no current estimate or mutable node context."""
    if result.state is not LocalLifecycleState.DONE or operation_kind not in {"GENERATE", "RESUME"}:
        return None
    if (
        not isinstance(result.job_id, str)
        or not result.job_id
        or _safe_job_id(result.job_id) is None
    ):
        return None
    if not isinstance(result.model, str) or not result.model or _safe_job_id(result.model) is None:
        return None
    if operation_kind == "RESUME" and (not expected_job_id or result.job_id != expected_job_id):
        return None
    if result.actual_cost_usd is not None and not isinstance(result.actual_cost_usd, Decimal):
        return None
    row: dict[str, object] = {
        "schema_version": 1,
        "job_id": result.job_id,
        "model": result.model,
        "amount_usd": None
        if result.actual_cost_usd is None
        else format(result.actual_cost_usd, "f"),
        "state": "DONE",
        "operation_kind": operation_kind,
    }
    if operation_kind == "RESUME":
        row["expected_job_id"] = expected_job_id
    return {"orv_actual_v1": [row]}


async def _node_output(
    result: GenerationResult,
    node_id: str | None,
    *,
    operation_kind: str = "GENERATE",
    expected_job_id: str | None = None,
) -> object:
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
    # LAST_FRAME is an auxiliary local decode; its failure never invalidates VIDEO.
    last_frame = to_native_last_frame(result.artifact)
    cost = format(result.actual_cost_usd, "f") if result.actual_cost_usd is not None else ""
    output = compat.IO.NodeOutput(
        video,
        result.job_id or "",
        result.model or "",
        cost,
        result.state.value,
        last_frame,
        ui=_actual_ui_metadata(
            result, operation_kind=operation_kind, expected_job_id=expected_job_id
        ),
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
        compat.IO.Image.Output("LAST_FRAME"),
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


def _creative_provider_inputs() -> dict[str, tuple[str, str | None, str]]:
    """Native STRING schema from reviewed semantics; never infer from field spelling."""
    result: dict[str, tuple[str, str | None, str]] = {}
    for model in load_manifest()["models"]:
        shapes = model["facts"].get("request_shape_profiles", {}).get("value", {})
        for method in shapes.get("methods", {}).values():
            control = method.get("controls", {}).get("provider_options", {})
            for provider, options in control.get("providers", {}).items():
                for key, spec in options.items():
                    if spec.get("text_semantic") not in {"negative_prompt", "creative_prompt"}:
                        continue
                    container = spec.get("container")
                    name = f"provider_option:{provider}:{container or ''}:{key}"
                    result[name] = (provider, container, key)
    return dict(sorted(result.items()))


def _merge_linked_creative_text(
    capability: ModelCapabilities,
    method: str,
    saved: tuple[ProviderOption, ...],
    inputs: Mapping[str, object],
) -> tuple[ProviderOption, ...]:
    """Resolve native STRING inputs through the same current provider contract."""
    identities = _creative_provider_inputs()
    if set(inputs) - identities.keys():
        raise ValueError("Unknown creative text input")
    providers = project_method(capability, method)["controls"].get("provider_options", {})
    active = providers.get("providers", {}) if providers.get("state") == "SUPPORTED" else {}
    result = list(saved)
    for name, value in inputs.items():
        if not isinstance(value, str):
            raise ValueError("Creative text input must be STRING")
        provider, container, key = identities[name]
        spec = active.get(provider, {}).get(key)
        if not spec or spec.get("text_semantic") not in {"negative_prompt", "creative_prompt"}:
            raise ValueError("Linked creative text is unsupported in the current method")
        result = [
            option
            for option in result
            if (option.provider, option.container, option.key) != (provider, container, key)
        ]
        if value:
            result.append(ProviderOption(provider, key, value, container))
    return tuple(result)


class OpenRouterVideoGenerate(compat.IO.ComfyNode):
    """Map one intentional queue execution to one Core Generate operation."""

    @classmethod
    def define_schema(cls) -> object:
        return compat.IO.Schema(
            node_id="OpenRouterVideoGenerate",
            display_name="OpenRouter Video",
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
                compat.IO.String.Input("prompt", display_name="prompt", default="", multiline=True),
                compat.IO.String.Input("resolution", default=""),
                compat.IO.String.Input("aspect_ratio", default=""),
                compat.IO.Int.Input("duration", default=0, min=-1, step=1),
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
                compat.IO.String.Input(
                    "geometry_authority", default="", optional=True, advanced=True
                ),
                compat.IO.String.Input("previous_job_id", default="", optional=True, advanced=True),
                compat.IO.String.Input("upscale_factor", default="", optional=True),
                compat.IO.Int.Input("creativity", default=-1, min=-1, optional=True),
                compat.IO.String.Input(
                    "provider_options", default="", optional=True, advanced=True
                ),
                *[
                    compat.IO.String.Input(
                        name,
                        display_name="negative prompt",
                        default="",
                        optional=True,
                        multiline=True,
                    )
                    for name in _creative_provider_inputs()
                ],
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
        geometry_authority: str = "",
        previous_job_id: str = "",
        upscale_factor: str | float | None = None,
        creativity: int | None = None,
        provider_options: str = "",
        **provider_text_inputs: object,
    ) -> object:
        normalized_model = _model(model)
        if geometry_authority and geometry_authority not in {"NORMALIZED", "EXACT"}:
            raise AdapterExecutionError(
                "Ambiguous saved geometry: explicitly edit a geometry control."
            )
        options: tuple[ProviderOption, ...] = ()
        if provider_options:
            try:
                decoded = json.loads(provider_options)
                if not isinstance(decoded, list) or len(decoded) > 64:
                    raise ValueError("Invalid option collection")
                options = tuple(ProviderOption(**item) for item in decoded)
            except (TypeError, ValueError):
                raise AdapterExecutionError(
                    "UNSUPPORTED_PARAMETER: invalid provider controls."
                ) from None
        if upscale_factor in (None, "", 0):
            factor = None
        else:
            try:
                factor = float(upscale_factor)
            except (ValueError, TypeError):
                raise AdapterExecutionError(
                    "UNSUPPORTED_PARAMETER: invalid upscale factor."
                ) from None
        runtime = get_runtime()
        observation = await runtime.effective_catalog()
        capability = next(
            (m for m in observation.models if normalized_model in {m.model_id, m.canonical_slug}),
            None,
        )
        if capability is None:
            raise AdapterExecutionError("UNSUPPORTED_MODEL: select a current model.")
        if inference_method:
            try:
                method = InferenceMethod(inference_method)
            except (TypeError, ValueError):
                raise AdapterExecutionError(
                    "UNSUPPORTED_PARAMETER: invalid inference method."
                ) from None
        else:
            legacy_references = (
                input_references or _reference_collection(direct_references)
            ).references
            method = infer_legacy_inference_method(
                first_frame=FrameReference(FrameType.FIRST, "")
                if first_frame is not None or first_frame_url
                else None,
                last_frame=FrameReference(FrameType.LAST, "")
                if last_frame is not None or last_frame_url
                else None,
                references=legacy_references,
            )
        try:
            options = _merge_linked_creative_text(
                capability, method.value, options, provider_text_inputs
            )
            projected = project_semantic_values(
                capability,
                method.value,
                {
                    "prompt": prompt,
                    "duration": duration,
                    "resolution": resolution,
                    "aspect_ratio": aspect_ratio,
                    "size": size,
                    "seed": seed,
                    "generate_audio": generate_audio,
                    "geometry_authority": geometry_authority,
                    "previous_job_id": previous_job_id,
                    "upscale_factor": factor,
                    "creativity": creativity,
                    "provider_options": options,
                    "first_frame": first_frame,
                    "last_frame": last_frame,
                    "source_video": source_video,
                    "direct_references": direct_references,
                    "input_references": input_references,
                },
            )
        except ValueError as exc:
            raise AdapterExecutionError(f"CAPABILITY_SIGNAL_GAP: {exc}") from None
        fixed = project_method(capability, method.value)["topology"]["fixed"]
        first_frame, last_frame, source_video = (
            projected[k] for k in ("first_frame", "last_frame", "source_video")
        )
        first_frame_url = first_frame_url if "first_frame" in fixed else ""
        last_frame_url = last_frame_url if "last_frame" in fixed else ""
        direct_references = projected["direct_references"]
        input_references = projected["input_references"]
        duration, resolution, aspect_ratio, size, seed, generate_audio = (
            projected[k]
            for k in ("duration", "resolution", "aspect_ratio", "size", "seed", "generate_audio")
        )
        if geometry_authority == "EXACT" and size is None:
            geometry_authority = "NORMALIZED"
        prompt = projected["prompt"] or ""
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
        try:
            wire_resolution, wire_aspect, wire_size = wire_geometry(
                geometry_authority,
                _optional_text(resolution or ""),
                _optional_text(aspect_ratio or ""),
                _optional_text(size or ""),
            )
        except ValueError as exc:
            raise AdapterExecutionError(str(exc)) from None
        request = GenerationRequest(
            model=_model(model),
            prompt=prompt if prompt.strip() else None,
            inference_method=method,
            duration=_duration(duration or 0),
            resolution=wire_resolution,
            aspect_ratio=wire_aspect,
            size=wire_size,
            seed=_seed(seed),
            generate_audio=generate_audio,
            first_frame=first_reference,
            last_frame=last_reference,
            source_video=_media_or_reference(source_video) if source_video is not None else None,
            input_references=effective_references,
            previous_job_id=projected.get("previous_job_id"),
            upscale_factor=projected.get("upscale_factor"),
            creativity=projected.get("creativity"),
            provider_options=projected.get("provider_options", ()),
        )
        node_id = compat.current_node_id(cls)
        try:
            result = await runtime.generate(request, node_id)
        except OperationInterrupted:
            compat.raise_host_interrupt()
        return await _node_output(result, node_id, operation_kind="GENERATE")


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
        return await _node_output(
            result, node_id, operation_kind="RESUME", expected_job_id=normalized
        )


__all__ = (
    "AdapterExecutionError",
    "OpenRouterVideoGenerate",
    "OpenRouterVideoAudioReference",
    "OpenRouterVideoImageReference",
    "OpenRouterVideoReferenceCollection",
    "OpenRouterVideoResume",
    "OpenRouterVideoVideoReference",
)
