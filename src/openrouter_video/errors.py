"""Internal errors for the safe OpenRouter boundary."""


class RequestPolicyError(RuntimeError):
    """A request was rejected before unsafe network transmission."""


class TransportError(RuntimeError):
    """A prepared request failed at the byte-transport boundary."""


__all__ = ("RequestPolicyError", "TransportError")
