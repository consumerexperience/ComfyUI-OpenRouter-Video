import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = readFileSync(new URL("../../web/openrouter_video.js", import.meta.url), "utf8")
    .replace(/^import .*;\r?\n/gm, "");
const MODEL = "test/exact-model";
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };

function harness() {
    let clock = 1000, wall = 100000, nextTimer = 0;
    const timers = new Map(), calls = [], apiEvents = new Map();
    const c = {
        app: { registerExtension(value) { this.extension = value; } },
        api: {
            addEventListener(name, fn) { const handlers = apiEvents.get(name) || []; handlers.push(fn); apiEvents.set(name, handlers); },
            fetchApi() { return Promise.resolve({ ok: false }); },
            queuePrompt(...args) {
                let resolve, reject;
                const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
                calls.push({ self: this, args, promise, resolve, reject });
                return promise;
            },
        },
        performance: { now: () => clock }, Date: class extends Date { static now() { return wall; } },
        setTimeout(fn, ms) { const id = ++nextTimer; timers.set(id, { fn, ms }); return id; },
        clearTimeout(id) { timers.delete(id); }, queueMicrotask,
    };
    vm.runInNewContext(source, c);
    c.installActualQueueObserver();
    function graph(id = "graph-A") {
        return { id, nodes: {}, _nodes: [], links: {}, getNodeById(id) { return this.nodes[id]; } };
    }
    function node(g, id = 42, type = "OpenRouterVideoGenerate", expected = "job-1", linked = false) {
        const n = { id, type, graph: g, size: [400, 400], inputs: linked ? [{ name: "job_id", link: 70 }] : [],
            widgets: [{ name: "model", value: MODEL }, { name: "job_id", value: expected }],
            __orvEstimate: { value: "≈ $1.00 EST.", result: { state: "FORMULA", amount_usd: "1" } },
            setDirtyCanvas() {} };
        g.nodes[id] = n; g._nodes.push(n); c.installCostLifecycle(n); return n;
    }
    const g = graph(), n = node(g);
    c.app.graph = g; c.app.rootGraph = g;
    function queue(nodes = [n], requestId = calls.length + 1, options = {}) {
        const ownerGraph = nodes[0].graph;
        c.app.graph = ownerGraph; c.app.rootGraph = ownerGraph;
        c.captureActualQueueTicket({ requestId, batchCount: options.batchCount || 1 });
        const payload = { workflow: { id: ownerGraph.id }, output: Object.fromEntries(nodes.map(node => [node.id, {
            class_type: node.type, inputs: node.type === "OpenRouterVideoGenerate" ? { model: MODEL, prompt: "private prompt never retained" } :
                { job_id: options.linked ? ["7", 1] : node.widgets.find(item => item.name === "job_id").value },
        }])) };
        const args = [0, payload, { previewMethod: "none" }];
        // Pinned native queue loop runs public widget hooks before graphToPrompt.
        for (const node of ownerGraph._nodes) for (const item of node.widgets || []) item.beforeQueued?.({ isPartialExecution: false });
        const promise = c.api.queuePrompt(...args);
        return { call: calls.at(-1), promise, payload, args };
    }
    function completion(prompt = "prompt-1", fields = {}) {
        return { prompt_id: prompt, node: "42", output: { orv_actual_v1: [{ schema_version: 1,
            job_id: "job-1", model: MODEL, amount_usd: "2.28", state: "DONE", operation_kind: "GENERATE", ...fields }] } };
    }
    return { c, n, g, graph, node, calls, queue, completion, timers, apiEvents,
        advance(ms) { clock += ms; wall += ms; }, lexical(name) { return vm.runInNewContext(name, c); } };
}

async function bound(h, prompt = "prompt-1", options) {
    const q = h.queue(options?.nodes || [h.n], h.calls.length + 1, options);
    q.call.resolve({ prompt_id: prompt }); await flush(); return q;
}

