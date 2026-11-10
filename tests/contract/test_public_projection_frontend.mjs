import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import test from "node:test";
const source = readFileSync(new URL("../../web/openrouter_video.js", import.meta.url), "utf8").replace(/^import .*;\r?\n/gm, "");
const fixture = JSON.parse(readFileSync(new URL("../fixtures/capability-audit-ui-projection.json", import.meta.url), "utf8"));
const graph = { links: {}, nodes: {}, getNodeById(id) { return this.nodes[id]; } };
const payloads = [];
const c = { app: { graph, registerExtension() {} }, api: { async fetchApi(url, init) { payloads.push(JSON.parse(init.body)); return { ok: true, async json() { return { availability: "UNAVAILABLE" }; } }; } }, clearTimeout() {}, setTimeout() { return 0; } };
vm.runInNewContext(source, c);
const plain = value => JSON.parse(JSON.stringify(value));
const model = id => fixture.models.find(m => m.model_id === id);
const reconciledGoogle = JSON.parse(readFileSync(new URL('../fixtures/op07-google-ui-projection.json',import.meta.url),'utf8'));
for (const capability of reconciledGoogle.models) for (const method of ['T2V','I2V','FLF2V']) {
    test(`OP07 ${capability.model_id} restores ${method} controls in bounded profile`,()=>{
        const n=node(capability.model_id,method);
        apply(n,capability,method);
        for(const name of ['prompt','duration','resolution','aspect_ratio']) assert(!widget(n,name).hidden,name);
        assert.equal(widget(n,'duration').value,8);
        assert.equal(widget(n,'resolution').value,'720p');
        assert.equal(widget(n,'aspect_ratio').value,'16:9');
        for(const name of ['size','seed','generate_audio']) assert(widget(n,name).hidden,name);
        assert.equal(n.inputs.some(i=>i.name==='first_frame'),method!=='T2V');
        assert.equal(n.inputs.some(i=>i.name==='last_frame'),method==='FLF2V');
    });
}
for (const method of ["V2V_EDIT", "V2V_EXTEND"]) test(`Seedance ${method} source, optional limits and saved media intent`, async () => {
    const capability = model("bytedance/seedance-2.5");
    const n = node(capability.model_id, method);
    apply(n, capability);
    assert(widget(n, "inference_method").options.values.includes(method));
    assert(n.inputs.some(i => i.name === "source_video" && i.type.includes("VIDEO")));
    assert(!n.inputs.some(i => ["first_frame", "last_frame"].includes(i.name)));
    assert(!widget(n, "inference_method").options.values.some(v => /draft/i.test(v)));
    const topology = capability.method_profiles[method].topology;
    assert(c.referenceShapeValid(topology, []));
    assert(!c.referenceShapeValid(topology, Array(10).fill("video")));
    assert(!c.referenceSocketType(topology, Array(9).fill("video")).split(",").includes("VIDEO"));
    const origin = { outputs: [{ type: "VIDEO" }], connect(slot, target, targetSlot) {
        const id = 77;
        graph.links[id] = { origin_id: 76, origin_slot: slot, target_id: target.id, target_slot: targetSlot, type: "VIDEO" };
        target.inputs[targetSlot].link = id;
    } };
    graph.nodes[76] = origin;
    origin.connect(0, n, n.inputs.findIndex(i => i.name === "source_video"));
    await c.refreshEstimate(n);
    assert.equal(payloads.at(-1).source_video_present, true);
    assert.equal(payloads.at(-1).inference_method, method);
    const away = model("x-ai/grok-imagine-video-1.5-lite");
    widget(n, "model").value = away.model_id;
    apply(n, away);
    assert(!n.inputs.some(i => i.name === "source_video"));
    assert(!widget(n, "inference_method").options.values.includes(method));
    const saved = plain(n.properties);
    const restored = node(capability.model_id, method);
    restored.properties = saved;
    apply(restored, capability, method);
    assert.equal(restored.inputs.find(i => i.name === "source_video").link, 77);
    assert.equal(widget(restored, "inference_method").value, method);
});
const widget = (node, name) => node.widgets.find(w => w.name === name);
function node(modelId, method = "T2V") {
    const values = { model: modelId, inference_method: method, prompt: "prompt", resolution: "720p", aspect_ratio: "16:9", duration: 8, size: "", seed: 42, generate_audio: false, geometry_authority: "NORMALIZED", "control after generate": "fixed" };
    return { id: 42, size: [400, 450], properties: {}, __orvEstimate: { value: "" }, __orvCapabilityStatus: { value: "" }, widgets: Object.entries(values).map(([name, value]) => ({ name, value, options: {}, computeSize: () => [0, 20] })), inputs: [],
        addInput(name, type) { this.inputs.push({ name, type, link: null }); },
        removeInput(index) { const input = this.inputs[index]; if (input.link != null) delete graph.links[input.link]; this.inputs.splice(index, 1); this.inputs.forEach((item, slot) => { if (item.link != null && graph.links[item.link]) graph.links[item.link].target_slot = slot; }); },
        setDirtyCanvas() {}, computeSize() { return [400, 200]; }, setSize(size) { this.size = size; } };
}
function apply(n, capability, method = widget(n, "inference_method").value) {
    n.__orvModelCapability = capability;
    widget(n, "inference_method").value = method;
    const selected = c.configureInferenceMethod(n, capability);
    return c.reprojectNodeSemantics(n, capability, selected);
}

