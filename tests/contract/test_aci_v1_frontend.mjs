import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../../web/openrouter_video.js", import.meta.url), "utf8")
    .replace(/^import .*;\r?\n/gm, "");
const fixture = JSON.parse(readFileSync(new URL("../fixtures/capability-audit-ui-projection.json", import.meta.url), "utf8"));
const model = fixture.models.find(item => item.model_id === "bytedance/seedance-2.5");

function harness(selectedModel = model) {
    const requests = [];
    const graph = { links: {}, nodes: {}, getNodeById(id) { return this.nodes[id]; } };
    const c = {
        app: { graph, registerExtension() {} },
        api: { fetchApi(url, init) {
            return new Promise(resolve => requests.push({ url, body: JSON.parse(init.body), resolve }));
        } },
        performance: { now: () => 0 }, clearTimeout() {}, setTimeout() { return 0; },
    };
    vm.runInNewContext(source, c);
    const values = { model: selectedModel.model_id, inference_method: "T2V", prompt: "never sent to estimator",
        resolution: "720p", aspect_ratio: "16:9", duration: 10, size: "", seed: 42,
        generate_audio: false, geometry_authority: "NORMALIZED", "control after generate": "fixed" };
    const n = { id: 42, size: [400, 450], properties: {}, __orvEstimate: { value: "" },
        __orvCapabilityStatus: { value: "" },
        widgets: Object.entries(values).map(([name, value]) => ({ name, value, options: {}, computeSize: () => [0, 20] })),
        inputs: [], addInput(name, type) { this.inputs.push({ name, type, link: null }); },
        removeInput(index) { this.inputs.splice(index, 1); }, setDirtyCanvas() {},
        computeSize() { return [400, 200]; }, setSize(size) { this.size = size; } };
    n.__orvModelCapability = selectedModel;
    const selected = c.configureInferenceMethod(n, selectedModel);
    c.reprojectNodeSemantics(n, selectedModel, selected, { cause: "catalogue" });
    return { c, n, requests };
}
function respond(request, result) {
    request.resolve({ ok: true, async json() { return { valid_for_ms: 900000, ...result, context_revision: request.body.context_revision }; } });
}

for (const [state, fields, label] of [
    ["FORMULA", { amount_usd: "2.3112", estimated_cost_usd: "2.3112", availability: "AVAILABLE" }, /2\.31.*EST/],
    ["RANGE", { lower_usd: "0.8", upper_usd: "1.2" }, /0\.80.*1\.20.*EST/],
    ["RATE_ONLY", { rate_usd: "0.03", rate_unit: "s" }, /^COST$/],
    ["RATE_ONLY", { rate_usd: "0.0000064", rate_unit: "token" }, /^COST$/],
    ["PARTIAL", {}, /COST/], ["UNKNOWN", {}, /COST/],
    ["STALE", {}, /COST/], ["INVALID", {}, /CHECK INPUTS/],
]) {
    test(`ACI ${state} has an explicit native badge state`, async () => {
        const { c, n, requests } = harness();
        const pending = c.refreshEstimate(n);
        assert.equal(requests.length, 1);
        respond(requests[0], { state, ...fields, reason_codes: ["test_reason"] });
        await pending;
        assert.match(n.__orvEstimate.value, label);
        assert(!n.__orvEstimate.value.includes("undefined"));
    });
}

test("ACI older response arriving last cannot replace newer revision", async () => {
    const { c, n, requests } = harness();
    const old = c.refreshEstimate(n);
    n.widgets.find(item => item.name === "duration").value = 5;
    const current = c.refreshEstimate(n);
    assert.equal(requests.length, 2);
    respond(requests[1], { state: "FORMULA", availability: "AVAILABLE", amount_usd: "1.15", estimated_cost_usd: "1.15" });
    await current;
    const accepted = n.__orvEstimate.value;
    respond(requests[0], { state: "FORMULA", availability: "AVAILABLE", amount_usd: "9.99", estimated_cost_usd: "9.99" });
    await old;
    assert.equal(n.__orvEstimate.value, accepted);
    assert(!n.__orvEstimate.value.includes("9.99"));
});

test("ACI cost payload excludes prompt, seeds, paths and credentials", async () => {
    const { c, n, requests } = harness();
    const pending = c.refreshEstimate(n);
    const { body, url } = requests[0];
    assert.equal(url, "/openrouter-video/v1/cost-estimate");
    for (const key of ["prompt", "seed", "api_key", "path", "url", "filename", "node_id"])
        assert(!Object.hasOwn(body, key), key);
    respond(requests[0], { state: "UNKNOWN" });
    await pending;
});

