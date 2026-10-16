from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.verify_release_artifacts import inspect_distribution


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("contracts/private.json", b"{}", "Development content"),
        ("openrouter_video/leak.txt", b"E:/_ARENAS_lab/private", "Absolute development path"),
        ("openrouter_video/leak.txt", b"sk-or-v1-" + b"0" * 30, "Secret-class pattern"),
    ],
)
def test_package_verifier_rejects_sensitive_or_development_content(
    tmp_path: Path, name: str, content: bytes, message: str
) -> None:
    path = tmp_path / "synthetic.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr("openrouter_video/data/capability-evidence.json", "{}")
        archive.writestr("openrouter_video/comfy/nodes.py", "")
        archive.writestr("synthetic.dist-info/METADATA", "Name: synthetic\nVersion: 0.0.0\n")
        archive.writestr(name, content)
    with pytest.raises(ValueError, match=message):
        inspect_distribution(path)
