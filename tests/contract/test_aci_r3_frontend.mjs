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

function precompletionResult(count = 1) {
    const amount = "1.8489600";
    return { state:"INVALID", availability:"UNAVAILABLE", reason:"required_inputs_missing",
        amount_usd:null, context_revision:1, valid_for_ms:900000, rates_hash:"a".repeat(64),
        precompletion_advisory:{ version:"ACI-PRECOMPLETION-1", currency:"USD", scope:"COMPARISON",
            amount_usd:amount, actual_reference_kinds:Array(count).fill("image"),
            missing_inputs:[{kind:"image",role:"reference",count:2-count}],
            completion_assumptions:["Add missing IMAGE references before generation."],
            scenario:{scope:"COMPARISON",amount_usd:amount,quantity:"8",quantity_unit:"s",
                sku:"video_tokens_without_audio",assumption:"Hypothetical valid completion."} } };
}

test("ACI pre-completion REF is violet and never changes primary readiness", () => {
    const { c, n } = harness();
    const result = precompletionResult();
    c.setCostPresentation(n, result);
    assert.equal(n.__orvEstimate.value, "≈ $1.85 REF.");
    assert.equal(n.__orvEstimate.result.state, "INVALID");
    assert.equal(c.costPriceView(result).accent, "#9E6BFF");
    assert.match(c.costDetailsText(n), /missing inputs/i);
});

for (const [name, mutate] of [
    ["unknown version", r => r.precompletion_advisory.version = "unknown"],
    ["hard invalid", r => r.reason = "media_combined_duration_exceeds_limit"],
    ["stale", r => r.state = "STALE"],
    ["expired", r => r.valid_for_ms = 0],
    ["primary total", r => r.amount_usd = "1.85"],
    ["scenario mismatch", r => r.precompletion_advisory.scenario.amount_usd = "2"],
    ["total scope", r => r.precompletion_advisory.scope = "CONDITIONAL_TOTAL"],
    ["missing assumptions", r => r.precompletion_advisory.completion_assumptions = []],
    ["missing inputs absent", r => r.precompletion_advisory.missing_inputs = []],
]) test(`ACI pre-completion fails closed: ${name}`, () => {
    const { c } = harness();
    const result = precompletionResult(); mutate(result);
    assert.equal(c.costAdvisoryComparison(result), null);
    assert.notEqual(c.costPriceView(result).kind, "reference");
});

test("ACI incomplete native shape sends actual zero counts and rejects late cross-context REF", async () => {
    const { c, n, requests } = harness();
    n.widgets.find(item => item.name === "inference_method").value = "MI2V";
    const selected = c.configureInferenceMethod(n, model);
    c.reprojectNodeSemantics(n, model, selected, { cause:"catalogue" });
    const first = c.refreshEstimate(n);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].body.reference_count, 0);
    assert.deepEqual(Array.from(requests[0].body.reference_kinds), []);
    const second = c.refreshEstimate(n);
    respond(requests[1], precompletionResult(0)); await second;
    assert.equal(n.__orvEstimate.value, "≈ $1.85 REF.");
    respond(requests[0], {state:"FORMULA",amount_usd:"999"}); await first;
    assert.equal(n.__orvEstimate.value, "≈ $1.85 REF.");
});

test("ACI pre-completion estimates stay independent across two nodes in one graph", async () => {
    const { c, n, requests } = harness();
    n.widgets.find(item => item.name === "inference_method").value = "MI2V";
    const selected = c.configureInferenceMethod(n, model);
    c.reprojectNodeSemantics(n, model, selected, {cause:"catalogue"});
    const other = { ...n, id:43, widgets:n.widgets.map(item => ({...item})),
        __orvEstimate:{value:""}, inputs:n.inputs.map(item => ({...item})) };
    c.app.graph.nodes[n.id] = n; c.app.graph.nodes[other.id] = other;
    const first = c.refreshEstimate(n), second = c.refreshEstimate(other);
    assert.equal(requests.length, 2);
    respond(requests[1], precompletionResult(0)); await second;
    respond(requests[0], precompletionResult(0)); await first;
    assert.equal(n.__orvEstimate.value, other.__orvEstimate.value);
    const changed = c.refreshEstimate(n);
    respond(requests[2], {state:"INVALID",reason:"provider_control_invalid"}); await changed;
    assert.equal(other.__orvEstimate.value, "≈ $1.85 REF.");
    assert.equal(n.__orvEstimate.result.reason, "provider_control_invalid");
    c.discardCurrentCost(other, "pricing_evidence_stale");
    assert(!other.__orvEstimate.value.includes("REF."));
});

