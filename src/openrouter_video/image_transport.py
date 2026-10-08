"""Bounded IMAGE data-URL contract, independent of ComfyUI objects."""

from __future__ import annotations

import base64
import binascii
import struct
import zlib

MAX_IMAGE_PIXELS = 16_777_216
MAX_PNG_BYTES = 32 * 1024 * 1024
PNG_DATA_PREFIX = "data:image/png;base64,"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def is_supported_image_data_url(value: str) -> bool:
    """Accept only bounded, structurally valid PNG data URLs for IMAGE roles."""

    if not isinstance(value, str) or not value.startswith(PNG_DATA_PREFIX):
        return False
    encoded = value[len(PNG_DATA_PREFIX) :]
    if not encoded or len(encoded) > 4 * ((MAX_PNG_BYTES + 2) // 3):
        return False
    try:
        binary = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return False
    if len(binary) < 33 or len(binary) > MAX_PNG_BYTES:
        return False
    if binary[:8] != _PNG_SIGNATURE or binary[8:16] != b"\x00\x00\x00\rIHDR":
        return False
    width, height = struct.unpack(">II", binary[16:24])
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        return False
    if binary[24] != 8 or binary[25] not in (2, 6) or binary[26:29] != b"\x00\x00\x00":
        return False
    return bool(struct.unpack(">I", binary[29:33])[0] == zlib.crc32(binary[12:29]))


__all__ = ("MAX_IMAGE_PIXELS", "MAX_PNG_BYTES", "PNG_DATA_PREFIX", "is_supported_image_data_url")
