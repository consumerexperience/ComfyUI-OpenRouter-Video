"""Render six offline review states from actual connection UI source (no provider data)."""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "web/openrouter_video.js").read_text(encoding="utf-8")
prefix = "\n".join(
    line
    for line in source.split("function widget(node, name)")[0].splitlines()
    if not line.startswith("import ")
)
cases = [
    ("1. Disconnected", {"state": "DISCONNECTED", "source": "NONE"}, False),
    (
        "2. OAuth Connect flow (local dialog; consent not simulated)",
        {"state": "DISCONNECTED", "source": "NONE"},
        True,
    ),
    (
        "3. Connected persistent",
        {"state": "CONNECTED", "source": "INTERACTIVE", "persistent": True},
        False,
    ),
    (
        "4. Settings Connected",
        {"state": "CONNECTED", "source": "INTERACTIVE", "persistent": True},
        False,
    ),
    (
        "5. Settings Managed by environment",
        {"state": "CONNECTED", "source": "ENVIRONMENT", "persistent": False},
        False,
    ),
    (
        "6. Settings Session only fallback",
        {"state": "CONNECTED", "source": "INTERACTIVE", "persistent": False},
        False,
    ),
]
style = "body{background:#171b1d;color:#e4ece9;font:15px system-ui;padding:24px}button{cursor:pointer;padding:8px}h2{font-size:18px}iframe{width:100%;height:300px;border:1px solid #536560;border-radius:8px}section{break-inside:avoid;margin:20px 0}"  # noqa: E501
sections = []
for title, state, modal in cases:
    setup = (
        "const app={graph:{_nodes:[]}}; const api={fetchApi:async()=>({ok:true,json:async()=>("
        + json.dumps(state)
        + ")})};"
    )
    body = (
        "<h3>OpenRouter Video → Connection</h3><script>"
        + setup
        + prefix
        + ";document.body.append(connectionSettingRenderer());"
        + ("showConnectionPanel();" if modal else "")
        + "</script>"
    )
    frame = "<!doctype html><style>" + style + "</style>" + body
    sections.append(
        "<section><h2>"
        + html.escape(title)
        + '</h2><iframe srcdoc="'
        + html.escape(frame, quote=True)
        + '"></iframe></section>'
    )
out = ROOT / "output/playwright/credential-persistence"
out.mkdir(parents=True, exist_ok=True)
(out / "review.html").write_text(
    "<!doctype html><meta charset=utf-8><title>Connection UI review fixtures</title><style>"
    + style
    + "</style><h1>Connection UI review fixtures</h1><p>Offline UI only. No real account, provider credential, OAuth consent, or live ComfyUI evidence.</p>"  # noqa: E501
    + "".join(sections),
    encoding="utf-8",
)
