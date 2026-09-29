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
    assert {
        case_id: (case["model_id"], case["reference_mode"]) for case_id, case in cases.items()
    } == {
        "first_frame": ("bytedance/seedance-2.0-mini", "first_frame"),
        "first_plus_last": ("bytedance/seedance-2.0-mini", "first_plus_last"),
        "multi_image_reference": (
            "bytedance/seedance-2.5",
            "multi_image_reference",
        ),
        "video_reference": ("bytedance/seedance-2.5", "video_reference"),
        "image_plus_video_reference": (
            "bytedance/seedance-2.5",
            "image_plus_video_reference",
        ),
    }


def test_runbook_matches_the_frozen_five_case_manifest() -> None:
    runbook = (ROOT / "docs" / "phase-9-live-runbook.md").read_text(encoding="utf-8")
    manifest = _manifest()
    configuration = manifest["paid_configuration"]
    assert isinstance(configuration, dict)
    for literal in (
        f"`duration={configuration['duration_seconds']}`",
        f"`resolution={configuration['resolution']}`",
        f"`aspect_ratio={configuration['aspect_ratio']}`",
        "`generate_audio=false`",
    ):
        assert literal in runbook

    cases = manifest["cases"]
    assert isinstance(cases, dict)
    for case_id, case in cases.items():
        assert f"`{case_id}`" in runbook
        assert f"`{case['model_id']}`" in runbook
        assert f"`{case['reference_mode']}`" in runbook