test("passive public queue observer preserves exact this, args, result promise and single call", async () => {
    const h = harness();
    assert.equal(h.calls.length, 0, "installation never queues");
    const q = h.queue();
    assert.equal(h.calls.length, 1); assert.equal(q.promise, q.call.promise); assert.equal(q.call.self, h.c.api);
    q.args.forEach((arg, index) => assert.equal(q.call.args[index], arg));
    assert.equal(q.payload.output[42].inputs.prompt, "private prompt never retained");
    q.call.resolve({ prompt_id: "prompt-1" }); await flush();
    const owners = h.lexical("actualDispatches.get('prompt-1')");
    assert.equal(owners[0].instance, h.n); assert(Object.isFrozen(owners[0]));
    const safe = { ...owners[0] }; delete safe.instance; delete safe.graph;
    assert(!JSON.stringify(safe).includes("private prompt"));
    assert(!Object.hasOwn(safe, "inputs")); assert(!Object.hasOwn(safe, "payload"));
});

test("native rejection and synchronous throw propagate unchanged, without retry", async () => {
    const h = harness(), q = h.queue(), error = new Error("native rejection");
    q.call.reject(error); await assert.rejects(q.promise, e => e === error); await flush();
    assert.equal(h.calls.length, 1);
    const c = { app: { registerExtension() {} }, api: { queuePrompt() { throw error; } }, setTimeout() {}, clearTimeout() {} };
    vm.runInNewContext(source, c); c.installActualQueueObserver();
    assert.throws(() => c.api.queuePrompt(0, {}), e => e === error);
});

test("native executed event binds exact immutable prompt, graph and node, independent of next EST", async () => {
    const h = harness(); await bound(h);
    h.n.widgets[0].value = "new/model";
    h.c.handleActualExecuted(h.completion());
    assert.equal(h.n.__orvActualState.status, "KNOWN");
    assert.equal(h.n.__orvActualState.receipt.model, MODEL);
    h.c.invalidateCostPresentation(h.n);
    assert.equal(h.n.__orvActualState.receipt.amount, "2.28");
    assert.match(h.c.costDetailsText(h.n), /Last completed job\nActual cost: \$2\.28/);
});

test("completion before HTTP prompt acknowledgement is buffered and then bound", async () => {
    const h = harness(), q = h.queue();
    h.c.handleActualExecuted(h.completion()); assert.equal(h.n.__orvActualState.status, "NO_JOB");
    q.call.resolve({ prompt_id: "prompt-1" }); await flush();
    assert.equal(h.n.__orvActualState.status, "KNOWN");
    assert.equal(h.lexical("actualEarlyEvents.size"), 0);
});

test("two graphs with the same node ID cannot receive each other's completion", async () => {
    const h = harness(); await bound(h);
    const other = h.graph("graph-B"), clone = h.node(other);
    h.c.app.graph = other; h.c.app.rootGraph = other;
    h.c.handleActualExecuted(h.completion());
    assert.equal(h.n.__orvActualState.status, "KNOWN"); assert.equal(clone.__orvActualState.status, "NO_JOB");
});

test("exact current graph object distinguishes separate tickets with the same saved UUID", async () => {
    const h = harness(); h.c.captureActualQueueTicket({ requestId: 99, batchCount: 1 });
    const other = h.graph("graph-A"), clone = h.node(other);
    const q = h.queue([clone], 1); q.call.resolve({ prompt_id: "prompt-1" }); await flush();
    h.c.handleActualExecuted(h.completion());
    assert.equal(h.n.__orvActualState.status, "NO_JOB"); assert.equal(clone.__orvActualState.status, "KNOWN");
});

test("multiple indistinguishable queued requests on one graph fail closed", async () => {
    const h = harness(); h.c.captureActualQueueTicket({ requestId: 99, batchCount: 1 });
    const q = h.queue(); q.call.resolve({ prompt_id: "prompt-1" }); await flush();
    h.c.handleActualExecuted(h.completion()); assert.equal(h.n.__orvActualState.status, "NO_JOB");
});