function tooltipDOM(c) {
    class Element {
        constructor(tag){this.tag=tag;this.style={};this.children=[];this.attributes={};this.handlers={};this.ownText="";}
        get textContent(){return this.ownText+this.children.map(child=>child.textContent).join("");}
        set textContent(value){this.ownText=value;this.children=[];}
        setAttribute(k,v){this.attributes[k]=v;} removeAttribute(k){delete this.attributes[k];}
        append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
        remove(){if(this.parent)this.parent.children=this.parent.children.filter(item=>item!==this);}
        addEventListener(name,fn){this.handlers[name]=fn;} focus(){}
        getBoundingClientRect(){return {left:100,top:80,right:530,bottom:100,width:430,height:200};}
    }
    c.document={documentElement:{dir:"ltr"},createElement:tag=>new Element(tag),body:new Element("body")};
    c.window={innerWidth:1000,innerHeight:700};
    return tag=>new Element(tag);
}

for (const [state, fields, label] of [
    ["FORMULA", { amount_usd: "2.3112", estimated_cost_usd: "2.3112", availability: "AVAILABLE" }, /2\.31.*EST/],
    ["RANGE", { lower_usd: "0.8", upper_usd: "1.2" }, /0\.80.*1\.20.*EST/],
    ["RATE_ONLY", { rate_usd: "0.03", rate_unit: "s" }, /0\.03\/s.*RATE/],
    ["RATE_ONLY", { rate_usd: "0.0000064", rate_unit: "token" }, /6\.40\/M\s*tok.*RATE/],
    ["PARTIAL", {}, /COST PARTIAL/], ["UNKNOWN", {}, /PRICE UNKNOWN/],
    ["STALE", {}, /PRICE STALE/], ["INVALID", {}, /CHECK INPUTS/],
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
    assert.equal(c.costBadgeText({ state: "RANGE", lower_usd: "0.8", upper_usd: "1.2" }), "$0.80\u20131.20 EST.");
    assert.equal(c.costBadgeText({ state: "CALCULATING" }), "CALCULATING\u2026");
});

test("ACI collapsed Classic retains badge without changing node geometry", () => {
    const { c, n } = harness();
    n.flags = { collapsed: true };
    n._collapsed_width = 300;
    n.__orvEstimate.value = "PRICE UNKNOWN";
    const before = [...n.size];
    const drawn = [];
    const ctx = { save() {}, restore() {}, fillRect() {}, fillText(text) { drawn.push(text); } };
    c.drawCollapsedCostBadge(n, ctx);
    assert.deepEqual(Array.from(n.size), before);
    assert.deepEqual(drawn, ["PRICE UNKNOWN"]);
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
        respond(requests[0], { state: "FORMULA", amount_usd: "2.31", observed_at: "2026-11-13T20:30:42Z", rates_hash: "prior" });
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
        assert.equal(n.__orvEstimate.value, "PRICE UNKNOWN");
        assert.equal(n.__orvEstimate.result.state, "UNKNOWN");
    });
}

