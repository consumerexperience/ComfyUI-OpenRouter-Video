import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import vm from "node:vm";
import test from "node:test";

const root = new URL("../../", import.meta.url);
const source = readFileSync(new URL("web/openrouter_video.js", root), "utf8").replace(/\r\n/g, "\n");
const prefix = source.split("function widget(node, name)")[0].replace(/^import .*;\r?\n/gm, "");
const ctx = vm.createContext({ app: { graph: { _nodes: [] } }, api: {} });
vm.runInContext(prefix, ctx);
const cases = [
    [{state: "DISCONNECTED", source: "NONE"}, "Not connected"],
    [{state: "CONNECTED", source: "INTERACTIVE", persistent: true}, "Connected ✓"],
    [{state: "CONNECTED", source: "ENVIRONMENT"}, "Connected ✓"],
    [{state: "CONNECTED", source: "INTERACTIVE", persistent: false}, "Connected for this session"],
    [{state: "DISCONNECTED", source: "NONE", needs_attention: true}, "Connection needs attention"],
];
for (const [state, expected] of cases) test(`connection status: ${expected}`, () => {
    ctx.input = state;
    assert.equal(vm.runInContext("connectionLabel(input)", ctx), expected);
});

test("persistence pass preserves all node/rendering/serialization functions", () => {
    const baseline = execFileSync("git", ["show", "58c8cff:web/openrouter_video.js"], {cwd: root, encoding: "utf8"}).replace(/\r\n/g, "\n");
    const protectedPart = text => text.split("function widget(node, name)")[1]
        .replaceAll("CONNECT OPENROUTER TO LOAD VIDEO MODELS", "OpenRouter connection required")
        .replace(/            type: (?:"text"|aboutSettingRenderer),\n            defaultValue: (?:"OpenRouter Video 0.1.0-rc.1 by ARENAS®lab"|null),\n(?:            attrs: \{ readonly: true \},\n)?/, "            ABOUT_PRESENTATION_ONLY\n");
    assert.equal(protectedPart(source), protectedPart(baseline));
    assert(source.includes('summary.textContent = "Use existing API key"'));
    assert(source.includes('key.type = "password"'));
    assert(!/localStorage|sessionStorage|indexedDB|setSettingValue|setSetting\(/i.test(source));
});
