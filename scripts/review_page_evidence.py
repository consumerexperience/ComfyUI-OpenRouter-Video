import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "docs/capability-audit"
records = []
for file in sorted(root.glob("*.html")):
    for text in re.findall(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        file.read_text(encoding="utf-8"),
        re.S,
    ):
        data = json.loads(text)
        if isinstance(data, dict) and "featureList" in data:
            records.append(
                {
                    "exact_model_id": file.stem.replace("__", "/"),
                    "description": data.get("description"),
                    "features": data["featureList"],
                    "source_url": "https://openrouter.ai/" + file.stem.replace("__", "/"),
                    "authority": "EXACT_OFFICIAL_MODEL_PAGE",
                }
            )
            print(file.stem, data.get("description"), data["featureList"])  # noqa: T201
(root / "official-page-profiles.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
