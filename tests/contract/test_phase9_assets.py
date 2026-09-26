from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "live" / "fixtures" / "phase9"


def _manifest() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8")),
    )


def test_frozen_phase9_fixture_bytes_and_image_dimensions() -> None:
    manifest = _manifest()
    files = manifest["files"]
    assert isinstance(files, dict)

    for relative, expected in files.items():
        assert isinstance(relative, str)
        assert isinstance(expected, dict)
        path = FIXTURES / relative
        data = path.read_bytes()
        assert len(data) == expected["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == expected["sha256"]
        if relative.endswith(".png"):
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack(">II", data[16:24]) == (
                expected["width"],
                expected["height"],
            )
        elif relative.endswith(".mp4"):
            assert data[4:8] == b"ftyp"
        else:
            assert path.read_text(encoding="utf-8").strip()


def test_exact_five_case_configuration_and_mapping_is_frozen() -> None:
    manifest = _manifest()

    assert manifest["paid_configuration"] == {
        "duration_seconds": 4,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": False,
    }
    cases = manifest["cases"]
    assert isinstance(cases, dict)
    assert set(cases) == {
        "first_frame",
        "first_plus_last",
        "multi_image_reference",
        "video_reference",
        "image_plus_video_reference",
    }
    assert all(case["assets"] and case["prompt"] for case in cases.values())
