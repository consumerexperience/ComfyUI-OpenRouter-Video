"""Generate temporary CFR/VFR MP4 and WebM samples and verify native LAST_FRAME."""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _run(command: list[str]) -> str:
    completed = subprocess.run(  # noqa: S603 - commands are fixed tool invocations with local paths
        command, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfy-root", type=Path, required=True)
    parser.add_argument("--product-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.comfy_root))
    sys.path.insert(0, str(args.product_root / "src"))

    torch = importlib.import_module("torch")
    from comfy_api.v0_0_2 import InputImpl

    from openrouter_video.comfy.compat import last_frame_from_file

    repo_revision = _run(["git", "-C", str(args.comfy_root), "rev-parse", "HEAD"])
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="orv-last-frame-") as temporary:
        temp = Path(temporary)
        for extension, codec in (("mp4", "libx264"), ("webm", "libvpx-vp9")):
            for profile in ("cfr", "vfr"):
                target = temp / f"synthetic-{profile}.{extension}"
                command = [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=128x72:rate=30:duration=2",
                ]
                if profile == "vfr":
                    command += ["-vf", "select='not(mod(n,5))+not(mod(n,7))'", "-fps_mode", "vfr"]
                command += ["-an", "-c:v", codec]
                if extension == "mp4":
                    command += ["-pix_fmt", "yuv420p"]
                command += ["-y", str(target)]
                _run(command)

                source = InputImpl.VideoFromFile(str(target))
                full = source.get_components().images
                tail = last_frame_from_file(target)
                if tail is None:
                    raise RuntimeError(f"Native extraction omitted {profile} {extension}")
                exact = torch.equal(full[-1:], tail)
                if not exact:
                    raise RuntimeError(f"Native extraction differs for {profile} {extension}")
                timestamps: list[float] = []
                if profile == "vfr":
                    raw = _run(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-select_streams",
                            "v:0",
                            "-show_entries",
                            "frame=best_effort_timestamp_time",
                            "-of",
                            "csv=p=0",
                            str(target),
                        ]
                    )
                    timestamps = [float(line.rstrip(",")) for line in raw.splitlines() if line]
                    deltas = {
                        round(b - a, 6) for a, b in zip(timestamps, timestamps[1:], strict=False)
                    }
                    if len(deltas) < 2:
                        raise RuntimeError(f"Generated {extension} sample was not VFR")
                cases.append(
                    {
                        "container": extension,
                        "profile": profile,
                        "duration_seconds": source.get_duration(),
                        "reported_frame_rate": float(source.get_frame_rate()),
                        "reported_frame_count": source.get_frame_count(),
                        "full_shape": list(full.shape),
                        "returned_shape": list(tail.shape),
                        "exact_full_decode_last_frame_match": exact,
                        "returned_value_range": [float(tail.min()), float(tail.max())],
                        "vfr_timestamp_count": len(timestamps),
                        "vfr_unique_intervals_seconds": sorted(
                            {
                                round(b - a, 6)
                                for a, b in zip(timestamps, timestamps[1:], strict=False)
                            }
                        ),
                        "ffmpeg_command": command[:-2] + ["-y", f"<temp>/{target.name}"],
                    }
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "comfyui_dev_revision": repo_revision,
                "comfy_root": str(args.comfy_root.resolve()),
                "product_root": str(args.product_root.resolve()),
                "python": sys.executable,
                "temporary_media": "Generated under Python TemporaryDirectory and removed at exit",
                "runtime_started": False,
                "protected_source_config_or_package_changes": False,
                "temporary_and_evidence_writes": True,
                "api": "comfy_api.v0_0_2.InputImpl.VideoFromFile",
                "source_file": str(
                    (args.comfy_root / "comfy_api/latest/_input_impl/video_types.py").resolve()
                ),
                "source_binding": (
                    "comfy_api/v0_0_2/__init__.py re-exports InputImpl_latest as InputImpl"
                ),
                "method": "native bounded start_time trim with duration=0 to decode through EOF",
                "python_command": (
                    "<comfy-root>/.venv/Scripts/python.exe "
                    "tests/manual/last_frame_native_verify.py "
                    "--comfy-root <comfy-root> --product-root <product-root> "
                    "--output tests/manual/last-frame-verification.json"
                ),
                "pytest_command": (
                    "PYTHONPATH=src python -m pytest tests/comfy/test_last_frame.py "
                    "tests/comfy/test_adapter.py -q"
                ),
                "command_template": (
                    "ffmpeg -f lavfi -i testsrc2=size=128x72:rate=30:duration=2 "
                    "[-vf select='not(mod(n,5))+not(mod(n,7))' -fps_mode vfr] "
                    "-an -c:v {libx264|libvpx-vp9} [-pix_fmt yuv420p for mp4]"
                ),
                "cases": cases,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