const modelPlan = { version: "ACI-PLANNING-1", display: "MODELLED", modelled_usd: "1.24416", scenarios: [{scope:"CONDITIONAL_TOTAL", label:"native", amount_usd:"1.24416", assumption:"route assumption"}] };
test("R3 distinguishes modelled money from EST and uses exact decimal rendering", () => {
    const {c}=harness();
    assert.equal(c.costBadgeText({state:"RATE_ONLY",planning:modelPlan}), "≈ $1.24 MODEL");
    assert.equal(c.costBadgeText({state:"RATE_ONLY",planning:{...modelPlan,display:"SCENARIO_RANGE",scenario_min_usd:"0.0756",scenario_max_usd:"0.1344"}}), "≈ $0.08–0.13 MODEL");
    assert.equal(c.costBadgeText({state:"UNKNOWN",planning:{...modelPlan,display:"DETAIL_ONLY"}}), "PRICE UNKNOWN");
    assert.equal(c.costBadgeText({state:"PARTIAL",planning:{...modelPlan,display:"DETAIL_ONLY"}}), "COST PARTIAL");
    assert.equal(c.costBadgeText({state:"FORMULA",amount_usd:"2.005",planning:modelPlan}), "≈ $2.01 EST.");
    assert.equal(c.costMoney("0.0001"),"<0.01");
    assert.equal(c.costMoney("0"),"0.00");
    assert.equal(c.costMoney("NaN"),null);
    assert.equal(c.costBadgeText({state:"STALE",planning:modelPlan}),"PRICE STALE");
});
test("R3 limited transparency disclosure and comparison details",()=>{
    const {c,n}=harness();
    c.setCostPresentation(n,{state:"UNKNOWN",planning:{...modelPlan,display:"DETAIL_ONLY",scenarios:[{scope:"COMPARISON",label:"with audio",amount_usd:"0.20",assumption:"not selected silent mode"}]}});
    assert.match(c.costDetailsText(n),/Reference only; not a total/);
    assert.match(c.costDetailsText(n),/\$0.20/);
    assert(!c.costDetailsText(n).includes(" × "));
    assert.match(c.costTechnicalDetailsText(n),/COMPARISON/);
    assert.equal(n.__orvEstimate.value,"≈ $0.20 REF.");
});

test("R2: the existing Gemini comparison is a Violet reference without changing Core",()=>{
    const {c,n}=harness();
    const result={state:"UNKNOWN",planning:{version:"ACI-PLANNING-1",display:"DETAIL_ONLY",scenarios:[{
        scope:"COMPARISON",label:"with-audio output component (comparison)",amount_usd:"0.208512",
        assumption:"Published with-audio output rate; selected audio and input charges may differ.",
        charges:[{sku:"output_seconds",quantity:"3.00000000",rate_usd:"0.069504000000",amount_usd:"0.208512",quantity_unit:"s"}]
    }]}};
    const before=JSON.stringify(result);c.setCostPresentation(n,result);
    assert.equal(n.__orvEstimate.value,"≈ $0.21 REF.");
    assert.equal(c.costBadgeColors(n,n.__orvEstimate.value).accent,"#9E6BFF");
    assert.match(c.costDetailsText(n),/not a total/);
    assert.match(c.costDetailsText(n),/input charges may differ/i);
    assert(!c.costDetailsText(n).includes("0.208512"));
    assert(!c.costDetailsText(n).includes("output_seconds"));
    assert.equal(JSON.stringify(result),before,"No tariff, amount, scope or Core state mutation");
});

test("Owner UX: no advisory total is fabricated from components, malformed comparisons or expired states",()=>{
    const {c}=harness();
    for(const row of [
        {scope:"COMPARISON",label:"invalid",assumption:"invalid",amount_usd:"NaN"},
        {scope:"CONDITIONAL_TOTAL",label:"not designated",amount_usd:"1"},
    ])assert.equal(c.costBadgeText({state:"UNKNOWN",planning:{version:"ACI-PLANNING-1",display:"DETAIL_ONLY",scenarios:[row]}}),"PRICE UNKNOWN");
    const planning={version:"ACI-PLANNING-1",display:"DETAIL_ONLY",scenarios:[{scope:"COMPARISON",label:"published scenario",assumption:"not a quote",amount_usd:"0.2"}]};
    assert.equal(c.costBadgeText({state:"INVALID",planning}),"CHECK INPUTS");
    assert.equal(c.costBadgeText({state:"STALE",planning}),"PRICE STALE");
    assert.equal(c.costBadgeText({state:"FORMULA",amount_usd:"4.8535200",planning}),"≈ $4.85 EST.");
});