test("graph switch with a reused saved UUID cannot borrow the old graph's single queue ticket", async () => {
    const h = harness(); h.c.captureActualQueueTicket({ requestId: 99, batchCount: 1 });
    const other = h.graph("graph-A"), clone = h.node(other);
    h.c.app.rootGraph = other; h.c.app.graph = other;
    for (const item of clone.widgets) item.beforeQueued?.();
    const pending = h.c.api.queuePrompt(0, { workflow: { id: "graph-A" }, output: { 42: {
        class_type: "OpenRouterVideoGenerate", inputs: { model: MODEL },
    } } });
    h.calls.at(-1).resolve({ prompt_id: "prompt-1" }); await pending; await flush();
    h.c.handleActualExecuted(h.completion());
    assert.equal(h.n.__orvActualState.status, "NO_JOB"); assert.equal(clone.__orvActualState.status, "NO_JOB");
});

test("foreign prompt and wrong node are ignored; owned model/operation mismatch suppresses ACTUAL", async () => {
    const h = harness(); await bound(h);
    h.c.handleActualExecuted(h.completion("foreign"));
    h.c.handleActualExecuted({ ...h.completion(), node: "43" });
    assert.equal(h.n.__orvActualState.status, "NO_JOB");
    h.c.handleActualExecuted(h.completion("prompt-1", { model: "wrong/model" }));
    h.c.handleActualExecuted(h.completion("prompt-1", { operation_kind: "RESUME" }));
    assert.equal(h.n.__orvActualState.receipt, null); assert.notEqual(h.n.__orvActualState.status, "KNOWN");
});

test("duplicates are idempotent, equivalent decimal strings preserve original exact receipt", async () => {
    const h = harness(); await bound(h);
    h.c.handleActualExecuted(h.completion("prompt-1", { amount_usd: "0.50" }));
    const receipt = h.n.__orvActualState.receipt;
    h.c.handleActualExecuted(h.completion("prompt-1", { amount_usd: "0.5" }));
    assert.equal(h.n.__orvActualState.status, "KNOWN"); assert.equal(h.n.__orvActualState.receipt, receipt);
    assert.equal(receipt.amount, "0.50");
});

for (const fields of [{ job_id: "another-job" }, { model: "contradictory/model" }, { amount_usd: "7.12" }]) {
    test(`same dispatch contradiction suppresses both receipts: ${JSON.stringify(fields)}`, async () => {
        const h = harness(); await bound(h); h.c.handleActualExecuted(h.completion());
        h.c.handleActualExecuted(h.completion("prompt-1", fields));
        assert.equal(h.n.__orvActualState.status, "CONFLICT"); assert.equal(h.n.__orvActualState.receipt, null);
        h.c.handleActualExecuted(h.completion()); assert.equal(h.n.__orvActualState.status, "CONFLICT");
        await bound(h, "prompt-2"); h.c.handleActualExecuted(h.completion("prompt-2", { job_id: "newer-job" }));
        assert.equal(h.n.__orvActualState.status, "KNOWN");
    });
}

test("newer execution wins regardless of completion order; starting a job keeps previous receipt", async () => {
    const h = harness(); await bound(h); h.c.handleActualExecuted(h.completion());
    const prior = h.n.__orvActualState.receipt;
    await bound(h, "prompt-2"); assert.equal(h.n.__orvActualState.receipt, prior);
    await bound(h, "prompt-3"); h.c.handleActualExecuted(h.completion("prompt-3", { job_id: "job-3" }));
    h.c.handleActualExecuted(h.completion("prompt-2", { job_id: "job-2" }));
    assert.equal(h.n.__orvActualState.receipt.job, "job-3");
});

for (const amount of [null, "0", "NaN", "-1", 1.2, undefined, "0." + "0".repeat(31) + "1"]) {
    test(`missing/zero/malformed authoritative cost remains distinct: ${String(amount)}`, async () => {
        const h = harness(); await bound(h); h.c.handleActualExecuted(h.completion());
        await bound(h, "prompt-2"); h.c.handleActualExecuted(h.completion("prompt-2", { job_id: "job-2", amount_usd: amount }));
        assert.equal(h.n.__orvActualState.status, amount === null ? "MISSING" : amount === "0" ? "KNOWN" : "INVALID_ACTUAL");
        if (amount === "0") assert.equal(h.c.actualCostText(h.n), "$0.00 ACTUAL");
        else assert(!h.c.costDetailsText(h.n).includes("2.28 USD ACTUAL"));
    });
}

