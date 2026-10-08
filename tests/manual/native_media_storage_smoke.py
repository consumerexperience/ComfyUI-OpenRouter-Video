"""Human-run, separately approved storage smoke. Never run by pytest or CI."""

from __future__ import annotations

import argparse
import asyncio
import secrets
import sys
import tempfile
import wave
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openrouter_video.s3_upload import S3MediaUploader, StorageError  # noqa: E402


async def smoke() -> None:
    uploader = S3MediaUploader()
    fingerprint = uploader.configuration_fingerprint()
    key = "openrouter-video/staging/" + secrets.token_hex(16) + ".wav"
    with tempfile.TemporaryDirectory(prefix="native-storage-smoke-") as temporary:
        path = Path(temporary) / "synthetic.wav"
        with wave.open(str(path), "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(8000)
            file.writeframes(b"\x00\x00" * 800)
        try:
            await uploader.upload(key, path, "audio/wav")
            url = await uploader.presign_get(key)
            async with httpx.AsyncClient(
                follow_redirects=False, trust_env=False, timeout=30
            ) as client:
                response = await client.get(url)
            if response.status_code != 200 or response.content != path.read_bytes():
                raise StorageError("Signed GET did not reproduce synthetic media.")
        finally:
            if uploader.configuration_fingerprint() != fingerprint:
                raise StorageError(
                    "Storage configuration changed; cleanup requires original settings."
                )
            await uploader.delete(key)
        # The same presigned URL must no longer retrieve the exact deleted object.
        # Keep it in memory only; no bucket listing or additional cloud resource.
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=30) as client:
            absent = await client.get(url)
        if absent.status_code != 404:
            raise StorageError(
                "Deleted storage object is still retrievable or cleanup is unverified."
            )
    print(  # noqa: T201
        "PASS: synthetic PUT, signed GET without authentication headers, exact DELETE and absence"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--execute", action="store_true", help="Run only after explicit storage-smoke approval"
    )
    args = parser.parse_args()
    if not args.execute:
        parser.error("Explicit storage-smoke approval required; use --execute only after approval.")
    try:
        asyncio.run(smoke())
    except Exception:
        raise SystemExit(
            "Storage smoke failed; check local settings and exact-object cleanup."
        ) from None


if __name__ == "__main__":
    main()
