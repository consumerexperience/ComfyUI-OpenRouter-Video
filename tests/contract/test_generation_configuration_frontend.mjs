import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const source = readFileSync(resolve(root, "web/openrouter_video.js"), "utf8").replace(/^import .*;\r?\n/gm, "");
const context = { app: { registerExtension() {} }, api: {} };
vm.runInNewContext(source, context);
const plain = (value) => JSON.parse(JSON.stringify(value));
const domains = {
    supported_resolutions: ["720p", "1080p"], supported_aspect_ratios: ["16:9", "9:16"],
    supported_durations: [4, 8], supported_sizes: null,
};
const rules = [{
    axes: ["resolution", "aspect_ratio", "duration"], when: {}, complete: true,
    allowed: [
        { resolution: ["720p"], aspect_ratio: ["16:9"], duration: [4, 8] },
        { resolution: ["720p"], aspect_ratio: ["9:16"], duration: [4] },
        { resolution: ["1080p"], aspect_ratio: ["16:9"], duration: [4] },
    ], forbidden: [],
}];

test("independent parameters preserve the existing Cartesian availability", () => {
    const result = plain(context.configurationOptions(domains, { resolution: "1080p", aspect_ratio: "9:16", duration: 8 }, {}));
    assert.equal(result.status, "READY");
    assert.deepEqual(result.options.duration, [4, 8]);
    assert.deepEqual(result.options.aspect_ratio, ["9:16", "16:9"]);
});

test("Resolution and Aspect Ratio immediately constrain remaining values", () => {
    const capability = { ...domains, configuration_relations: rules };
    const high = plain(context.configurationOptions(capability, { resolution: "1080p" }, {}));
    assert.deepEqual(high.options.aspect_ratio, ["16:9"]);
    assert.deepEqual(high.options.duration, [4]);
    const portrait = plain(context.configurationOptions(capability, { resolution: "720p", aspect_ratio: "9:16" }, {}));
    assert.deepEqual(portrait.options.duration, [4]);
});

test("invalid saved intent remains repairable without creating a false tuple", () => {
    const result = plain(context.configurationOptions({ ...domains, configuration_relations: rules }, { resolution: "720p", aspect_ratio: "9:16", duration: 8 }, {}));
    assert.equal(result.status, "CONFIRMED_INCOMPATIBLE");
    assert.deepEqual(result.options.duration, [4]);
    assert.deepEqual(result.options.aspect_ratio, ["16:9"]);
});

test("known incomplete coupling fails closed only for the specific unknown tuple", () => {
    const relation = [{ ...rules[0], complete: false }];
    assert.equal(context.configurationStatus(relation, { resolution: "1080p", aspect_ratio: "9:16", duration: 8 }, {}), "UNKNOWN_COMBINATION");
    assert.equal(context.configurationStatus(relation, { resolution: "720p", aspect_ratio: "16:9", duration: 8 }, {}), "READY");
});

test("method and mode scopes reproject without a model-specific branch", () => {
    for (const key of ["inference_method", "mode"]) {
        const capability = { ...domains, configuration_relations: [{ ...rules[0], when: { [key]: ["selected"] } }] };
        assert.deepEqual(plain(context.configurationOptions(capability, { resolution: "1080p" }, { [key]: "selected" })).options.duration, [4]);
        assert.deepEqual(plain(context.configurationOptions(capability, { resolution: "1080p" }, { [key]: "other" })).options.duration, [4, 8]);
    }
});

test("future relation-only model gets options without adding an ID to UI code", () => {
    const capability = { model_id: "synthetic/future-only", configuration_relations: rules };
    const result = plain(context.configurationOptions(capability, { resolution: "1080p" }, {}));
    assert.deepEqual(result.options.aspect_ratio, ["16:9"]);
    assert.deepEqual(result.options.duration, [4]);
});

test("Duration is a real combo and incompatible numeric intent is preserved", () => {
    const previous = { name: "duration", type: "number", value: 6, serializeValue() { return this.value; } };
    const target = {
        widgets: [previous],
        __orvCapabilityStatus: { value: "" },
        addWidget(type, name, value, callback, options) {
            const created = { type, name, value, callback, options };
            this.widgets.push(created);
            return created;
        },
    };
    context.createGeometryCombos(target);
    assert.equal(target.widgets.length, 1);
    assert.equal(target.widgets[0].type, "combo");
    assert.equal(target.widgets[0].serializeValue(), 6);
    context.configureDuration(target, [4, 8]);
    assert.equal(target.widgets[0].value, 6);
    assert.equal(target.widgets[0].type, "combo");
    assert.match(target.__orvCapabilityStatus.value, /incompatible saved value preserved/);
    target.widgets[0].value = 4;
    context.configureDuration(target, [4, 8]);
    assert.equal(target.widgets[0].type, "combo");
    assert.deepEqual(plain(target.widgets[0].options.values), [0, 4, 8]);
});

test("every current model retains its real structured axis options", () => {
    const catalogue = JSON.parse(readFileSync(resolve(root, "docs/adaptive-generation-controls/evidence/live-catalogue.json"), "utf8"));
    const keys = { resolution: "supported_resolutions", aspect_ratio: "supported_aspect_ratios", duration: "supported_durations", size: "supported_sizes" };
    for (const model of catalogue.payload.data) {
        const result = plain(context.configurationOptions(model, {}, {}));
        assert.equal(result.status, "READY", model.id);
        for (const [axis, key] of Object.entries(keys)) assert.deepEqual(result.options[axis], plain(context.canonicalOptions(axis, model[key] ?? null)), `${model.id}: ${axis}`);
    }
});

const orderCases = JSON.parse(readFileSync(resolve(root, "tests/fixtures/configuration_option_order.json"), "utf8"));
for (const record of orderCases) test(`canonical ${record.axis} order: ${JSON.stringify(record.input)}`, () => {
    const before = [...record.input];
    assert.deepEqual(plain(context.canonicalOptions(record.axis, record.input)), record.expected);
    assert.deepEqual(record.input, before);
});

test("reprojection preserves selected wire value and sentinel label", () => {
    const resolution = { name: "resolution", value: "720p", options: {} };
    const duration = { name: "duration", value: 0, options: {} };
    const node = { widgets: [resolution, duration], __orvCapabilityStatus: { value: "" } };
    context.configureEnum(node, resolution, ["4K", "720p", "480p"], "RESOLUTION");
    assert.equal(resolution.value, "720p");
    assert.deepEqual(plain(resolution.options.values), ["AUTO / MODEL DEFAULT", "480p", "720p", "4K"]);
    const saved = JSON.stringify(node.widgets.map(w => w.value));
    context.configureEnum(node, resolution, ["720p", "1080p"], "RESOLUTION");
    assert.equal(JSON.stringify(node.widgets.map(w => w.value)), saved);
    context.configureDuration(node, [8, 4, 6]);
    assert.equal(duration.value, 0);
    assert.equal(duration.options.getOptionLabel(0), "AUTO / MODEL DEFAULT");
    assert.equal(duration.options.getOptionLabel("0"), "AUTO / MODEL DEFAULT");
    assert.equal(duration.options.getOptionLabel(null), "AUTO / MODEL DEFAULT");
    assert.equal(duration.options.getOptionLabel(4), "4");
    assert.deepEqual(plain(duration.options.values), [0, 4, 6, 8]);
    resolution.value = "2K";
    context.configureEnum(node, resolution, ["720p", "480p"], "RESOLUTION");
    assert.equal(resolution.value, "2K");
    assert.match(node.__orvCapabilityStatus.value, /Generate blocked/);
});
