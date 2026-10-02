"""Offline real-host conversions and unions. No server, credentials or network."""

# mypy: ignore-errors
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import wave
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--schema-out", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.host))
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    sys.argv = [sys.argv[0], "--cpu"]
    import comfy.options

    comfy.options.enable_args_parsing()
    import av
    import torch
    from comfy_api.v0_0_2 import InputImpl, Types
    from comfy_execution.validation import validate_node_input

    from openrouter_video.comfy import compat
    from openrouter_video.comfy.native_media import native_reference
    from openrouter_video.comfy.nodes import (
        OpenRouterVideoGenerate,
        _media_or_reference,
        _reference_collection,
    )
    from openrouter_video.local_media import NativeMediaError

    compat.validate_host_api()
    union = "IMAGE,VIDEO,AUDIO,OPENROUTER_VIDEO_INPUT_REFERENCE"
    for kind in union.split(","):
        assert validate_node_input(kind, union)
    assert validate_node_input("VIDEO", "VIDEO,OPENROUTER_VIDEO_INPUT_REFERENCE")
    assert not validate_node_input("AUDIO", "VIDEO,OPENROUTER_VIDEO_INPUT_REFERENCE")
    with tempfile.TemporaryDirectory(prefix="native-media-proof-") as temporary:
        root = Path(temporary)
        video = InputImpl.VideoFromComponents(
            Types.VideoComponents(images=torch.zeros((2, 16, 16, 3)), frame_rate=2, audio=None)
        )
        source = root / "source.webm"
        with av.open(str(source), "w", format="webm") as output:
            stream = output.add_stream("libvpx", rate=2)
            stream.width = 16
            stream.height = 16
            stream.pix_fmt = "yuv420p"
            import numpy as np

            for _ in range(2):
                frame = av.VideoFrame.from_ndarray(
                    np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24"
                )
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        for index, value in enumerate([video, InputImpl.VideoFromFile(str(source))]):
            ref = native_reference(value)
            path = root / f"encoded-{index}.mp4"
            assert ref.local_media.encode(path) > 0
            with av.open(str(path)) as container:
                assert container.streams.video[0].codec_context.name == "h264"
                assert len(list(container.decode(video=0))) == 2
        for channels in (1, 2):
            audio = {
                "waveform": torch.tensor([[[0.0, 0.5, -0.5, 1.0, -1.0]]] * channels).reshape(
                    1, channels, 5
                ),
                "sample_rate": 22050,
            }
            ref = native_reference(audio)
            path = root / f"audio-{channels}.wav"
            ref.local_media.encode(path)
            with wave.open(str(path)) as file:
                assert (
                    file.getnchannels(),
                    file.getsampwidth(),
                    file.getframerate(),
                    file.getnframes(),
                ) == (channels, 2, 22050, 5)
        for shape in [(2, 1, 5), (1, 3, 5), (1, 1, 0)]:
            try:
                native_reference({"waveform": torch.zeros(shape), "sample_rate": 22050})
            except NativeMediaError:
                pass
            else:
                raise AssertionError("invalid audio batch accepted")
        bad = native_reference({"waveform": torch.tensor([[[float("nan")]]]), "sample_rate": 22050})
        try:
            bad.local_media.encode(root / "invalid.wav")
        except NativeMediaError:
            pass
        else:
            raise AssertionError("nonfinite audio accepted")
        image = torch.zeros((1, 2, 2, 3))
        mixed = _reference_collection(
            {"reference_0": video, "reference_1": audio, "reference_2": image, "reference_3": video}
        )
        assert [item.kind.value for item in mixed.references] == [
            "video",
            "audio",
            "image",
            "video",
        ]
        assert _media_or_reference(video).kind.value == "video"
    if args.schema_out:
        args.schema_out.parent.mkdir(parents=True, exist_ok=True)
        args.schema_out.write_text(
            json.dumps(OpenRouterVideoGenerate.GET_NODE_INFO_V1(), indent=2), encoding="utf-8"
        )
    print("PASS: real VIDEO H264, AUDIO PCM16, IMAGE, mixed order and native unions")  # noqa: T201


if __name__ == "__main__":
    main()