for (const method of ["T2V", "I2V", "FLF2V", "MI2V", "VR2V", "MMR2V"]) test(`RC upgrade preserves accepted ${method} values and compatible links`, () => {
    const capability = model("bytedance/seedance-2.5");
    const before = node(capability.model_id, method);
    apply(before, capability);
    const media = before.inputs.find(input => input.name === "first_frame" || input.name.startsWith("direct_references."));
    if (media) {
        const type = method === "VR2V" ? "VIDEO" : "IMAGE";
        graph.nodes[901] = { outputs: [{ type }] };
        graph.links[902] = { origin_id: 901, origin_slot: 0, target_id: before.id, target_slot: before.inputs.indexOf(media), type };
        media.link = 902;
    }
    const saved = plain({ properties: before.properties, widgets: before.widgets.map(item => [item.name, item.value]), inputs: before.inputs });
    const restored = node(capability.model_id, method);
    restored.properties = saved.properties;
    restored.inputs = saved.inputs;
    for (const [name, value] of saved.widgets) {
        const target = widget(restored, name);
        if (target) target.value = value;
    }
    apply(restored, capability);
    assert.equal(widget(restored, "inference_method").value, method);
    assert.equal(widget(restored, "duration").value, widget(before, "duration").value);
    if (media) assert(restored.inputs.some(input => input.name === media.name && input.link === 902));
    assert(!restored.inputs.some(input => input.name === "source_video"));
    assert(!JSON.stringify(saved).includes("api_key"));
});

for (const capability of fixture.models) test(`supported-only projection for ${capability.model_id}`, () => {
    const n = node(capability.model_id, "AR2V");
    apply(n, capability);
    const picker = widget(n, "inference_method");
    assert.deepEqual(plain(picker.options.values), capability.supported_inference_methods);
    if (capability.supported_inference_methods.length) assert(capability.supported_inference_methods.includes(picker.value));
    else assert(picker.hidden);
    const profile = n.__orvCapability.__methodProfile;
    for (const field of ["duration", "resolution", "aspect_ratio", "size", "seed", "generate_audio"]) {
        assert.equal(widget(n, field).hidden, profile.controls?.[field]?.state !== "SUPPORTED", field);
    }
});

test("invalid saved method never becomes selected or an option; existing deterministic fallback is used", () => {
    const capability = model("bytedance/seedance-2.0-mini");
    const n = node(capability.model_id, "AR2V");
    apply(n, capability);
    assert.equal(widget(n, "inference_method").value, capability.preferred_inference_method || capability.supported_inference_methods[0]);
    assert(!widget(n, "inference_method").options.values.includes("AR2V"));
    assert.equal(n.properties.orv_capability_intent.methods[capability.model_id], "AR2V");
    assert(!n.inputs.some(i => i.type === "AUDIO,OPENROUTER_VIDEO_INPUT_REFERENCE"));
});

