"""Opt-in synthetic OS-vault restart probe; never reads the product credential entry."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

CHILD = """
import sys
from openrouter_video.credential_backend import secure_backend
backend = secure_backend()
service, action = sys.argv[1:]
account = "synthetic-restart-probe"
canary = "TEST_ONLY_NON_PROVIDER_CREDENTIAL"
if action == "save":
    assert backend.get_password(service, account) is None
    backend.set_password(service, account, canary)
elif action == "restore":
    assert backend.get_password(service, account) == canary
elif action == "remove":
    if backend.get_password(service, account) is not None:
        backend.delete_password(service, account)
    assert backend.get_password(service, account) is None
"""


def main() -> int:
    service = "OpenRouterVideo-TEST-ONLY-" + uuid.uuid4().hex
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    success = True
    try:
        for action in ("save", "restore"):
            result = subprocess.run(  # noqa: S603
                [sys.executable, "-c", CHILD, service, action],
                env=env,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                success = False
                break
    finally:
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", CHILD, service, "remove"],
            env=env,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            success = False
    sys.stdout.write(
        "OS_VAULT_RESTART=PASS; SYNTHETIC_ENTRY_CLEANUP=PASS; PAID_POST_COUNT=0\n"
        if success
        else "OS_VAULT_RESTART=FAIL (details suppressed)\n"
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
