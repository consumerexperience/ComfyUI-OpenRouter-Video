import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import vm from "node:vm";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const source = readFileSync(resolve(root, "web/openrouter_video.js"), "utf8")
    .replace(/^import .*;\r?\n/gm, "");
const context = { app: { registerExtension() {} }, api: {} };
vm.runInNewContext(source, context, { filename: "openrouter_video.js" });

function node() {
    const names = [
        "model", "inference_method", "prompt", "resolution", "aspect_ratio",
        "duration", "size", "seed", "control after generate", "generate_audio",
        "first_frame_url", "last_frame_url",
    ];
    return { widgets: names.map((name) => ({ name, value: name === "model" ? "SELECT MODEL" : null })) };
}

test("Phase 8 remote-options values restore by field, not Phase 10 widget position", () => {
    const target = node();
    const legacy = [
        "exact/model-id", false, "refresh", "saved prompt", "6", "480p",
        "16:9", "", "77", "randomize", true, "https://example.test/first.png", "",
    ];
    assert.equal(context.restorePhase8RemoteOptionsValues(target, legacy), true);
    const values = Object.fromEntries(target.widgets.map(({ name, value }) => [name, value]));
    assert.equal(values.model, "exact/model-id");
    assert.equal(values.inference_method, null);
    assert.equal(values.prompt, "saved prompt");
    assert.equal(values.duration, "6");
    assert.equal(values.resolution, "480p");
    assert.equal(values.aspect_ratio, "16:9");
    assert.equal(values.seed, "77");
    assert.equal(values["control after generate"], "randomize");
    assert.equal(values.generate_audio, true);
    assert.equal(values.first_frame_url, "https://example.test/first.png");
});

test("unresolved numeric legacy model stays unresolved", () => {
    const target = node();
    const legacy = [
        0, false, "refresh", "saved prompt", 5, "480", "adaptive", "",
        791669044, "randomize", true, "", "",
    ];
    assert.equal(context.restorePhase8RemoteOptionsValues(target, legacy), true);
    const values = Object.fromEntries(target.widgets.map(({ name, value }) => [name, value]));
    assert.equal(values.model, "SELECT MODEL");
    assert.equal(values.prompt, "saved prompt");
    assert.equal(values.duration, 5);
    assert.equal(values.seed, 791669044);
    assert.equal(values.generate_audio, true);
});