test("MI2V sockets are image-only; MMR keeps AUDIO without AUDIO-only completion", () => {
    const mini = model("bytedance/seedance-2.0-mini");
    const n = node(mini.model_id, "MI2V");
    apply(n, mini);
    assert.equal(n.inputs[0].type, "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE");
    apply(n, mini, "MMR2V");
    assert(n.inputs[0].type.split(",").includes("AUDIO"));
    const next = c.referenceSocketType(mini.method_profiles.MMR2V.topology, ["audio", "audio"]);
    assert(!next.split(",").includes("AUDIO"));
    assert(next.split(",").includes("IMAGE"));
    assert(next.split(",").includes("VIDEO"));
});

test("model/method switch parks incompatible links and save/reload restores compatible origins", () => {
    const capability = model("x-ai/grok-imagine-video-1.5-lite");
    const origin = { outputs: [{ type: "IMAGE" }], connect(slot, target, targetSlot) { const id = 9; graph.links[id] = { origin_id: 1, origin_slot: slot, target_id: target.id, target_slot: targetSlot, type: "IMAGE" }; target.inputs[targetSlot].link = id; } };
    graph.nodes[1] = origin;
    const n = node(capability.model_id, "I2V");
    apply(n, capability);
    origin.connect(0, n, n.inputs.findIndex(i => i.name === "first_frame"));
    apply(n, capability, "T2V");
    assert(!n.inputs.some(i => i.name === "first_frame"));
    assert.equal(n.properties.orv_capability_intent.media.length, 1);
    const saved = plain(n.properties);
    const reloaded = node(capability.model_id, "I2V");
    reloaded.properties = saved;
    apply(reloaded, capability);
    assert.equal(reloaded.inputs.find(i => i.name === "first_frame").link, 9);
    assert.equal(reloaded.properties.orv_capability_intent.media.length, 0);
});

test("hidden scalars and media cannot affect estimate; local control is retained", async () => {
    const capability = model("x-ai/grok-imagine-video-1.5-lite");
    const n = node(capability.model_id);
    widget(n, "seed").value = "malformed";
    widget(n, "generate_audio").value = true;
    widget(n, "size").value = "stale";
    apply(n, capability);
    c.syncAdvancedControls(n);
    await c.refreshEstimate(n);
    const payload = payloads.at(-1);
    assert.equal(payload.generate_audio, false);
    assert.equal(payload.size, null);
    assert.equal(payload.reference_count, 0);
    assert.equal(widget(n, "control after generate").value, "fixed");
    assert.equal(Boolean(widget(n, "control after generate").hidden), false);
    assert.equal(n.__orvCapabilityStatus.hidden, true);
});

test("sparse Duration and method-dependent duration domains reproject synchronously", () => {
    const capability = model("google/veo-3.1");
    const n = node(capability.model_id);
    apply(n, capability);
    assert.deepEqual(plain(n.__orvDurationValues), [4, 6, 8]);
    apply(n, capability, "FLF2V");
    assert.deepEqual(plain(n.__orvDurationValues), [8]);
    assert.deepEqual(n.inputs.map(i => i.name), ["first_frame", "last_frame"]);
    apply(n, capability, "T2V");
    assert.deepEqual(plain(n.__orvDurationValues), [4, 6, 8]);
});

test("restricted resolution, exact authority and unknown tier remain the accepted geometry UI", () => {
    const capability = model("runway/gen-4.5");
    const n = node(capability.model_id);
    widget(n, "size").value = "1280x720";
    widget(n, "geometry_authority").value = "EXACT";
    apply(n, capability);
    assert.equal(widget(n, "resolution").hidden, false);
    assert.equal(widget(n, "aspect_ratio").hidden, false);
    assert.equal(widget(n, "size").hidden, false);
    assert.equal(c.geometryAuthority(n), "EXACT");
    assert(!widget(n, "size").options.values.includes("480x480"));
    assert.equal(widget(n, "duration").hidden, false);
});

