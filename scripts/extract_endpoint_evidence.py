"""Offline extraction of structured endpoint metadata from harvested official pages."""

import json
import re
from contextlib import suppress
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "docs/capability-audit"
all_records = []


def walk(value, records):
    if isinstance(value, dict):
        if "supported_video_parameters" in value and value.get("provider_name"):
            records.append(value)
        for item in value.values():
            walk(item, records)
    elif isinstance(value, list):
        for item in value:
            walk(item, records)


for file in sorted(root.glob("*.html")):
    records = []
    for encoded in re.findall(
        r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', file.read_text(encoding="utf-8")
    ):
        text = json.loads(encoded)
        for line in text.splitlines():
            fragment = line.split(":", 1)[-1]
            if fragment.startswith(("{", "[")):
                with suppress(json.JSONDecodeError):
                    walk(json.loads(fragment), records)
    unique = {json.dumps(record, sort_keys=True): record for record in records}
    all_records.append(
        {"exact_model_id": file.stem.replace("__", "/"), "endpoints": list(unique.values())}
    )
(root / "official-endpoint-profiles.json").write_text(
    json.dumps(all_records, indent=2), encoding="utf-8"
)
for record in all_records:
    print(record["exact_model_id"], len(record["endpoints"]))  # noqa: T201 - public CLI summary
