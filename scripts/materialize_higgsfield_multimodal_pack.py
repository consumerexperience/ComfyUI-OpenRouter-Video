#!/usr/bin/env python3
"""Explicitly materialize the test-only Golden Pack; never run implicitly in tests/CI."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.golden_pack import load_default_pack  # noqa: E402

OLD_IMAGE_PACK = ROOT / "tests/live/fixtures/higgsfield_car_v1/assets"
IMAGE_FETCHER = ROOT / "scripts/fetch_higgsfield_car_v1.py"
ALLOWED_HOSTS = {"static.higgsfield.ai", "assets.mixkit.co"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _copy_existing_image(asset: dict[str, object], destination: Path) -> None:
    source = OLD_IMAGE_PACK / str(asset["local_filename"])
    if not source.is_file():
        raise FileNotFoundError(source)
    data = source.read_bytes()
    if len(data) != asset["bytes"] or _sha256(data) != asset["sha256"]:
        raise RuntimeError(f"Existing image source does not match manifest: {source}")
    if destination.exists():
        if destination.read_bytes() != data:
            raise RuntimeError(f"Refusing to replace changed Golden Pack asset: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)


def _download(asset: dict[str, object], destination: Path) -> None:
    if destination.exists():
        data = destination.read_bytes()
        if len(data) != asset["bytes"] or _sha256(data) != asset["sha256"]:
            raise RuntimeError(f"Refusing to replace changed Golden Pack asset: {destination}")
        return

    source_url = str(asset["source_url"])
    parsed = urllib.parse.urlsplit(source_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise RuntimeError(f"Golden Pack source host is not allow-listed: {parsed.hostname}")
    request = urllib.request.Request(  # noqa: S310
        source_url, headers={"Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        final_url = urllib.parse.urlsplit(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != parsed.hostname:
            raise RuntimeError("Refusing redirected download to a different host")
        data = response.read(int(asset["bytes"]) + 1)
    if len(data) != asset["bytes"] or _sha256(data) != asset["sha256"]:
        raise RuntimeError(f"Downloaded bytes do not match manifest: {asset['asset_id']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(data)
    except FileExistsError as error:
        raise RuntimeError(
            f"Refusing to replace concurrently created asset: {destination}"
        ) from error


def main() -> int:
    pack = load_default_pack()
    assets = pack.assets_by_id
    missing_images = [
        assets[asset_id]
        for asset_id in ("car_sheet", "street_environment")
        if not (pack.pack_root / assets[asset_id]["path"]).is_file()
    ]
    if missing_images and any(
        not (OLD_IMAGE_PACK / str(asset["local_filename"])).is_file() for asset in missing_images
    ):
        sys.stdout.write(
            "Materializing selected Higgsfield IMAGE sources via the existing image fetcher...\n"
        )
        subprocess.run(  # noqa: S603
            [sys.executable, str(IMAGE_FETCHER)], cwd=ROOT, check=True
        )

    for asset in pack.manifest["assets"]:
        destination = pack.pack_root / str(asset["path"])
        if asset["type"] == "IMAGE":
            _copy_existing_image(asset, destination)
        else:
            _download(asset, destination)

    verification = pack.verify_local_assets()
    if not verification.ready:
        raise RuntimeError(f"Materialization incomplete: {verification.missing_asset_ids}")
    sys.stdout.write(f"Materialized and SHA-256 verified Golden Pack: {pack.manifest_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
