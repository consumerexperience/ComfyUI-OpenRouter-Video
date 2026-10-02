"""Pinned ComfyUI V3 extension exposing the Phase-6 adapter."""

from .compat import ComfyExtension, validate_host_api
from .nodes import (
    OpenRouterVideoAudioReference,
    OpenRouterVideoGenerate,
    OpenRouterVideoImageReference,
    OpenRouterVideoReferenceCollection,
    OpenRouterVideoResume,
    OpenRouterVideoVideoReference,
)
from .routes import register_routes


class OpenRouterVideoExtension(ComfyExtension):
    """Register one safe route and the bounded Phase-8 adapter nodes."""

    async def on_load(self) -> None:
        validate_host_api()
        register_routes()
        from .runtime import get_runtime

        get_runtime()

    async def get_node_list(self) -> list[type]:
        return [
            OpenRouterVideoImageReference,
            OpenRouterVideoVideoReference,
            OpenRouterVideoAudioReference,
            OpenRouterVideoReferenceCollection,
            OpenRouterVideoGenerate,
            OpenRouterVideoResume,
        ]


async def comfy_entrypoint() -> OpenRouterVideoExtension:
    """Return the extension without creating the network/runtime layer."""

    validate_host_api()
    return OpenRouterVideoExtension()


__all__ = ("OpenRouterVideoExtension", "comfy_entrypoint")
