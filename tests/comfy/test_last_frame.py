"""Focused tests for best-effort native final-frame extraction."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openrouter_video.comfy import compat


def test_native_frame_extraction_expands_backward_and_decodes_through_eof(
    monkeypatch: Any,
) -> None:
    calls: list[dict[str, object]] = []

    class Source:
        def __init__(self, path: str, *, start_time: float = 0) -> None:
            calls.append({"path": path, "start_time": start_time})
            self.start_time = start_time

        def get_duration(self) -> float:
            return 8.0

        def get_frame_rate(self) -> float:
            return 1.0

        def get_components(self) -> object:
            # Native implementation decodes from start_time through EOF.
            images = [] if self.start_time > 6 else ["earlier", "last"]
            return SimpleNamespace(images=_TensorLike(images))

    monkeypatch.setattr(compat, "validate_host_api", lambda: None)
    monkeypatch.setattr(compat, "InputImpl", SimpleNamespace(VideoFromFile=Source))

    result = compat.last_frame_from_file(Path("synthetic.mp4"))

    assert result is not None
    assert result.values == ["last"]
    assert calls == [
        {"path": "synthetic.mp4", "start_time": 0},
        {"path": "synthetic.mp4", "start_time": 7.0},
        {"path": "synthetic.mp4", "start_time": 6.0},
    ]


def test_native_frame_extraction_returns_none_for_empty_video(
    monkeypatch: Any,
) -> None:
    class Source:
        def __init__(self, path: str, *, start_time: float = 0) -> None:
            pass

        def get_duration(self) -> float:
            return 0.0

        def get_frame_rate(self) -> float:
            return 30.0

        def get_components(self) -> object:
            return SimpleNamespace(images=_TensorLike([]))

    monkeypatch.setattr(compat, "validate_host_api", lambda: None)
    monkeypatch.setattr(compat, "InputImpl", SimpleNamespace(VideoFromFile=Source))

    assert compat.last_frame_from_file(Path("synthetic.webm")) is None


class _TensorLike:
    def __init__(self, values: list[str]) -> None:
        self.values = values

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: slice) -> _TensorLike:
        return _TensorLike(self.values[index])

    def clone(self) -> _TensorLike:
        return _TensorLike(list(self.values))
