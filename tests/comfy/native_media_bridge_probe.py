"""Offline real-host conversions and unions. No server, credentials or network."""

# mypy: ignore-errors
from __future__ import annotations

import argparse
import asyncio
import gc
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
    from openrouter_video.models import GenerationRequest, InferenceMethod
    from openrouter_video.persistence import JobStore
    from openrouter_video.staging import StagingManager

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

        # Real host encoders feed the real staging manager; the storage boundary
        # is offline. No model/capability fixture replaces canonical browser data.
        class OfflineUploader:
            def __init__(self):
                self.keys = []
                self.paths = []
                self.deleted = []

            def configuration_fingerprint(self):
                return "offline-real-host-staging"

            async def upload(self, key, path, content_type):
                with path.open("rb+") as file:
                    assert file.read(8)
                if content_type == "video/mp4":
                    with av.open(str(path)) as container:
                        assert container.streams.video[0].codec_context.name == "h264"
                else:
                    with wave.open(str(path)) as file:
                        assert (file.getnchannels(), file.getsampwidth(), file.getframerate()) == (
                            2,
                            2,
                            22050,
                        )
                self.keys.append(key)
                self.paths.append(path)

            async def presign_get(self, key):
                return "https://offline.example.test/" + key + "?signature=synthetic"

            async def delete(self, key):
                self.deleted.append(key)

        uploader = OfflineUploader()
        staging = StagingManager(JobStore(root / "offline-staging.sqlite3"), uploader)
        ordered = _reference_collection(
            {"reference_0": image, "reference_1": video, "reference_2": audio, "reference_3": video}
        )
        request = GenerationRequest(
            "bytedance/seedance-2.5",
            "Synthetic host staging proof",
            InferenceMethod.MMR2V,
            input_references=ordered,
        )
        staged = asyncio.run(staging.materialize("offline-host-proof", request))
        assert [ref["type"] for ref in staged.to_openrouter_payload()["input_references"]] == [
            "image_url",
            "video_url",
            "audio_url",
            "video_url",
        ]
        assert len(uploader.keys) == len(set(uploader.keys)) == 3
        assert all(not path.exists() for path in uploader.paths)
        asyncio.run(staging.cleanup_operation("offline-host-proof"))
        assert uploader.deleted == uploader.keys
        # Existing JobStore connections are released by GC. Release this test's
        # temporary SQLite handles before Windows removes its temporary folder.
        del staging
        gc.collect()
    if args.schema_out:
        args.schema_out.parent.mkdir(parents=True, exist_ok=True)
        args.schema_out.write_text(
            json.dumps(OpenRouterVideoGenerate.GET_NODE_INFO_V1(), indent=2), encoding="utf-8"
        )
    print(  # noqa: T201
        "PASS: real VIDEO H264, AUDIO PCM16, IMAGE, mixed order, native unions and offline staging"
    )


if __name__ == "__main__":
    main()
