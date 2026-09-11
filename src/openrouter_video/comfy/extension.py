"""Pinned ComfyUI V3 extension exposing the Phase-6 adapter."""

from .compat import ComfyExtension, validate_host_api
from .nodes import OpenRouterVideoGenerate, OpenRouterVideoResume
from .routes import register_routes


class OpenRouterVideoExtension(ComfyExtension):
    """Register one safe route and exactly two public adapter nodes."""

    async def on_load(self) -> None:
        validate_host_api()
        register_routes()

    async def get_node_list(self) -> list[type]:
        return [OpenRouterVideoGenerate, OpenRouterVideoResume]


async def comfy_entrypoint() -> OpenRouterVideoExtension:
    """Return the extension without creating the network/runtime layer."""

    validate_host_api()
    return OpenRouterVideoExtension()


__all__ = ("OpenRouterVideoExtension", "comfy_entrypoint")