test("UNKNOWN/UNSUPPORTED/CONFLICT are hidden, supported future evidence appears with no model branch", () => {
    const capability = plain(model("bytedance/seedance-2.0-mini"));
    capability.model_id = "future/model";
    const n = node(capability.model_id);
    for (const state of ["UNKNOWN", "UNSUPPORTED", "CONFLICT"]) {
        capability.method_profiles.AR2V = { state, controls: {}, topology: {} };
        capability.supported_inference_methods = ["T2V", "AR2V"];
        apply(n, capability, "AR2V");
        assert(!widget(n, "inference_method").options.values.includes("AR2V"));
    }
    capability.method_profiles.AR2V = { state: "SUPPORTED", controls: {}, topology: { fixed: [], reference_kinds: ["audio"], kind_sets: [["audio"]], min: 1, max: 1, per_kind_max: { audio: 1 } } };
    apply(n, capability, "AR2V");
    assert.equal(widget(n, "inference_method").value, "AR2V");
    assert.equal(n.inputs[0].type, "AUDIO,OPENROUTER_VIDEO_INPUT_REFERENCE");
});

test("no provider/model condition branches or generation submit was added to frontend", () => {
    assert(!/if\s*\([^)]*(?:seedance|grok|bytedance\/|x-ai\/|minimax\/|google\/)/i.test(source));
    assert(!source.includes("/api/v1/videos"));
    assert(!source.includes("/prompt"));
});

test("legacy collection shape is known only from the owned typed producer and carriers stay exclusive", () => {
    graph.nodes[101] = { type: "LoadImage", outputs: [{ type: "IMAGE" }] };
    graph.nodes[102] = { type: "OpenRouterVideoImageReference" };
    graph.nodes[103] = { type: "OpenRouterVideoReferenceCollection", inputs: [
        { name: "references.reference_7", link: 702 }, { name: "references.reference_2", link: 701 } ] };
    graph.links[701] = { origin_id: 101, origin_slot: 0 };
    graph.links[702] = { origin_id: 102, origin_slot: 0 };
    const capability = model("x-ai/grok-imagine-video");
    const n = node(capability.model_id, "MI2V");
    n.addInput("input_references", "OPENROUTER_VIDEO_INPUT_REFERENCES");
    n.inputs[0].link = 700;
    graph.links[700] = { origin_id: 103, origin_slot: 0, target_id: n.id, target_slot: 0 };
    apply(n, capability);
    assert.deepEqual(plain(c.selectedReferenceKinds(n)), ["image", "image"]);
    assert(!n.inputs.some(input => input.name.startsWith("direct_references.")));
    graph.nodes[102] = { type: "OpenRouterVideoAudioReference" };
    apply(n, capability);
    assert(!n.inputs.some(input => input.name === "input_references"));
    assert(n.properties.orv_capability_intent.media.some(input => input.origin_id === 103));
});

test("supported Seed uses confirmed bounds and preserves rejected intent without a deterministic promise", () => {
    const capability = plain(model("bytedance/seedance-2.0-mini"));
    capability.model_id = "future/seed";
    capability.method_profiles.T2V.controls.seed = { state: "SUPPORTED", integer_range: { min: 0, max: 99 } };
    const n = node(capability.model_id);
    widget(n, "seed").value = 100;
    apply(n, capability);
    assert.equal(widget(n, "seed").hidden, false);
    assert.equal(widget(n, "seed").options.max, 99);
    assert.equal(widget(n, "seed").value, -1);
    assert.equal(n.properties.orv_capability_intent.inactive[`${capability.model_id}|T2V`].seed, 100);
});

test("publishing nested visibility preserves public collection identities, order, links and values", () => {
    const n = node("fixture/model");
    n.addInput("first_frame", "IMAGE"); n.inputs[0].link = 99;
    const widgets = n.widgets, inputs = n.inputs;
    const before = plain({ widgets: n.widgets.map(item => [item.name, item.value]), inputs: n.inputs });
    c.publishSemanticProjection(n);
    widget(n, "size").hidden = true;
    c.publishSemanticProjection(n);
    assert.equal(n.widgets, widgets); assert.equal(n.inputs, inputs);
    assert.deepEqual(plain({ widgets: n.widgets.map(item => [item.name, item.value]), inputs: n.inputs }), before);
});

