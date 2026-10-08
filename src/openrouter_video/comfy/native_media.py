"""Host-only VIDEO/AUDIO conversion into bounded temporary files."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from openrouter_video.local_media import MAX_OBJECT_BYTES, LocalMedia, NativeMediaError
from openrouter_video.models import InputReference, InputReferenceKind


def native_reference(value: Any) -> InputReference:
    if isinstance(value, dict) and "waveform" in value:
        waveform: Any = value.get("waveform")
        shape: Any = getattr(waveform, "shape", ())
        rate = value.get("sample_rate")
        if (
            len(shape) != 3
            or shape[0] != 1
            or shape[1] not in (1, 2)
            or shape[2] < 1
            or not isinstance(rate, int)
            or isinstance(rate, bool)
            or not 1 <= rate <= 384000
            or shape[1] * shape[2] * 2 + 44 > MAX_OBJECT_BYTES
        ):
            raise NativeMediaError("AUDIO requires one non-empty mono/stereo waveform.")

        def write_audio(path: Path) -> None:
            import numpy as np  # type: ignore[import-not-found]

            array = waveform[0].detach().cpu().numpy()
            if not bool(np.isfinite(array).all()):
                raise NativeMediaError("AUDIO contains non-finite samples.")
            with wave.open(str(path), "wb") as output:
                output.setnchannels(int(shape[1]))
                output.setsampwidth(2)
                output.setframerate(rate)
                # Chunk conversion bounds temporary encoding memory.
                for start in range(0, int(shape[2]), 65536):
                    pcm = np.clip(array[:, start : start + 65536], -1, 1) * 32767
                    output.writeframesraw(pcm.T.astype("<i2").tobytes())

        return InputReference(
            InputReferenceKind.AUDIO, local_media=LocalMedia("audio/wav", ".wav", write_audio)
        )
    if callable(getattr(value, "save_to", None)):

        def write_video(path: Path) -> None:
            from .compat import Types

            duration = value.get_duration()
            if not duration or duration <= 0:
                raise NativeMediaError("VIDEO must contain non-empty frames.")
            value.save_to(str(path), format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264)

        return InputReference(
            InputReferenceKind.VIDEO, local_media=LocalMedia("video/mp4", ".mp4", write_video)
        )
    raise NativeMediaError("Expected native VIDEO or AUDIO input.")
