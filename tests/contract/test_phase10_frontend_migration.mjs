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

test("presentation order keeps reference summary above Model and Advanced above its controls", () => {
    const target = node();
    target.__orvSummary = { name: "REFERENCES" };
    target.__orvAdvanced = { name: "Advanced" };
    target.widgets.push(target.__orvAdvanced, target.__orvSummary);
    const originalArray = target.widgets;
    context.orderPresentationWidgets(target);
    assert.equal(target.widgets, originalArray);
    assert.deepEqual(
        Array.from(target.widgets, (item) => item.name),
        [
            "REFERENCES", "model", "inference_method", "prompt", "resolution",
            "aspect_ratio", "duration", "seed", "generate_audio", "Advanced",
            "size", "control after generate", "first_frame_url", "last_frame_url",
        ],
    );
});

test("primary control sizing preserves original widget measurement and visibility", () => {
    const prompt = { name: "prompt", hidden: false, computeSize: () => [320, 42] };
    context.setMinimumWidgetHeight(prompt, 92);
    assert.deepEqual(Array.from(prompt.computeSize()), [320, 92]);
    context.setVisible(prompt, false);
    assert.deepEqual(Array.from(prompt.computeSize()), [0, -4]);
    context.setVisible(prompt, true);
    assert.deepEqual(Array.from(prompt.computeSize()), [320, 92]);
});

test("Prompt styling is scoped to this Generate widget", () => {
    const target = node();
    const prompt = target.widgets.find((item) => item.name === "prompt");
    prompt.element = { placeholder: "prompt", style: {} };
    context.stylePrompt(target);
    assert.equal(prompt.element.placeholder, "Prompt");
    assert.equal(prompt.element.style.borderRadius, "9px");
    assert.equal(target.widgets.find((item) => item.name === "model").element, undefined);
});

test("named Phase 10 values win over presentation positions", () => {
    const target = node();
    const named = {
        model: "exact/model-id", inference_method: "MI2V", prompt: "saved prompt",
        resolution: "720p", aspect_ratio: "16:9", duration: 5,
        seed: 77, generate_audio: true, "control after generate": "fixed",
    };
    assert.equal(context.restorePhase10NamedValues(target, named), true);
    const values = Object.fromEntries(target.widgets.map(({ name, value }) => [name, value]));
    assert.equal(values.model, "exact/model-id");
    assert.equal(values.inference_method, "MI2V");
    assert.equal(values.prompt, "saved prompt");
    assert.equal(values.duration, 5);
    assert.equal(values["control after generate"], "fixed");
});

test("prior Phase 10 positional values restore by field after presentation reorder", () => {
    const target = node();
    const saved = [
        "exact/model-id", "MI2V", "saved prompt", "720p", "16:9", 5,
        "", 77, "fixed", true, "", "",
    ];
    assert.equal(context.restorePhase10Values(target, saved), true);
    const values = Object.fromEntries(target.widgets.map(({ name, value }) => [name, value]));
    assert.equal(values.model, "exact/model-id");
    assert.equal(values.inference_method, "MI2V");
    assert.equal(values.prompt, "saved prompt");
    assert.equal(values.duration, 5);
    assert.equal(values.seed, 77);
    assert.equal(values["control after generate"], "fixed");
    assert.equal(values.generate_audio, true);
});

test("new presentation order restores the same intent on reload", () => {
    const target = node();
    const saved = [
        "2 connected · 48 remaining", "exact/model-id", "MI2V", "saved prompt",
        "720p", "16:9", 5, 77, true, "›", "", "fixed", "", "",
    ];
    assert.equal(context.restorePhase10Values(target, saved), true);
    const values = Object.fromEntries(target.widgets.map(({ name, value }) => [name, value]));
    assert.equal(values.model, "exact/model-id");
    assert.equal(values.inference_method, "MI2V");
    assert.equal(values.prompt, "saved prompt");
    assert.equal(values.duration, 5);
    assert.equal(values.seed, 77);
    assert.equal(values["control after generate"], "fixed");
    assert.equal(values.generate_audio, true);
});

test("visible reference sockets lead hidden widget inputs and preserve link slots", () => {
    const target = {
        id: 42,
        inputs: [
            { name: "model", type: "COMBO", link: null },
            { name: "prompt", type: "STRING", link: null },
            { name: "direct_references.reference_0", type: "OPENROUTER_VIDEO_INPUT_REFERENCE", link: 7 },
        ],
        addInput(name, type) { this.inputs.push({ name, type, link: null }); },
        removeInput(index) { this.inputs.splice(index, 1); },
    };
    context.app.graph = {
        links: { 7: { target_id: 42, target_slot: 2, origin_id: 9 } },
        getNodeById(id) { return id === 9 ? { type: "OpenRouterVideoImageReference" } : null; },
    };
    context.configureReferenceTopology(target, { max_reference_count: 2 }, "MI2V");
    assert.deepEqual(
        Array.from(target.inputs.slice(0, 2), ({ name, label }) => [name, label]),
        [
            ["direct_references.reference_0", "image_1"],
            ["direct_references.reference_1", "image_2"],
        ],
    );
    assert.equal(context.app.graph.links[7].target_slot, 0);
    assert.equal(target.__orvReferenceSummary, "1 connected · 1 remaining");

    target.inputs[1].link = 8;
    context.app.graph.links[8] = { target_id: 42, target_slot: 1, origin_id: 9 };
    context.configureReferenceTopology(target, { max_reference_count: 2 }, "MI2V");
    assert.equal(target.inputs.filter((item) => item.name.startsWith("direct_references.")).length, 2);
    assert.equal(target.__orvReferenceSummary, "2 connected · maximum reached");
    assert.equal(context.app.graph.links[7].target_slot, 0);
    assert.equal(context.app.graph.links[8].target_slot, 1);
});

test("native Load Image is recognized as IMAGE while existing URL helper remains valid", () => {
    const target = {
        id: 43,
        inputs: [],
        addInput(name, type) { this.inputs.push({ name, type, link: null }); },
        removeInput(index) { this.inputs.splice(index, 1); },
    };
    context.app.graph = {
        links: { 11: { target_id: 43, origin_id: 12, origin_slot: 0, type: "IMAGE" } },
        getNodeById(id) {
            return id === 12 ? { type: "LoadImage", outputs: [{ type: "IMAGE" }] } : null;
        },
    };
    context.configureReferenceTopology(target, { max_reference_count: 2 }, "MI2V");
    assert.equal(target.inputs[0].type, "IMAGE,VIDEO,AUDIO,OPENROUTER_VIDEO_INPUT_REFERENCE");
    target.inputs[0].link = 11;
    context.configureReferenceTopology(target, { max_reference_count: 2 }, "MI2V");
    assert.equal(context.connectedReferenceKind(target.inputs[0]), "image");
    assert.equal(target.__orvReferenceInvalid, false);
    assert.equal(target.inputs[1].label, "image_2");
});