test("local Control After Generate remains available when upstream Seed is omitted", () => {
    const n = node("fixture/model");
    const seed = widget(n, "seed"), local = widget(n, "control after generate");
    seed.hidden = true; local.options.canvasOnly = true;
    c.syncAdvancedControls(n);
    assert.equal(local.options.canvasOnly, false);
    assert.equal(local.hidden, undefined);
    assert.equal(local.value, "fixed");
    seed.hidden = false;
    c.syncAdvancedControls(n);
    assert.equal(local.options.canvasOnly, true);
});
const currentProjection = JSON.parse(readFileSync(new URL('../fixtures/op07-full-parity-ui-projection.json', import.meta.url),'utf8'));
function operationNode(id, method) {
    const n=node(id,method);
    for(const [name,value] of Object.entries({previous_job_id:'',upscale_factor:'',creativity:-1,provider_options:''}))
        n.widgets.push({name,value,type:name==='creativity'?'number':'text',options:{},computeSize:()=>[0,20]});
    n.addWidget=(type,name,value,callback,options={})=>{
        const w={type,name,value,callback,options,computeSize:()=>[0,20]};n.widgets.push(w);return w;
    };
    return n;
}
for(const capability of currentProjection.models) for(const method of capability.supported_inference_methods) {
    test(`current catalogue UI projects ${capability.model_id} / ${method}`,()=>{
        const n=operationNode(capability.model_id,method);
        apply(n,capability,method);
        const profile=capability.method_profiles[method];
        for(const name of ['prompt','duration','resolution','aspect_ratio','size','seed','generate_audio','previous_job_id','upscale_factor','creativity']){
            assert.equal(!widget(n,name).hidden,profile.controls[name]?.state==='SUPPORTED',name);
        }
        for(const fixed of profile.topology.fixed)assert(n.inputs.some(i=>i.name===fixed),fixed);
    });
}
test('upscale factor and creativity are editable native controls and retain workflow values',()=>{
    const capability=currentProjection.models.find(m=>m.model_id==='black-forest-labs/flux-video-upscale');
    const n=operationNode(capability.model_id,'V2V_UPSCALE');apply(n,capability);
    assert.equal(widget(n,'upscale_factor').type,'number');
    assert.equal(widget(n,'upscale_factor').options.min,1.5);
    assert.equal(widget(n,'upscale_factor').options.max,3);
    assert.deepEqual(plain(widget(n,'creativity').options.values),[0,1]);
    widget(n,'upscale_factor').value=2.75;widget(n,'creativity').value=1;
    const saved=plain({properties:n.properties,values:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    const restored=operationNode(capability.model_id,'V2V_UPSCALE');restored.properties=saved.properties;
    for(const [name,value]of Object.entries(saved.values))if(widget(restored,name))widget(restored,name).value=value;
    apply(restored,capability);
    assert.equal(widget(restored,'upscale_factor').value,2.75);
    assert.equal(widget(restored,'upscale_factor').serializeValue(),'2.75');
    assert.equal(widget(restored,'creativity').value,1);
});
test('provider controls reset empty state, preserve serialized values and do not expose raw JSON',()=>{
    const capability=currentProjection.models.find(m=>m.model_id==='heygen/avatar-iv');
    const n=operationNode(capability.model_id,'IR2V');apply(n,capability);
    const name='provider_option:heygen::voice_id', option=widget(n,name);
    assert(option && !option.hidden);
    assert(widget(n,'provider_options').hidden);
    option.callback('TEST_ONLY_VOICE');
    assert.equal(JSON.parse(widget(n,'provider_options').value)[0].value,'TEST_ONLY_VOICE');
    widget(n,'provider_options').value='';c.configureOperationControls(n,capability.method_profiles.IR2V);
    assert.equal(option.value,'');
    widget(n,'provider_options').value=JSON.stringify([{provider:'heygen',key:'voice_settings',value:'unreviewed'}]);
    assert.match(c.configureOperationControls(n,capability.method_profiles.IR2V),/no longer supported/);
    assert.equal(JSON.parse(widget(n,'provider_options').value)[0].key,'voice_settings');
});
test('original Unicode identity and geometry characters remain intact',()=>{
    assert(source.includes('ARENAS\u00aelab'));
    assert(source.includes('[x\u00d7]'));
    assert(!source.includes('\u0420\u00ae'));
});

test('optional provider boolean distinguishes default, true and false through workflow storage',()=>{
    const capability=currentProjection.models.find(m=>m.model_id==='google/veo-3.1-lite');
    const n=operationNode(capability.model_id,'T2V');apply(n,capability,'T2V');
    const option=widget(n,'provider_option:google-vertex:parameters:enhancePrompt');
    const storage=widget(n,'provider_options');
    assert.equal(option.type,'combo');
    assert.equal(option.value,'AUTO / PROVIDER DEFAULT');
    assert.equal(storage.value,'');
    option.callback('false');
    assert.equal(JSON.parse(storage.value)[0].value,false);
    c.configureOperationControls(n,capability.method_profiles.T2V);
    assert.equal(option.value,'false');
    option.callback('true');
    assert.equal(JSON.parse(storage.value)[0].value,true);
    option.callback('AUTO / PROVIDER DEFAULT');
    assert.deepEqual(JSON.parse(storage.value),[]);
});

test('Omni edit allows six image guides in addition to its fixed video source',()=>{
    const capability=currentProjection.models.find(m=>m.model_id==='google/gemini-omni-1.2-flash');
    const n=operationNode(capability.model_id,'V2V_EDIT');apply(n,capability,'V2V_EDIT');
    const scoped=c.scopedCapability(capability,'V2V_EDIT');
    const sourceInput=n.inputs.find(i=>i.name==='source_video');
    sourceInput.link=8800;graph.links[8800]={origin_id:8800,origin_slot:0,type:'VIDEO'};
    for(let i=0;i<6;i++){
        c.configureReferenceTopology(n,scoped,'V2V_EDIT');
        const free=n.inputs.find(input=>/reference_\d+$/.test(input.name)&&input.link==null);
        assert(free,`guide ${i+1} must remain connectable`);
        free.link=8801+i;graph.links[8801+i]={origin_id:8801+i,origin_slot:0,type:'IMAGE'};
    }
    c.configureReferenceTopology(n,scoped,'V2V_EDIT');
    assert.equal(n.inputs.filter(i=>/reference_\d+$/.test(i.name)&&i.link!=null).length,6);
    assert(!n.inputs.some(i=>/reference_\d+$/.test(i.name)&&i.link==null));
    assert.equal(n.__orvReferenceInvalid,false);
});

test('nested provider leaves retain siblings, zero and explicit omission across workflow reload',()=>{
    const n=operationNode('test/nested','T2V');
    const profile={controls:{provider_options:{state:'SUPPORTED',providers:{runway:{contentModeration:{type:'object',fields:{
        publicFigureThreshold:{type:'string',values:['auto','low']},
        testNumber:{type:'number',min:0,max:1,omitted_default:0.5}
    }}}}}}};
    assert.equal(c.configureOperationControls(n,profile),'');
    const prefix='provider_option:runway::contentModeration:';
    const threshold=widget(n,prefix+'publicFigureThreshold');
    const number=widget(n,prefix+'testNumber'), mode=widget(n,prefix+'testNumber:override');
    assert(number.hidden); assert.equal(number.value,0.5);
    threshold.callback('low');
    mode.callback('SET'); number.callback(0);
    let saved=JSON.parse(widget(n,'provider_options').value);
    assert.equal(saved.length,2);
    assert.equal(saved.find(v=>v.path[0]==='testNumber').value,0);
    const restored=operationNode('test/nested','T2V');
    widget(restored,'provider_options').value=JSON.stringify(saved);
    c.configureOperationControls(restored,profile);
    assert.equal(widget(restored,prefix+'testNumber').value,0);
    assert(!widget(restored,prefix+'testNumber').hidden);
    assert.equal(widget(restored,prefix+'publicFigureThreshold').value,'low');
    widget(restored,prefix+'testNumber:override').callback('AUTO / PROVIDER DEFAULT');
    saved=JSON.parse(widget(restored,'provider_options').value);
    assert.equal(saved.length,1); assert.equal(saved[0].path[0],'publicFigureThreshold');
    assert(widget(restored,prefix+'testNumber').hidden);
    assert(widget(restored,'provider_options').hidden);
});

test('reviewed prompt constraints are visible without truncating saved text',()=>{
    const capability=plain(currentProjection.models.find(m=>m.model_id==='minimax/hailuo-2.3'));
    Object.assign(capability.method_profiles.I2V.controls.prompt,{required:false,max_length:2000});
    const n=operationNode(capability.model_id,'I2V');
    widget(n,'prompt').value='x'.repeat(2001);
    apply(n,capability,'I2V');
    assert.equal(widget(n,'prompt').label,'Prompt (optional)');
    assert.match(widget(n,'prompt').options.tooltip,/maximum 2000 characters/);
    assert.equal(widget(n,'prompt').value.length,2001);
    Object.assign(capability.method_profiles.I2V.controls.prompt,{required:true,max_length:4096,min_length:1});
    apply(n,capability,'I2V');
    assert.equal(widget(n,'prompt').label,'Prompt');
    assert.match(widget(n,'prompt').options.tooltip,/minimum 1 characters/);
});

test('provider object variants project only selected fields and preserve incompatible workflow intent',()=>{
    const n=operationNode('test/variants','T2V');
    const profile={controls:{provider_options:{state:'SUPPORTED',providers:{heygen:{voice_settings:{type:'object',fields:{engine_settings:{
        type:'object',required_fields:['engine_type'],fields:{engine_type:{type:'string',values:['elevenlabs','fish','starfish']},
            model:{type:'string'},style:{type:'number',min:0,max:1},similarity:{type:'number',min:0,max:1}},
        variants:{discriminator_field:'engine_type',cases:{
            elevenlabs:{forbidden_fields:['similarity'],field_values:{model:['eleven_v3','eleven_v4']}},
            fish:{forbidden_fields:['style'],field_values:{model:['s2-pro','s2.1-pro']}},
            starfish:{forbidden_fields:['model','style','similarity']}
        }}
    }}}}}}}};
    c.configureOperationControls(n,profile);
    const prefix='provider_option:heygen::voice_settings:engine_settings:';
    assert(!widget(n,prefix+'model'));
    widget(n,prefix+'engine_type').callback('elevenlabs');
    assert(!widget(n,prefix+'model').hidden);
    assert.deepEqual(plain(widget(n,prefix+'model').options.values),['AUTO / PROVIDER DEFAULT','eleven_v3','eleven_v4']);
    widget(n,prefix+'model').callback('eleven_v4');
    widget(n,prefix+'engine_type').callback('fish');
    assert.equal(widget(n,prefix+'model').value,'eleven_v4');
    assert.match(c.configureOperationControls(n,profile),/explicit replacement/);
    assert.deepEqual(plain(widget(n,prefix+'model').options.values),['AUTO / PROVIDER DEFAULT','s2-pro','s2.1-pro']);
    widget(n,prefix+'model').callback('s2.1-pro');
    assert.equal(c.configureOperationControls(n,profile),'');
    widget(n,prefix+'engine_type').callback('starfish');
    assert(widget(n,prefix+'model').hidden);
    assert.match(c.configureOperationControls(n,profile),/explicit replacement/);
    assert(JSON.parse(widget(n,'provider_options').value).some(v=>v.value==='s2.1-pro'));
    widget(n,prefix+'engine_type').callback('fish');
    assert(!widget(n,prefix+'model').hidden);
    assert.equal(widget(n,prefix+'model').value,'s2.1-pro');
    assert.equal(c.configureOperationControls(n,profile),'');
});

test('bounded provider arrays use named row controls, preserve ordering and reload typed values',()=>{
    const n=operationNode('runway/aleph-2','V2V_EDIT');
    const keyframes={type:'array',min_items:1,max_items:5,items:{type:'object',required_fields:['uri'],one_of_required:[['seconds','at']],fields:{
        uri:{type:'string'},seconds:{type:'number',min:0,max:30},at:{type:'number',min:0,max:1}
    }}};
    const profile={controls:{provider_options:{state:'SUPPORTED',providers:{runway:{keyframes}}}}};
    c.configureOperationControls(n,profile);
    const prefix='provider_option:runway::keyframes:';
    const count=widget(n,prefix+'count');
    assert.deepEqual(plain(count.options.values),[0,1,2,3,4,5]);
    count.callback(2);
    assert.match(c.configureOperationControls(n,profile),/Complete each/);
    widget(n,prefix+'0:uri').callback('https://example.test/first.png');
    widget(n,prefix+'0:seconds:override').callback('SET');
    widget(n,prefix+'0:seconds').callback(0);
    widget(n,prefix+'1:uri').callback('https://example.test/last.png');
    widget(n,prefix+'1:at:override').callback('SET');widget(n,prefix+'1:at').callback(1);
    assert.equal(c.configureOperationControls(n,profile),'');
    const saved=widget(n,'provider_options').value;
    const restored=operationNode('runway/aleph-2','V2V_EDIT');
    widget(restored,'provider_options').value=saved;c.configureOperationControls(restored,profile);
    assert.equal(widget(restored,prefix+'count').value,2);
    assert.equal(widget(restored,prefix+'0:seconds').value,0);
    assert.equal(widget(restored,prefix+'1:at').value,1);
    widget(restored,prefix+'count').callback(1);
    assert(JSON.parse(widget(restored,'provider_options').value).every(v=>v.path[0]===0));
    assert(widget(restored,prefix+'1:uri').hidden);
    widget(restored,prefix+'count').callback(0);
    assert.deepEqual(JSON.parse(widget(restored,'provider_options').value),[]);
    assert(widget(restored,'provider_options').hidden);
});

test('provider option estimate guard invalidates a prior in-flight numeric estimate',async()=>{
    const capability=currentProjection.models.find(m=>m.model_id==='google/veo-3.1-lite');
    const n=operationNode(capability.model_id,'T2V');apply(n,capability,'T2V');
    const previous=c.api.fetchApi;
    let resolve;
    c.api.fetchApi=()=>new Promise(done=>{resolve=done;});
    try{
        const pending=c.refreshEstimate(n);
        widget(n,'provider_options').value=JSON.stringify([{provider:'google-vertex',container:'parameters',key:'enhancePrompt',value:false}]);
        await c.refreshEstimate(n);
        assert.equal(n.__orvEstimate.value,'ESTIMATE UNAVAILABLE');
        resolve({ok:true,async json(){return {availability:'AVAILABLE',estimated_cost_usd:'1'};}});
        await pending;
        assert.equal(n.__orvEstimate.value,'ESTIMATE UNAVAILABLE');
    }finally{c.api.fetchApi=previous;}
});

test('avatar audio workflow preserves its exact method and mixed sockets, while script voice intent survives switching',()=>{
    const capability=currentProjection.models.find(m=>m.model_id==='heygen/avatar-iv');
    const n=operationNode(capability.model_id,'IR2V');apply(n,capability,'IR2V');
    widget(n,'provider_option:heygen::voice_id').callback('TEST_ONLY_VOICE');
    apply(n,capability,'AVATAR_AUDIO');
    assert.equal(widget(n,'inference_method').value,'AVATAR_AUDIO');
    assert(widget(n,'prompt').hidden);
    assert(widget(n,'provider_option:heygen::voice_id').hidden);
    const scoped=c.scopedCapability(capability,'AVATAR_AUDIO');
    for(const [index,kind]of ['IMAGE','AUDIO'].entries()){
        c.configureReferenceTopology(n,scoped,'AVATAR_AUDIO');
        const input=n.inputs.find(i=>/reference_\d+$/.test(i.name)&&i.link==null);
        assert(input && input.type.split(',').includes(kind));
        const id=9500+index;
        graph.nodes[id]={outputs:[{type:kind}]};
        graph.links[id]={origin_id:id,origin_slot:0,type:kind};input.link=id;
    }
    c.configureReferenceTopology(n,scoped,'AVATAR_AUDIO');
    assert.equal(n.__orvReferenceInvalid,false);
    const saved=plain({properties:n.properties,inputs:n.inputs,values:Object.fromEntries(n.widgets.filter(w=>w.serialize!==false).map(w=>[w.name,w.value]))});
    const restored=operationNode(capability.model_id,'AVATAR_AUDIO');restored.properties=saved.properties;restored.inputs=saved.inputs;
    for(const [name,value]of Object.entries(saved.values))if(widget(restored,name))widget(restored,name).value=value;
    apply(restored,capability,'AVATAR_AUDIO');
    assert.equal(widget(restored,'inference_method').value,'AVATAR_AUDIO');
    assert.equal(restored.inputs.filter(i=>i.link!=null).length,2);
    assert(widget(restored,'prompt').hidden);
    apply(n,capability,'IR2V');
    assert.equal(widget(n,'provider_option:heygen::voice_id').value,'TEST_ONLY_VOICE');
});