test("Resume literal expected job and trusted linked-input expected job require exact owned prompt", async () => {
    const h = harness(), resume = h.node(h.g, 43, "OpenRouterVideoResume", "resume-job");
    await bound(h, "resume-1", { nodes: [resume] });
    const event = { ...h.completion("resume-1", { operation_kind: "RESUME", job_id: "wrong" }), node: "43" };
    h.c.handleActualExecuted(event); assert.equal(resume.__orvActualState.status, "INVALID_ACTUAL");
    await bound(h, "resume-1b", { nodes: [resume] }); event.prompt_id = "resume-1b";
    event.output.orv_actual_v1[0].job_id = "resume-job";
    h.c.handleActualExecuted(event); assert.equal(resume.__orvActualState.status, "KNOWN");
    const linked = h.node(h.g, 44, "OpenRouterVideoResume", "untrusted-widget", true);
    await bound(h, "resume-2", { nodes: [linked], linked: true });
    const owned = { ...h.completion("resume-2", { operation_kind: "RESUME", job_id: "linked-job", expected_job_id: "linked-job" }), node: "44" };
    h.c.handleActualExecuted({ ...owned, prompt_id: "foreign" }); assert.equal(linked.__orvActualState.status, "NO_JOB");
    h.c.handleActualExecuted(owned); assert.equal(linked.__orvActualState.status, "KNOWN");
});

test("removal, same-object configure reset, graph reload, replacement and TTL invalidate ownership", async () => {
    for (const mode of ["remove", "configure", "reload", "replace", "ttl"]) {
        const h = harness(); await bound(h);
        if (mode === "remove") h.n.onRemoved();
        if (mode === "configure") h.c.resetActualBinding(h.n);
        if (mode === "reload") h.c.app.extension.beforeConfigureGraph();
        if (mode === "replace") h.node(h.g);
        if (mode === "ttl") h.advance(3600001);
        h.c.handleActualExecuted(h.completion()); assert.equal(h.n.__orvActualState.status, "NO_JOB", mode);
    }
});

test("early buffer and observer/ticket ownership expire, registry contains no workflow payload", () => {
    const h = harness(); h.queue();
    for (let i = 0; i < 150; i++) h.c.handleActualExecuted(h.completion(`early-${i}`));
    assert.equal(h.lexical("actualEarlyEvents.size"), 128);
    h.advance(30001); h.c.pruneActualBindings();
    assert.equal(h.lexical("actualEarlyEvents.size + actualQueueTickets.size + actualQueueObservers.size"), 0);
});

test("draw/details and visibility/focus check monotonic freshness even if timers never run", () => {
    const h = harness(); h.c.setCostPresentation(h.n, { state: "FORMULA", amount_usd: "2.28", valid_for_ms: 10 });
    h.advance(11);
    assert.equal(h.c.costBadgeLabel(h.n), "PRICE STALE");
    assert(!h.c.costDetailsText(h.n).includes("2.28"));
    const listeners = new Map();
    h.c.document = { addEventListener(name, fn) { listeners.set(name, fn); } };
    h.c.window = { addEventListener(name, fn) { listeners.set(name, fn); } };
    vm.runInNewContext("costLifecycleInstalled=false", h.c); h.c.installCostLifecycle(h.n);
    for (const event of ["visibilitychange", "focus"]) {
        h.c.setCostPresentation(h.n, { state: "FORMULA", amount_usd: "1", valid_for_ms: 10 }); h.advance(11);
        listeners.get(event)(); assert.equal(h.n.__orvEstimate.result.state, "STALE");
    }
});

test("compact display retains primary semantic suffix and distinct LAST ACTUAL details", async () => {
    const h = harness(); await bound(h); h.c.handleActualExecuted(h.completion());
    assert.equal(h.c.costBadgeLabel(h.n, 140), "≈ $1.00 EST.");
    assert.equal(h.c.costBadgeLabel(h.n, 1000), "≈ $1.00 EST.");
    h.n.__orvEstimate = { value: "≈ $1.50 MODEL", result: { state: "PARTIAL" } };
    assert.equal(h.c.costBadgeLabel(h.n, 140), "≈ $1.50 MODEL");
    assert.match(h.c.costDetailsText(h.n), /Last completed job/);
    h.n.__orvEstimate.value = "≈ $123456789012345678901234567890.00 MODEL";
    assert(h.c.costBadgeLabel(h.n, 120).endsWith(" MODEL"));
    assert.equal(h.c.costBadgeLabel(h.n, 35), "MODEL");
});

