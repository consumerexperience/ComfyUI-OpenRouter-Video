"""Inspect locally built distributions without installing or publishing them."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {
    ".git",
    ".github",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "tests",
    "contracts",
    "output",
    "delivery-receipts",
    ".idea",
    ".vscode",
}
SECRET = re.compile(
    rb"sk-or-v1-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"[?&]X-Amz-Signature=[0-9a-fA-F]{32,}"
)
LOCAL_PATH = re.compile(rb"(?:[EC]:[/\\](?:Users|_ARENAS_lab)[/\\])", re.I)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def inspect_distribution(path: Path) -> dict[str, object]:
    """Fail without exposing matched secret values."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            entries = {
                name: archive.read(name) for name in archive.namelist() if not name.endswith("/")
            }
        required = {
            "openrouter_video/data/capability-evidence.json",
            "openrouter_video/comfy/nodes.py",
        }
    else:
        with tarfile.open(path) as archive:
            entries = {}
            for member in archive.getmembers():
                if member.isfile():
                    stream = archive.extractfile(member)
                    require(stream is not None, "Unreadable archive member")
                    if stream is None:
                        raise ValueError("Unreadable archive member")
                    entries[member.name.split("/", 1)[1]] = stream.read()
        required = {
            "__init__.py",
            "web/openrouter_video.js",
            "pyproject.toml",
            "README.md",
            "LICENSE",
        }
    require(required <= entries.keys(), f"Missing required distribution files in {path.name}")
    metadata_name = next(
        (name for name in entries if name == "PKG-INFO" or name.endswith(".dist-info/METADATA")),
        None,
    )
    require(metadata_name is not None, "Package metadata missing")
    if metadata_name is None:
        raise ValueError("Package metadata missing")
    metadata = BytesParser().parsebytes(entries[metadata_name])
    for name, content in entries.items():
        parts = PurePosixPath(name).parts
        require(not set(parts) & FORBIDDEN_PARTS, f"Development content: {name}")
        require(
            not name.endswith((".png", ".zip", ".log", ".sqlite3", ".db", ".mp4", ".wav")), name
        )
        require(not any(part.startswith(".env") for part in parts), name)
        require(not SECRET.search(content), f"Secret-class pattern in {name}")
        require(not LOCAL_PATH.search(content), f"Absolute development path in {name}")
    return {
        "filename": path.name,
        "version": str(metadata["Version"]),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
        "files": sorted(entries),
        "status": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = sorted([*args.dist.glob("*.whl"), *args.dist.glob("*.tar.gz")])
    require(len(paths) == 2, "Expected exactly one wheel and one source distribution")
    result = {"status": "PASS", "artifacts": [inspect_distribution(p) for p in paths]}
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")  # noqa: T201 - explicit verifier output


if __name__ == "__main__":
    main()