test("ACI native badge glyphs remain exact Unicode", () => {
    const { c } = harness();
    assert.equal(c.costBadgeText({ state: "FORMULA", amount_usd: "2.3112" }), "\u2248 $2.31 EST.");
    assert.equal(c.costBadgeText({ state: "RANGE", lower_usd: "0.8", upper_usd: "1.2" }), "\u2248 $0.80\u20131.20 EST.");
    assert.equal(c.costBadgeText({ state: "CALCULATING" }), "CALCULATING\u2026");
});

test("ACI collapsed Classic retains badge without changing node geometry", () => {
    const { c, n } = harness();
    n.flags = { collapsed: true };
    n._collapsed_width = 300;
    n.__orvEstimate.value = "COST";
    const before = [...n.size];
    const drawn = [];
    const ctx = { save() {}, restore() {}, fillRect() {}, fillText(text) { drawn.push(text); } };
    c.drawCollapsedCostBadge(n, ctx);
    assert.deepEqual(Array.from(n.size), before);
    assert.deepEqual(drawn, ["COST"]);
});

test("ACI reads active loaded DOM scalars as HINT and refines without media fetch", () => {
    const { c, n, requests } = harness();
    class Media {
        constructor() { this.tagName = "VIDEO"; this.readyState = 1; this.duration = 7.5;
            this.videoWidth = 1920; this.videoHeight = 1080; this.events = new Map(); }
        get src() { throw new Error("cost metadata must never read media URLs"); }
        get currentSrc() { throw new Error("cost metadata must never read media URLs"); }
        addEventListener(name, callback) { this.events.set(name, callback); }
        removeEventListener(name) { this.events.delete(name); }
    }
    c.HTMLMediaElement = Media;
    c.HTMLImageElement = class {};
    const element = new Media();
    const input = { name: "source_video", type: "VIDEO", link: 303 };
    n.inputs = [input];
    c.app.graph.nodes[901] = { outputs: [{ type: "VIDEO" }], widgets: [{ element }] };
    c.app.graph.links[303] = { origin_id: 901, origin_slot: 0, target_id: n.id, target_slot: 0, type: "VIDEO" };
    const profile = n.__orvCapability.__methodProfile;
    profile.topology = { ...profile.topology, fixed: ["source_video"] };
    const metadata = c.readNativeCostMetadata(n, { input, kind: "video", role: "source_video" });
    assert.deepEqual(JSON.parse(JSON.stringify(metadata)), {
        kind: "video", role: "source_video", status: "HINT", duration_seconds: "7.5", width: 1920, height: 1080,
    });
    assert.equal(requests.length, 0);
    assert(!/path|url|filename|node_id|src/i.test(JSON.stringify(metadata)));
    const before = n.__orvEstimateRevision || 0;
    element.duration = 8;
    element.events.get("durationchange")();
    assert.equal(n.__orvEstimateRevision, before + 1);
    assert.equal(n.__orvEstimate.value, "CALCULATING\u2026");
    assert.equal(requests.length, 0);
    input.link = null;
    const detachedRevision = n.__orvEstimateRevision;
    element.events.get("durationchange")();
    assert.equal(n.__orvEstimateRevision, detachedRevision);
    n.onRemoved();
    assert.equal(element.events.size, 0);
});

test("ACI price-only refresh recomputes when capability projection stays unchanged", async () => {
    const { c, n, requests } = harness();
    n.type = "OpenRouterVideoGenerate";
    c.app.graph.nodes[n.id] = n;
    const savedValues = n.widgets.map(item => [item.name, item.value]);
    const initial = c.refreshEstimate(n);
    respond(requests[0], { state: "FORMULA", amount_usd: "2.31", rates_hash: "before" });
    await initial;
    const projection = { catalogue_revision: "same-capabilities", source_state: "FRESH", models: [model] };
    c.loadConnection = async () => ({ state: "CONNECTED" });
    c.loadCapabilities = async () => projection;
    c.projectSelectedModel = async () => {};
    await c.refreshCatalogue();
    assert.equal(requests.length, 1);
    const refresh = c.refreshCatalogue();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(requests.length, 2);
    respond(requests[1], { state: "FORMULA", amount_usd: "1.15", rates_hash: "after" });
    await refresh;
    assert.equal(n.__orvEstimate.value, "\u2248 $1.15 EST.");
    assert.equal(n.__orvEstimate.result.rates_hash, "after");
    assert.deepEqual(n.widgets.map(item => [item.name, item.value]), savedValues);
});