test("R2 keeps next MODEL in the badge and prior owned ACTUAL in a separate Green section", async () => {
    const h = harness(); await bound(h); h.c.handleActualExecuted(h.completion());
    h.n.__orvEstimate = { value: "≈ $1.50 MODEL", result: { state: "PARTIAL" } };
    const label = h.c.costBadgeLabel(h.n, 1000), drawn = [];
    const ctx = { fillStyle: "#FFBB00", measureText: text => ({ width: text.length * 7 }),
        fillText(text) { drawn.push({ text, color: this.fillStyle }); } };
    h.c.drawCostBadgeLabel(h.n, ctx, label, 500, 0, 400);
    assert(!drawn.some(row => row.text.endsWith(" ACTUAL")));
    assert(drawn.some(row => row.text.includes("MODEL") && row.color === "#FFBB00"));
    class Element {
        constructor() { this.style = {}; this.children = []; this.ownText = ""; }
        get textContent() { return this.ownText + this.children.map(child => child.textContent).join(""); }
        set textContent(value) { this.ownText = value; this.children = []; }
        append(...children) { this.children.push(...children); }
    }
    h.c.document = { createElement: () => new Element() };
    const badge = new Element(); h.c.setCostBadgeLabel(h.n, badge, label);
    assert.equal(badge.textContent, label); assert.equal(badge.children.length, 0);
    const detail = new Element(); h.c.renderCostDetails(h.n, detail);
    const all=item=>[item,...item.children.flatMap(all)];
    assert(all(detail).some(item=>item.textContent==="$2.28" && item.style.color==="#0ACF83"));
    h.n.__orvActualState = { status: "MISSING", receipt: null, watermark: 2 };
    h.c.renderCostDetails(h.n, detail);
    assert(!all(detail).some(child=>child.className==="orv-cost-actual"));
    assert(!detail.textContent.includes("2.28"));
});

test("RATE_ONLY uses exact decimal scaling and never displays positive token rate as free", () => {
    const h = harness();
    assert.equal(h.c.costBadgeText({ state: "RATE_ONLY", rate_usd: "0.000001005", rate_unit: "token" }), "$1.01/M tok RATE");
    assert.equal(h.c.costBadgeText({ state: "RATE_ONLY", rate_usd: "0.000000000000000001", rate_unit: "token" }), "<$0.01/M tok RATE");
    assert.equal(h.c.costBadgeText({ state: "RATE_ONLY", rate_usd: "0.0000064", rate_unit: "token" }), "$6.40/M tok RATE");
    assert.equal(h.c.costBadgeText({ state: "RATE_ONLY", rate_usd: "0.1234567890123456789", rate_unit: "s" }), "$0.1235/s RATE");
});

function mediaFixture(h) {
    class Media {
        constructor() { this.tagName = "VIDEO"; this.readyState = 1; this.duration = 4.5; this.videoWidth = 1280; this.videoHeight = 720;
            this.src = "local-preview-A"; this.currentSrc = this.src; this.events = new Map(); }
        addEventListener(name, fn) { this.events.set(name, fn); }
        removeEventListener(name, fn) { if (this.events.get(name) === fn) this.events.delete(name); }
        emit(type) { this.events.get(type)?.({ type }); }
    }
    h.c.HTMLMediaElement = Media;
    const element = new Media(), origin = { id: 7, outputs: [{ type: "VIDEO" }], widgets: [{ name: "video", value: "selection-A" }, { element }] };
    const input = { name: "source_video", link: 70 }, link = { origin_id: 7, origin_slot: 0, target_id: 42, target_slot: 0 };
    h.g.nodes[7] = origin; h.g.links[70] = link; h.n.inputs = [input];
    h.n.__orvCapability = { __methodProfile: { topology: { fixed: ["source_video"] } } };
    return { element, origin, input, link, occurrence: { input, kind: "video", role: "source_video" } };
}

