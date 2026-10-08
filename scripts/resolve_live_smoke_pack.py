#!/usr/bin/env python3
"""Resolve and verify the selected fixture input for a separately gated live smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures.golden_pack import (  # noqa: E402
    MATERIALIZATION_COMMAND,
    GoldenPackError,
    load_default_pack,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden-pack", default="default", choices=("default",), help="test-only pack selector"
    )
    args = parser.parse_args()
    try:
        pack = load_default_pack(selector=args.golden_pack)
        verification = pack.verify_local_assets()
    except GoldenPackError as error:
        sys.stdout.write(json.dumps({"state": "INVALID", "error": str(error)}, indent=2) + "\n")
        return 1

    result = {
        "state": "READY_FOR_SEPARATELY_GATED_LIVE_SMOKE"
        if verification.ready
        else verification.state,
        "pack_id": pack.pack_id,
        "manifest": str(pack.manifest_path.relative_to(ROOT)),
        "ordered_inputs": [
            {
                "position": ref["position"],
                "type": ref["type"],
                "filename": ref["local_filename"],
                "sha256": ref["sha256"],
                "roles": ref["roles"],
                "transport": ref["transport"],
            }
            for ref in pack.canonical_references
        ],
        "network_requests_sent": 0,
        "paid_post_count": 0,
        "execution_note": (
            "Input resolution only; live capability validation and immediate Product Owner "
            "approval remain separate gates."
        ),
    }
    if not verification.ready:
        result["missing_asset_ids"] = verification.missing_asset_ids
        result["materialization_command"] = MATERIALIZATION_COMMAND
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
        return 2
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
