"""Extend the existing manual fixture host for zero-cost Native Media UI proof.
No canonical DEV process is managed. Child environment has only OS variables.
"""

# mypy: ignore-errors
from __future__ import annotations

import argparse
import os
import socket
import subprocess
from pathlib import Path

SYNTHETIC_MEDIA = """
import sys, wave
from pathlib import Path
import av
import numpy as np
from PIL import Image
root=Path(sys.argv[1])
Image.new('RGB',(16,16),(30,100,140)).save(root/'synthetic.png')
with wave.open(str(root/'synthetic.wav'),'wb') as output:
    output.setnchannels(1);output.setsampwidth(2);output.setframerate(8000)
    output.writeframes(b'\\x00\\x00'*800)
with av.open(str(root/'synthetic.mp4'),'w',format='mp4') as output:
    stream=output.add_stream('libx264',rate=2)
    stream.width=16;stream.height=16;stream.pix_fmt='yuv420p'
    for _ in range(2):
        frame=av.VideoFrame.from_ndarray(np.zeros((16,16,3),dtype=np.uint8),format='rgb24')
        for packet in stream.encode(frame):output.mux(packet)
    for packet in stream.encode():output.mux(packet)
"""

WRAPPER = """
import importlib.util
from pathlib import Path
import sys
repo = Path(REPOSITORY)
sys.path.insert(0,str(repo/'src'))
from openrouter_video.comfy import extension, nodes, routes
from openrouter_video.application import GenerateService
from openrouter_video.capabilities import CapabilityService, RequestValidator
from openrouter_video.local_media import NativeMediaError
from openrouter_video.persistence import JobStore
from openrouter_video.s3_upload import S3MediaUploader, StorageSecretProvider, StorageError
from openrouter_video.staging import StagingManager
from openrouter_video.media import DownloadService
from openrouter_video.models import ModelCapabilities
spec=importlib.util.spec_from_file_location(
    'phase9_fixture',repo/'tests/manual/phase9_fixture_custom_node/__init__.py'
)
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
fixture._fixture_models=lambda:(ModelCapabilities(model_id='bytedance/seedance-2.5'),)
class MissingStorage(StorageSecretProvider):
    def resolve(self):
        raise StorageError('Configure local S3 endpoint, region, bucket and credentials.')
class NoNetwork:
    async def submit_video(self,request): raise AssertionError('fixture must never submit')
    async def get_job(self,job_id): raise AssertionError('fixture must never poll')
class Runtime(fixture._FixtureRuntime):
    async def generate(self,request,node_id):
        store=JobStore(Path(STATE)/'jobs.sqlite3');client=NoNetwork()
        service=GenerateService(
            capabilities=CapabilityService(client=fixture._FixtureDiscovery(),store=store),
            validator=RequestValidator(),store=store,submit_client=client,
            observation_client=client,
            downloader=DownloadService(client=client,output_root=Path(STATE)/'output'),
            staging=StagingManager(store,S3MediaUploader(MissingStorage())),
        )
        return await service.generate('fixture-operation',request)
runtime=Runtime()
for module in (extension,nodes,routes): module.__dict__['get_runtime']=lambda:runtime
WEB_DIRECTORY=str(repo/'web')
async def comfy_entrypoint(): return extension.OpenRouterVideoExtension()
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--deps", type=Path, required=True)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.port is not None and not 49152 <= args.port <= 65535:
        parser.error("Fixture port must be in the ephemeral test range.")
    repo = Path(__file__).resolve().parents[2]
    base = repo / "output/playwright/native-fixture"
    custom = base / "custom_nodes" / "native_fixture"
    custom.mkdir(parents=True, exist_ok=True)
    for folder in ("input", "output", "user", "temp"):
        (base / folder).mkdir(exist_ok=True)
    custom.joinpath("__init__.py").write_text(
        "REPOSITORY=" + repr(str(repo)) + "\nSTATE=" + repr(str(base / "user")) + "\n" + WRAPPER,
        encoding="utf-8",
    )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", args.port or 0))
        port = sock.getsockname()[1]
    env = {
        name: os.environ[name]
        for name in (
            "SystemRoot",
            "WINDIR",
            "PATH",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
        )
        if name in os.environ
    }
    env["PYTHONPATH"] = (
        str(args.deps.resolve()) + os.pathsep + str(repo.parent / ".tmp/phase9-comfy-deps")
    )
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run(  # noqa: S603 - explicit fixture interpreter and synthetic source
        [str(args.python.resolve()), "-c", SYNTHETIC_MEDIA, str(base / "input")],
        check=True,
        env=env,
    )
    cmd = [
        str(args.python.resolve()),
        str(args.host.resolve() / "main.py"),
        "--cpu",
        "--listen",
        "127.0.0.1",
        "--port",
        str(port),
        "--base-directory",
        str(base),
        "--database-url",
        "sqlite:///:memory:",
        "--disable-all-custom-nodes",
        "--whitelist-custom-nodes",
        "native_fixture",
        "--disable-auto-launch",
        "--disable-api-nodes",
    ]
    (base.parent / "fixture-port.txt").write_text(str(port), encoding="utf-8")
    print("ISOLATED FIXTURE PORT " + str(port), flush=True)  # noqa: T201
    child = subprocess.Popen(cmd, env=env, cwd=args.host.resolve())  # noqa: S603 - explicit test paths
    try:
        raise SystemExit(child.wait())
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait()


if __name__ == "__main__":
    main()