test("preview metadata is current-link/current-selection HINT, never guessed output usage", () => {
    const h = harness(), m = mediaFixture(h);
    assert.equal(h.c.readNativeCostMetadata(h.n, m.occurrence).duration_seconds, "4.5");
    m.origin.widgets[0].value = "selection-B";
    m.origin.widgets[0].callback();
    assert.equal(h.c.readNativeCostMetadata(h.n, m.occurrence).status, "UNKNOWN");
    m.element.src = "local-preview-B"; m.element.emit("loadstart");
    assert.equal(h.c.readNativeCostMetadata(h.n, m.occurrence).status, "UNKNOWN");
    m.element.currentSrc = m.element.src; m.element.duration = 7; m.element.emit("loadedmetadata");
    const result = h.c.readNativeCostMetadata(h.n, m.occurrence);
    assert.equal(result.status, "HINT"); assert.equal(result.duration_seconds, "7");
    assert(!JSON.stringify(result).includes("preview")); assert(!Object.hasOwn(result, "effective_output_seconds"));
});

test("replaced/disconnected/parked occurrences and removed nodes release preview listeners", () => {
    const h = harness(), m = mediaFixture(h); h.c.readNativeCostMetadata(h.n, m.occurrence);
    h.g.links[70] = { ...m.link }; h.c.pruneCostMetadataWatches(h.n);
    assert.equal(m.element.events.size, 0);
    h.c.readNativeCostMetadata(h.n, m.occurrence); m.input.link = null; h.c.pruneCostMetadataWatches(h.n);
    assert.equal(m.element.events.size, 0);
    m.input.link = 70; h.c.readNativeCostMetadata(h.n, m.occurrence); h.n.onRemoved();
    assert.equal(m.element.events.size, 0); assert.equal(h.lexical("costPresentationNodes.size"), 0);
});

test("live v2 preview entries carry ordered occurrence index and enclosing current context revision", async () => {
    const h = harness(); mediaFixture(h);
    h.n.widgets.push(...Object.entries({ inference_method: "V2V_EDIT", duration: 4, resolution: "720p", aspect_ratio: "16:9",
        size: "", generate_audio: false, provider_options: "[]" }).map(([name, value]) => ({ name, value })));
    h.n.__orvCapability.__methodProfile.state = "SUPPORTED";
    Object.assign(h.n.__orvCapability.__methodProfile.topology, { reference_kinds: [], kind_sets: [[]], min: 0, max: 0 });
    let body;
    h.c.api.fetchApi = (url, init) => {
        assert.equal(url, "/openrouter-video/v1/cost-estimate"); body = JSON.parse(init.body);
        return Promise.resolve({ ok: true, json: async () => ({ state: "RATE_ONLY", rate_usd: "0.03", rate_unit: "s",
            context_revision: body.context_revision, valid_for_ms: 1000 }) });
    };
    await h.c.refreshEstimate(h.n);
    assert(body); assert.equal(body.media.length, 1); assert.equal(body.media[0].status, "HINT");
    assert.equal(body.media[0].occurrence_index, 0); assert.equal(body.media[0].context_revision, body.context_revision);
    assert(!JSON.stringify(body).includes("preview")); assert(!JSON.stringify(body).includes("selection-A"));
});

test("native preview element replacement is detected at draw/sync even with identical quantities", () => {
    const h = harness(), m = mediaFixture(h);
    h.c.checkNativeCostMetadata(h.n);
    const oldRevision = h.n.__orvEstimateRevision || 0;
    const replacement = new h.c.HTMLMediaElement(); m.origin.widgets[1].element = replacement;
    h.c.checkNativeCostMetadata(h.n);
    assert(h.n.__orvEstimateRevision > oldRevision); assert.equal(h.n.__orvEstimate.result.state, "CALCULATING");
    assert.equal(m.element.events.size, 0); assert(replacement.events.size > 0);
    assert.equal(h.calls.length, 0, "preview observation never queues execution");
});