test("Owner UX: compact decimal precision is bounded without turning tiny positive rates into zero",()=>{
    const {c}=harness();
    for(const [input,expected] of [["0.3267354000000","0.3267"],["4.8535200","4.8535"],["0.20000000000","0.2"],
        ["1.9999999","2"],["0.0000001","<0.0001"],["0","0"],["NaN","?"]])assert.equal(c.costCompactDecimal(input),expected);
    assert.equal(c.costBadgeText({state:"RATE_ONLY",rate_usd:"0.3267354000000",rate_unit:"s"}),"$0.3267/s RATE");
});

test("R2: one read-only tooltip owner, no native title, disclosure, pinning or click handler",()=>{
    const {c,n}=harness();
    const element=tooltipDOM(c);
    const badge=element("button");c.setCostPresentation(n,{state:"FORMULA",amount_usd:"4.8535200",breakdown:[{sku:"duration",quantity:"3",rate_usd:"1.61784",amount_usd:"4.85352"}]});
    c.bindCostBadge(n,badge);assert(!("title" in badge.attributes));
    badge.handlers.mouseenter();badge.handlers.mouseenter();
    assert.equal(c.document.body.children.length,1);
    assert.equal(n.__orvCostPopover.attributes.role,"tooltip");
    assert.equal(n.__orvCostPopover.style.pointerEvents,"none");
    const all=item=>[item,...item.children.flatMap(all)];
    assert(!all(n.__orvCostPopover).some(item=>["button","a","details","summary"].includes(item.tag)));
    assert(!n.__orvCostPopover.textContent.includes("Technical details"));
    assert(!badge.handlers.click);assert(!("aria-haspopup" in badge.attributes));
    assert(!c.costDetailsText(n).includes(" × "));
    badge.handlers.mouseleave();assert.equal(c.document.body.children.length,0);
});

test("Owner UX: renderer and graph switches retire invisible Classic cost owners",()=>{
    const {c,n}=harness();let removed=0;
    const badge={hidden:false,setAttribute(){}};
    n.__orvClassicCostBadge=badge;n.__orvCostPopoverOwner=badge;n.__orvCostPopover={remove(){removed++;}};
    c.document={querySelectorAll(){return [{dataset:{nodeId:String(n.id)}}]}};
    c.syncClassicCostBadge(n,{},{});
    assert.equal(badge.hidden,true);assert.equal(removed,1);assert.equal(n.__orvCostPopover,null);
    badge.hidden=false;n.__orvCostPopoverOwner=badge;n.__orvCostPopover={remove(){removed++;}};n.__orvResumeActualInstalled=true;
    const root={dataset:{nodeId:String(n.id)},classList:{add(){}},querySelector(){return null;}};
    c.document.querySelectorAll=()=>[root];c.syncBetaPresentation(n);
    assert.equal(badge.hidden,true);assert.equal(removed,2);assert.equal(n.__orvCostPopover,null);
    n.graph={};n.__orvCostPopover={remove(){removed++;}};
    c.syncBetaPresentation(n);
    assert.equal(removed,3);assert.equal(n.__orvCostPopover,null);
});
test("R3 expired result cannot present a numerical modelled estimate",async()=>{
    const {c,n,requests}=harness(); const pending=c.refreshEstimate(n);
    respond(requests[0],{state:"RATE_ONLY",planning:modelPlan,valid_for_ms:0});await pending;
    assert.equal(n.__orvEstimate.value,"PRICE STALE");
});
test("R3 expiry timer clears unchanged numerical state",async()=>{
    const {c,n,requests}=harness();const timers=[];let now=0;c.performance.now=()=>now;c.setTimeout=(fn,ms)=>{timers.push({fn,ms});return timers.length;};
    const pending=c.refreshEstimate(n);respond(requests[0],{state:"RATE_ONLY",planning:modelPlan,valid_for_ms:100});await pending;
    assert.equal(n.__orvEstimate.value,"≈ $1.24 MODEL");now=99;assert.equal(c.expireCostPresentation(n),false);now=100;timers.find(t=>t.ms===100).fn();assert.equal(n.__orvEstimate.value,"PRICE STALE");
});

