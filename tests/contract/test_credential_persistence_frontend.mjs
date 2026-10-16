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
    [{state: "DISCONNECTED", source: "NONE"}, "OpenRouter isn’t connected"],
    [{state: "CONNECTED", source: "INTERACTIVE", persistent: true}, "OpenRouter — Connected ✓"],
    [{state: "CONNECTED", source: "ENVIRONMENT"}, "OpenRouter — Connected ✓ · Managed by environment"],
    [{state: "CONNECTED", source: "INTERACTIVE", persistent: false}, "OpenRouter — Connected for this session · Reconnect after restart"],
    [{state: "DISCONNECTED", source: "NONE", needs_attention: true}, "OpenRouter connection needs attention. Reconnect to continue."],
];
for (const [state, expected] of cases) test(`connection status: ${expected}`, () => {
    ctx.input = state;
    assert.equal(vm.runInContext("connectionLabel(input)", ctx), expected);
});

test("persistence pass preserves all node/rendering/serialization functions", () => {
    const baseline = execFileSync("git", ["show", "796697a:web/openrouter_video.js"], {cwd: root, encoding: "utf8"}).replace(/\r\n/g, "\n");
    assert.equal(source.split("function widget(node, name)")[1], baseline.split("function widget(node, name)")[1]);
    assert(source.includes('summary.textContent = "Use existing API key"'));
    assert(source.includes('key.type = "password"'));
    assert(!/localStorage|sessionStorage|indexedDB|setSettingValue|setSetting\(/i.test(source));
});