for (const failure of ["catalogue_failure", "disconnected"]) {
    test(`ACI ${failure} cannot keep an ancient formula current or cached`, async () => {
        const { c, n, requests } = harness();
        n.type = "OpenRouterVideoGenerate";
        c.app.graph.nodes[n.id] = n;
        const prior = c.refreshEstimate(n);
        respond(requests[0], { state: "FORMULA", amount_usd: "2.31", observed_at: "2000-01-01T00:00:00Z", rates_hash: "ancient" });
        await prior;
        assert.equal(n.__orvEstimate.result.state, "FORMULA");
        assert(n.__orvCostAcceptedSignature);
        c.loadConnection = async () => ({ state: failure === "disconnected" ? "DISCONNECTED" : "CONNECTED" });
        c.loadCapabilities = async () => { throw new Error("synthetic catalogue failure"); };
        await c.refreshCatalogue();
        assert(!["FORMULA", "RANGE"].includes(n.__orvEstimate.result.state));
        assert(!n.__orvEstimate.value.includes("2.31"));
        assert(!n.__orvCostAcceptedSignature);
        assert(!n.__orvCostAcceptedResult || n.__orvCostAcceptedResult.state !== "FORMULA");
    });
}

const neutralFixture = JSON.parse(readFileSync(new URL("../fixtures/aci_v1/kling-neutral-ui-projection.json", import.meta.url), "utf8")).model;
function neutralHarness(entries) {
    const result = harness(JSON.parse(JSON.stringify(neutralFixture)));
    result.n.widgets.find(item => item.name === "duration").value = 3;
    result.n.widgets.push({ name: "provider_options", value: JSON.stringify(entries), options: {} });
    return result;
}
const neutralEntries = [
    { provider: "atlas-cloud", key: "cfg_scale", value: 0.5 },
    { provider: "atlas-cloud", key: "negative_prompt", value: "PRIVATE_SELECTED_NEGATIVE_TEXT\u{1F642}" },
];
test("ACI reviewed neutral Kling controls preserve known price without leaking selected text", async () => {
    const { c, n, requests } = neutralHarness(neutralEntries);
    const pending = c.refreshEstimate(n);
    assert.equal(requests.length, 1);
    const outbound = JSON.stringify(requests[0].body);
    assert(!outbound.includes("PRIVATE_SELECTED_NEGATIVE_TEXT"));
    assert(!Object.hasOwn(requests[0].body, "provider_options"));
    assert.equal(requests[0].body.provider_policy_version, "ACI-1.0");
    const controls = requests[0].body.provider_controls;
    assert.equal(controls.find(item => item.key === "cfg_scale").number_value, "0.5");
    assert.equal(controls.find(item => item.key === "negative_prompt").text_length,
        [...neutralEntries[1].value].length);
    assert(controls.every(item => !Object.hasOwn(item, "value")));
    respond(requests[0], { state: "FORMULA", amount_usd: "0.336" });
    await pending;
    assert.equal(n.__orvEstimate.result.state, "FORMULA");
    assert.equal(n.__orvEstimate.value, "\u2248 $0.34 EST.");
});


test("ACI unknown complex provider control stays unavailable without a request", async () => {
    const { c, n, requests } = neutralHarness([...neutralEntries,
        { provider: "atlas-cloud", key: "unknown_complex", value: { private: "DO_NOT_SEND" } }]);
    await c.refreshEstimate(n);
    assert.equal(requests.length, 0);
    assert.equal(n.__orvEstimate.result.state, "UNKNOWN");
});

for (const value of ["0.5", 2, true]) {
    test(`ACI malformed typed neutral cfg_scale ${JSON.stringify(value)} is invalid`, async () => {
        const { c, n, requests } = neutralHarness([{ provider: "atlas-cloud", key: "cfg_scale", value }]);
        await c.refreshEstimate(n);
        assert.equal(requests.length, 0);
        assert.equal(n.__orvEstimate.result.state, "INVALID");
    });
}

for (const reason of ["provider_policy_version_mismatch", "provider_policy_scope_mismatch"]) {
    test(`ACI server ${reason} stays unknown rather than restoring a price`, async () => {
        const { c, n, requests } = neutralHarness(neutralEntries);
        const pending = c.refreshEstimate(n);
        assert.equal(requests.length, 1);
        respond(requests[0], { state: "UNKNOWN", reason_codes: [reason] });
        await pending;
        assert.equal(n.__orvEstimate.value, "COST");
        assert.equal(n.__orvEstimate.result.state, "UNKNOWN");
    });
}
