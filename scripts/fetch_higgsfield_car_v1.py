#!/usr/bin/env python3
"""Fetch the official Higgsfield car-commercial asset archive unchanged."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import math
import os
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

SOURCE_URL = (
    "https://cdn.sanity.io/files/s479xw3z/production/367b90336bcfca0b8929c58e4ced493d7204760f.zip"
)
SOURCE_NAME = "all_assets_here_car_commercial.zip"
SOURCE_SIZE = 96_761_184
SOURCE_SHA256 = "3ff6d1b23f91028174a572182436781a079c1ccc44d099725db356490eace404"
CHUNK_SIZE = 4 * 1024 * 1024
SELECTED = {
    "all assets here_car commercial/car_sheet.png": (
        "fa3dcadd9b0a9492ffed690ac8c33b930251e871e5c72b638fd864fec7796c1b",
        "car_sheet.png",
    ),
    "all assets here_car commercial/loc_street_main.png": (
        "58839076ec0047430465b8516e51d93735a1cadfde9d792a0c7941271fa2b5b7",
        "loc_street_main.png",
    ),
}


def fetch_range(index: int, total: int, timeout: int) -> tuple[int, bytes]:
    start = index * CHUNK_SIZE
    end = min(total - 1, start + CHUNK_SIZE - 1)
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
    )
    # URL is the fixed official HTTPS CDN constant above; never accept a CLI URL.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        if response.status != 206:
            raise RuntimeError(f"Expected HTTP 206 for range {index}, got {response.status}")
        expected = f"bytes {start}-{end}/{total}"
        if response.headers.get("Content-Range") != expected:
            raise RuntimeError(f"Unexpected Content-Range for range {index}")
        data = response.read()
    if len(data) != end - start + 1:
        raise RuntimeError(f"Incomplete range {index}: {len(data)} bytes")
    return index, data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def materialize(archive_path: Path, pack_root: Path) -> None:
    extracted_root = pack_root / "source" / "extracted"
    assets_root = pack_root / "assets"
    extracted_root.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if not member.filename.startswith("all assets here_car commercial/"):
                continue
            destination = (extracted_root / member.filename).resolve()
            if not destination.is_relative_to(extracted_root.resolve()):
                raise RuntimeError(f"Unsafe archive path: {member.filename}")
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            content = archive.read(member)
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            elif destination.read_bytes() != content:
                raise RuntimeError(f"Refusing to replace changed extracted original: {destination}")

        for upstream_name, (expected_sha, local_name) in SELECTED.items():
            content = archive.read(upstream_name)
            actual_sha = hashlib.sha256(content).hexdigest()
            if actual_sha != expected_sha:
                raise RuntimeError(f"Unexpected upstream bytes for {upstream_name}")
            destination = assets_root / local_name
            if not destination.exists():
                destination.write_bytes(content)
            elif sha256(destination) != expected_sha:
                raise RuntimeError(f"Refusing to replace changed canonical asset: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests/live/fixtures/higgsfield_car_v1/source",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / SOURCE_NAME
    if target.exists():
        if target.stat().st_size != SOURCE_SIZE:
            raise RuntimeError(f"Refusing to replace existing noncanonical archive: {target}")
        actual_sha = sha256(target)
        if actual_sha != SOURCE_SHA256:
            raise RuntimeError(
                f"Existing archive hash does not match official source: {actual_sha}"
            )
        materialize(target, target.parent.parent)
        sys.stdout.write(f"Archive verified and materialized: {target}\n")
        sys.stdout.write(f"bytes={SOURCE_SIZE} sha256={actual_sha}\n")
        return 0

    count = math.ceil(SOURCE_SIZE / CHUNK_SIZE)
    with tempfile.TemporaryDirectory(prefix="higgsfield-car-v1-") as temporary:
        parts_dir = Path(temporary)
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch_range, i, SOURCE_SIZE, args.timeout) for i in range(count)]
            for future in concurrent.futures.as_completed(futures):
                index, data = future.result()
                (parts_dir / f"{index:04d}.part").write_bytes(data)
                completed += len(data)
                sys.stdout.write(f"downloaded={completed}/{SOURCE_SIZE}\n")
                sys.stdout.flush()

        fd, temporary_archive = tempfile.mkstemp(
            prefix=f".{SOURCE_NAME}.", suffix=".partial", dir=args.output_dir
        )
        try:
            with os.fdopen(fd, "wb") as output:
                for index in range(count):
                    output.write((parts_dir / f"{index:04d}.part").read_bytes())
            partial = Path(temporary_archive)
            if partial.stat().st_size != SOURCE_SIZE:
                raise RuntimeError(
                    "Assembled archive size does not match the official Content-Length"
                )
            with zipfile.ZipFile(partial) as archive:
                bad_member = archive.testzip()
                if bad_member:
                    raise RuntimeError(f"Archive CRC check failed: {bad_member}")
            if sha256(partial) != SOURCE_SHA256:
                raise RuntimeError("Downloaded archive SHA-256 does not match the confirmed source")
            os.replace(partial, target)
        finally:
            Path(temporary_archive).unlink(missing_ok=True)

    sys.stdout.write(f"saved={target}\n")
    sys.stdout.write(f"bytes={SOURCE_SIZE} sha256={sha256(target)}\n")
    materialize(target, target.parent.parent)
    sys.stdout.write("extracted full source corpus and verified canonical asset copies\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