// R3.1 Owner-approved palette; these checks are deliberately presentation-only.
test("R3.1 exact brand palette and unchanged state labels", () => {
    const {c,n}=harness();
    for (const [result,expected,label] of [
        [{state:"FORMULA",amount_usd:"2.31"},"#0ACF83","≈ $2.31 EST."],
        [{state:"RANGE",lower_usd:"1.80",upper_usd:"2.60"},"#0ACF83","$1.80–2.60 EST."],
        [{state:"UNKNOWN",planning:modelPlan},"#FFBB00","≈ $1.24 MODEL"],
        [{state:"PARTIAL",planning:{...modelPlan,display:"SCENARIO_RANGE",scenario_min_usd:"1.80",scenario_max_usd:"2.60"}},"#FFBB00","≈ $1.80–2.60 MODEL"],
        [{state:"RATE_ONLY",rate_usd:"0.28",rate_unit:"s"},"","$0.28/s RATE"],
        [{state:"PARTIAL"},"","COST PARTIAL"],
        [{state:"UNKNOWN"},"","PRICE UNKNOWN"],
        [{state:"STALE",planning:modelPlan},"","PRICE STALE"],
        [{state:"INVALID"},"","CHECK INPUTS"],
        [{state:"CALCULATING"},"","CALCULATING…"],
    ]) {
        c.setCostPresentation(n,result);
        assert.equal(n.__orvEstimate.value,label);
        const colors=c.costBadgeColors(n,label);
        assert.equal(colors.accent,expected||"#C4C4C4");
        assert.equal(colors.background,"#1A1A1A");
    }
});
test("R2 references and components stay Violet and reset to neutral on stale",()=>{
    const {c,n}=harness(); const element=tooltipDOM(c);n.__orvCostPopover=element("div");
    for(const scope of ["COMPARISON","COMPONENT"]){
        c.setCostPresentation(n,{state:"UNKNOWN",planning:{...modelPlan,display:"DETAIL_ONLY",scenarios:[{scope,label:"illustration",amount_usd:"1.20",assumption:"not total"}]}});
        const comparison=scope==="COMPARISON";
        assert.equal(n.__orvEstimate.value,comparison?"≈ $1.20 REF.":"$1.20 REF.");
        assert.equal(c.costBadgeColors(n,n.__orvEstimate.value).accent,"#9E6BFF");
        assert.equal(n.__orvCostPopover.style.borderColor,"#9E6BFF");
    }
    c.setCostPresentation(n,{state:"STALE",planning:modelPlan});
    assert.equal(n.__orvCostPopover.style.borderColor,"#C4C4C4");
});
test("R3.1 collapsed canvas paints brand accent without changing geometry",()=>{
    const {c,n}=harness();n._collapsed_width=300;
    const before=[...n.size];
    for(const [result,expected] of [[{state:"FORMULA",amount_usd:"2.31"},"#0ACF83"],[{state:"UNKNOWN",planning:modelPlan},"#FFBB00"]]){
        c.setCostPresentation(n,result);const drawn=[];
        const ctx={save(){},restore(){},fillRect(){drawn.push(this.fillStyle)},fillText(){drawn.push(this.fillStyle)}};
        c.drawCollapsedCostBadge(n,ctx);
        assert.deepEqual(drawn,["#1A1A1A",expected]);
        assert.deepEqual(Array.from(n.size),before);
    }
});
test("R3.1 Nodes 2.0 applies and resets the same badge tokens",()=>{
    const {c,n}=harness();
    const badge={style:{},textContent:"",title:"",setAttribute(){}};
    const root={dataset:{nodeId:String(n.id)},classList:{add(){}},querySelector(selector){return selector===".lg-node-header > div"?{querySelector(){return badge}}:null}};
    c.document={querySelectorAll(){return [root]}};
    for(const [result,expected] of [[{state:"FORMULA",amount_usd:"2.31"},"#0ACF83"],[{state:"UNKNOWN",planning:modelPlan},"#FFBB00"],[{state:"STALE"},""]]){
        c.setCostPresentation(n,result);c.syncBetaPresentation(n);
        assert.equal(badge.style.color,expected||"#C4C4C4");assert.equal(badge.style.borderColor,expected||"#C4C4C4");
        assert.equal(badge.style.backgroundColor,"#1A1A1A");
    }
});

