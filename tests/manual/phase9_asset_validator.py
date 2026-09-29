"""Local Stage-A validator for the frozen synthetic Phase-9 fixture corpus."""

from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "live" / "fixtures" / "phase9"


def _manifest() -> dict[str, Any]:
    value = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError(f"{path.name} is not a PNG")
    return struct.unpack(">II", data[16:24])


def _probe_video(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ValueError("ffprobe is unavailable")
    completed = subprocess.run(  # noqa: S603 - resolved executable and frozen local path
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,codec_type,width,height,r_frame_rate,duration",
            "-show_entries",
            "format=duration,format_name,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("ffprobe returned an invalid object")
    return value


def validate() -> dict[str, object]:
    manifest = _manifest()
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("manifest files are missing")
    for relative, expected_raw in files.items():
        if not isinstance(relative, str) or not isinstance(expected_raw, dict):
            raise ValueError("manifest file record is invalid")
        path = (FIXTURES / relative).resolve()
        if FIXTURES.resolve() not in path.parents:
            raise ValueError("fixture path escapes the corpus")
        if not path.is_file():
            raise ValueError(f"missing fixture: {relative}")
        if path.stat().st_size != expected_raw.get("size_bytes"):
            raise ValueError(f"size mismatch: {relative}")
        if _sha256(path) != expected_raw.get("sha256"):
            raise ValueError(f"hash mismatch: {relative}")
        if relative.endswith(".png") and _png_dimensions(path) != (
            expected_raw.get("width"),
            expected_raw.get("height"),
        ):
            raise ValueError(f"dimension mismatch: {relative}")
        if relative.endswith(".txt"):
            prompt = path.read_text(encoding="utf-8")
            if not prompt.strip() or "copyrighted characters" not in prompt:
                raise ValueError(f"prompt policy mismatch: {relative}")

    video_expected = files["motion-reference.mp4"]
    video = _probe_video(FIXTURES / "motion-reference.mp4")
    streams = video.get("streams")
    if not isinstance(streams, list):
        raise ValueError("video streams are missing")
    video_streams = [item for item in streams if item.get("codec_type") == "video"]
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    if len(video_streams) != 1 or len(audio_streams) != video_expected["audio_streams"]:
        raise ValueError("unexpected stream layout")
    stream = video_streams[0]
    if (
        stream.get("codec_name") != video_expected["video_codec"]
        or stream.get("width") != video_expected["width"]
        or stream.get("height") != video_expected["height"]
        or stream.get("r_frame_rate") != video_expected["frame_rate"]
        or float(stream.get("duration")) != video_expected["duration_seconds"]
    ):
        raise ValueError("video media contract mismatch")

    return {
        "result": "PASS",
        "fixture_count": len(files),
        "case_count": len(manifest["cases"]),
        "policy": manifest["fixture_policy"],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))  # noqa: T201 - manual gate result