test("preview metadata never reads media URLs or selected filenames; selection callback forwards semantics", () => {
    const h = harness(), m = mediaFixture(h), calls = [];
    const original = function (...args) { calls.push({ self: this, args }); return "native-result"; };
    m.origin.widgets[0].callback = original;
    for (const key of ["src", "currentSrc"]) Object.defineProperty(m.element, key, { get() { throw new Error("URL access forbidden"); } });
    Object.defineProperty(m.origin.widgets[0], "value", { get() { throw new Error("filename access forbidden"); } });
    assert.equal(h.c.readNativeCostMetadata(h.n, m.occurrence).status, "HINT");
    const self = {}, args = ["selected-value-is-forwarded-not-retained", 7];
    assert.equal(m.origin.widgets[0].callback.apply(self, args), "native-result");
    assert.equal(calls.length, 1); assert.equal(calls[0].self, self); assert.deepEqual(calls[0].args, args);
    assert.equal(h.c.readNativeCostMetadata(h.n, m.occurrence).status, "UNKNOWN");
    h.c.clearCostMetadataWatches(h.n); assert.equal(m.origin.widgets[0].callback, original);
});

for (const [name, output] of [
    ["absent", {}], ["empty", { orv_actual_v1: [] }],
    ["multiple", { orv_actual_v1: [{}, {}] }],
    ["schema", { orv_actual_v1: [{ schema_version: 2, job_id: "job-2", model: MODEL }] }],
    ["nested malformed", { orv_actual_v1: [{ schema_version: 1, job_id: "job-2", model: MODEL, state: "DONE",
        operation_kind: "GENERATE", amount_usd: { private: "never retain nested payload" } }] }],
    ["model mismatch", { orv_actual_v1: [{ schema_version: 1, job_id: "job-2", model: "unexpected/model", state: "DONE",
        operation_kind: "GENERATE", amount_usd: "2" }] }],
    ["operation mismatch", { orv_actual_v1: [{ schema_version: 1, job_id: "job-2", model: MODEL, state: "DONE",
        operation_kind: "RESUME", amount_usd: "2" }] }],
]) {
    for (const early of [false, true]) test(`owned newer ${name} completion suppresses old ACTUAL (${early ? "early" : "after acknowledgement"})`, async () => {
        const h = harness(); await bound(h); h.c.handleActualExecuted(h.completion());
        const q = h.queue(), detail = { prompt_id: "prompt-2", node: "42", output };
        if (early) h.c.handleActualExecuted(detail);
        q.call.resolve({ prompt_id: "prompt-2" }); await flush();
        if (!early) h.c.handleActualExecuted(detail);
        assert.equal(h.n.__orvActualState.status, "INVALID_ACTUAL");
        assert.equal(h.n.__orvActualState.watermark, 2); assert.equal(h.n.__orvActualState.receipt, null);
        assert(!h.c.costDetailsText(h.n).includes("2.28 USD ACTUAL"));
    });
}

test("older or foreign malformed completion cannot suppress a newer valid ACTUAL", async () => {
    const h = harness(); await bound(h); await bound(h, "prompt-2");
    h.c.handleActualExecuted(h.completion("prompt-2", { job_id: "job-2" }));
    const state = h.n.__orvActualState;
    h.c.handleActualExecuted({ prompt_id: "prompt-1", node: "42", output: {} });
    h.c.handleActualExecuted({ prompt_id: "foreign", node: "42", output: {} });
    assert.equal(h.n.__orvActualState, state);
});

test("linked Resume cannot use mutable widget fallback without backend expected-job metadata", async () => {
    const h = harness(), linked = h.node(h.g, 44, "OpenRouterVideoResume", "widget-job", true);
    await bound(h, "resume-1", { nodes: [linked], linked: true });
    h.c.handleActualExecuted({ ...h.completion("resume-1", { operation_kind: "RESUME", job_id: "widget-job" }), node: "44" });
    assert.equal(linked.__orvActualState.status, "INVALID_ACTUAL"); assert.equal(linked.__orvActualState.receipt, null);
});