const r2Reference = {state:"UNKNOWN",reason_codes:["AUDIO_EFFECTIVE_SEMANTICS_UNRESOLVED"],planning:{version:"ACI-PLANNING-1",display:"DETAIL_ONLY",scenarios:[{
    scope:"COMPARISON",label:"with-audio output component (comparison)",sku:"duration_seconds_with_audio_720p",quantity:"4",quantity_unit:"s",amount_usd:"0.278016",
    assumption:"Published with-audio output rate; selected audio and input charges may differ.",charges:[{sku:"duration_seconds_with_audio_720p",quantity:"4",rate_usd:"0.069504",amount_usd:"0.278016"}]
}]}};

test("R2 exact Gemini witness has readable identity, reference geometry/scope and no debug dump",()=>{
    // Presentation witness only; no synthetic catalogue/capability claim.
    const selected={...model,model_id:"test/gemini-presentation-witness",display_name:"Google: Gemini Omni 1.2 Flash"};
    const {c,n}=harness(selected);c.widget(n,"inference_method").value="I2V";c.widget(n,"duration").value=4;
    const before=JSON.stringify(r2Reference);c.setCostPresentation(n,r2Reference);
    const view=c.costTooltipView(n);
    assert.equal(view.kind,"reference");assert.equal(view.amount,"$0.28");assert.equal(view.accent,"#9E6BFF");
    assert.equal(view.identity,"Gemini Omni 1.2 Flash · I2V");assert.equal(view.context,"720p · 4s");
    assert.equal(view.sub,"With audio · Output only");assert.match(view.note,/Input charges may differ/);
    assert.equal(view.sections[0].rows[0][1],"Off");assert.equal(view.sections[0].rows[1][1],"Not established");
    const text=c.costDetailsText(n);
    for(const hidden of ["duration_seconds","0.278016","0.069504","Catalogue observed","Technical details","No completed job","google/"])assert(!text.includes(hidden),hidden);
    assert.equal(JSON.stringify(r2Reference),before);
});

test("R2 locale follows only Comfy.Locale; RU inherits commas and other untranslated host locales fall back to EN",()=>{
    const {c,n}=harness();let locale="ru";
    c.app.ui={settings:{getSettingValue(key){assert.equal(key,"Comfy.Locale");return locale;}}};
    c.navigator={get language(){throw Error("Do not use browser language");}};
    c.setCostPresentation(n,r2Reference);
    assert.equal(n.__orvEstimate.value,"≈ $0,28 REF.");assert.equal(c.costTooltipView(n).title,"Справочная стоимость");
    assert.equal(c.costUsd("0.0001"),"<$0,01");assert.equal(c.costUsd("0"),"$0,00");assert.equal(c.costMoney("0.278016"),"0.28");
    assert.equal(c.costBadgeText({state:"INVALID"}),"ПРОВЕРЬТЕ ВХОДЫ");
    locale="fr";assert.equal(c.costBadgeText({state:"FORMULA",amount_usd:"2.31"}),"≈ $2.31 EST.");
    assert.equal(c.costTooltipView(n).title,"Reference cost");
});

test("R2 locale change refreshes presentation without resetting expiry, changing Core or issuing a request",()=>{
    const {c,n,requests}=harness();let locale="en",handler;
    c.app.ui={settings:{getSettingValue(){return locale;},addEventListener(name,fn){assert.equal(name,"Comfy.Locale.change");handler=fn;}}};
    c.installCostLifecycle(n);c.setCostPresentation(n,{...r2Reference,valid_for_ms:1000});
    const result=n.__orvEstimate.result,expiry=n.__orvCostExpiresAt;assert(handler);
    locale="ru";handler();assert.equal(n.__orvEstimate.value,"≈ $0,28 REF.");
    assert.equal(n.__orvEstimate.result,result);assert.equal(n.__orvCostExpiresAt,expiry);assert.equal(requests.length,0);
    c.performance.now=()=>1001;c.expireCostPresentation(n);assert.equal(n.__orvEstimate.value,"ЦЕНА УСТАРЕЛА");
});

test("R2 does not choose a comparison arbitrarily or replace a primary formula/rate",()=>{
    const {c,n}=harness();const first=r2Reference.planning.scenarios[0];
    const result={...r2Reference,planning:{...r2Reference.planning,scenarios:[first,{...first,amount_usd:"0.4"}]}};
    c.setCostPresentation(n,result);const view=c.costTooltipView(n);
    assert.equal(n.__orvEstimate.value,"COST DETAILS");assert.equal(view.amount,null);assert.equal(view.sections[0].rows.length,2);
    assert.equal(c.costBadgeText({...r2Reference,state:"FORMULA",amount_usd:"1"}),"≈ $1.00 EST.");
    c.setCostPresentation(n,{...r2Reference,state:"RATE_ONLY",rate_usd:"0.28",rate_unit:"s"});
    assert.equal(n.__orvEstimate.value,"$0.28/s RATE");assert.equal(c.costTooltipView(n).sections.at(-1).rows.length,1);
    assert.equal(c.costBadgeText({...result,state:"STALE"}),"PRICE STALE");
});

test("R2 keeps exact bounds while outward display rounding avoids false equality",()=>{
    const {c}=harness();
    assert.equal(c.costBadgeText({state:"RANGE",lower_usd:"0.208512",upper_usd:"0.208513"}),"$0.20–0.21 EST.");
    assert.equal(c.costUsd("0.0000001"),"<$0.01");assert.equal(c.costUsd("0"),"$0.00");
    assert.equal(c.costBadgeText({state:"UNKNOWN",planning:{...modelPlan,display:"SCENARIO_RANGE",scenario_min_usd:"1.8",scenario_max_usd:"2.6"}}),"≈ $1.80–2.60 MODEL");
});

test("R2 normative metrics use common screen-space DOM with no focusable or scrollable descendants",()=>{
    const {c,n}=harness();const element=tooltipDOM(c);c.setCostPresentation(n,r2Reference);const detail=element("div");c.renderCostDetails(n,detail);
    const all=item=>[item,...item.children.flatMap(all)],items=all(detail),find=name=>items.find(item=>item.className===`orv-cost-${name}`);
    assert.equal(detail.style.width,"430px");assert.equal(detail.style.boxSizing,"border-box");assert.equal(detail.style.padding,"12px");assert.equal(detail.style.pointerEvents,"none");
    assert.equal(find("heading").style.fontSize,"13px");assert.equal(find("heading").style.lineHeight,"18px");assert.equal(find("heading").style.fontWeight,"600");
    assert.equal(find("context").style.lineHeight,"18px");assert.equal(find("identity").style.lineHeight,"18px");
    assert.equal(find("amount").style.fontSize,"20px");assert.equal(find("amount").style.lineHeight,"24px");assert.equal(find("amount").style.letterSpacing,"-0.35px");
    assert.equal(find("note").style.fontSize,"11px");assert.equal(find("note").style.lineHeight,"16px");
    assert(!items.some(item=>["details","summary","a","button","input"].includes(item.tag)||item.tabIndex>=0));
    assert(!detail.style.maxHeight);assert(!detail.style.overflow);
    c.setCostPresentation(n,{state:"RANGE",lower_usd:"1.8",upper_usd:"2.6"});c.renderCostDetails(n,detail);
    assert.equal(all(detail).find(item=>item.className==="orv-cost-amount").style.fontSize,"17px");
});

test("R2 tooltip placement uses measured bounds and closes when its anchor disappears",()=>{
    const {c,n}=harness(),element=tooltipDOM(c);const badge=element("span");c.setCostPresentation(n,r2Reference);c.bindCostBadge(n,badge);
    badge.getBoundingClientRect=()=>({left:900,top:650,right:990,bottom:670,width:90,height:20});
    badge.handlers.mouseenter();assert.equal(n.__orvCostPopover.style.top,"446px");assert.equal(n.__orvCostPopover.style.left,"562px");
    badge.isConnected=false;c.positionCostTooltip(n,badge);assert.equal(n.__orvCostPopover,null);
    badge.isConnected=true;badge.handlers.focus();assert(n.__orvCostPopover);badge.handlers.blur();assert.equal(n.__orvCostPopover,null);
});
