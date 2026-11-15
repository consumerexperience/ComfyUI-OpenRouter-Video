import assert from 'node:assert/strict';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test, { after } from 'node:test';

// Offline VM graph contract. This harness is not native ComfyUI acceptance.
const sourceBytes = readFileSync(process.env.ORV_QA_SOURCE || new URL('../../web/openrouter_video.js', import.meta.url));
const source = sourceBytes.toString('utf8').replace(/^import .*;\r?\n/gm, '');
const catalogueURL = new URL('../fixtures/op07-topology-catalogue-b628912.json', import.meta.url);
const catalogueBytes = readFileSync(catalogueURL);
assert.equal(createHash('sha256').update(catalogueBytes).digest('hex'),'9a737ab893728eefb7f65716710ccb8e75938d59b80a3f851d16979c11a9c833','immutable b628912 captured catalogue bytes');
const catalogue = JSON.parse(catalogueBytes);
const suiteSHA256=createHash('sha256').update(readFileSync(new URL(import.meta.url))).digest('hex');
// Derive profiles from the exact captured bytes through the existing Core.
// Older frontend fixtures omit constraint/execution state and are not catalogue proof.
const projection = JSON.parse(execFileSync(process.env.ORV_QA_PYTHON || 'python', ['-c', `
import json,sys
from datetime import datetime,timezone
from openrouter_video.client import _parse_capability
from openrouter_video.comfy.projection import project_selectable
from openrouter_video.evidence_registry import enrich_capabilities
raw=json.load(open(sys.argv[1],encoding='utf-8'))
print(json.dumps({'models':[project_selectable(enrich_capabilities(_parse_capability(row)),datetime(2026,11,13,tzinfo=timezone.utc)).as_dict() for row in raw['data']]}))
`, fileURLToPath(catalogueURL)], { cwd: fileURLToPath(new URL('../..', import.meta.url)), env: { ...process.env, PYTHONPATH: fileURLToPath(new URL('../../src', import.meta.url)) }, maxBuffer: 32 * 1024 * 1024, encoding:'utf8' }));
const models = catalogue.data.map(raw => {
    const profile = projection.models.find(item => item.model_id === raw.id);
    assert(profile, `saved catalogue missing method profile: ${raw.id}`);
    return profile;
});
const rows = [];
const plain = value => JSON.parse(JSON.stringify(value));
const widget = (n, name) => n.widgets.find(w => w.name === name);
const model = id => models.find(m => m.model_id === id);
const kinds = ['image', 'video', 'audio'];
function harness() {
    let nextId = 100;
    let extension, nextTimer=0;
    const timers=new Map();
    const graph = { links: {}, nodes: {}, getNodeById(id) { return this.nodes[id]; } };
    const c = { app: { graph, registerExtension(value) { extension=value; } }, api: {}, clearTimeout(id) { timers.delete(id); }, setTimeout(fn) { const id=++nextTimer;timers.set(id,fn);return id; } };
    vm.runInNewContext(source, c);
    function unlink(id) {
        const link = graph.links[id];
        if (!link) return;
        const output = graph.nodes[link.origin_id]?.outputs[link.origin_slot];
        if (output) output.links = output.links.filter(value => value !== id);
        const target = graph.nodes[link.target_id], input=target?.inputs[link.target_slot];
        if (target?.inputs[link.target_slot]?.link === id) target.inputs[link.target_slot].link = null;
        delete graph.links[id];
        if(target?.__qaReentrant)target.onConnectionsChange?.(1,link.target_slot,false,link,input);
    }
    graph.removeLink = unlink;
    function node(capability, method) {
        const values = { model: capability.model_id, inference_method: method, prompt: 'prompt', resolution: '720p', aspect_ratio: '16:9', duration: 8, size: '', seed: 42, generate_audio: false, geometry_authority: 'NORMALIZED', 'control after generate': 'fixed', previous_job_id: '', upscale_factor: '', creativity: -1, provider_options: '' };
        const n = { id: nextId++, graph, properties: {}, size: [400,450], __orvEstimate: {value:''}, __orvCapabilityStatus:{value:''}, widgets:[], inputs:[],
            addInput(name,type,options={}) { this.inputs.push({name,type,link:null,...options}); },
            removeInput(index) { const input=this.inputs[index]; if(input.link!=null) unlink(input.link); this.inputs.splice(index,1); this.inputs.forEach((item,slot)=>{if(item.link!=null&&graph.links[item.link])graph.links[item.link].target_slot=slot;}); },
            disconnectInput(index) { if(this.inputs[index]?.link!=null)unlink(this.inputs[index].link); },
            setDirtyCanvas() {}, computeSize(){return [400,200];}, setSize(size){this.size=size;},
            addWidget(type,name,value,callback,options={}) { const w={type,name,value,callback,options,computeSize:()=>[0,20]};this.widgets.push(w);return w; },
        };
        for(const [name,value] of Object.entries(values))n.addWidget('text',name,value);
        graph.nodes[n.id]=n;
        apply(n,capability,method);
        return n;
    }
    function apply(n,capability,method=widget(n,'inference_method').value,cause='explicit') {
        n.__orvModelCapability=capability;
        widget(n,'model').value=capability.model_id;
        widget(n,'inference_method').value=method;
        const selected=c.configureInferenceMethod(n,capability);
        return c.reprojectNodeSemantics(n,capability,selected,{cause});
    }
    function origin(kind) {
        const o={id:nextId++,outputs:[{type:kind.toUpperCase(),links:[]}],connect(slot,target,targetSlot){
            assert(targetSlot>=0,'target slot exists');
            if(target.onConnectInput?.(targetSlot,this.outputs[slot].type,this.outputs[slot],this,slot)===false)return null;
            if(target.inputs[targetSlot].link!=null)unlink(target.inputs[targetSlot].link);
            const id=nextId++;
            graph.links[id]={id,origin_id:this.id,origin_slot:slot,target_id:target.id,target_slot:targetSlot,type:this.outputs[slot].type};
            this.outputs[slot].links.push(id);target.inputs[targetSlot].link=id;return graph.links[id];
        }};graph.nodes[o.id]=o;return o;
    }
    function refs(n){return n.inputs.filter(i=>/^direct_references\.reference_\d+$/.test(i.name));}
    function add(n,kind,o=origin(kind),name=null){
        const input=name?n.inputs.find(i=>i.name===name):refs(n).find(i=>i.link==null&&i.type.split(',').includes(kind.toUpperCase()));
        assert(input,`admissible empty ${kind} socket`);
        o.connect(0,n,n.inputs.indexOf(input));
        apply(n,n.__orvModelCapability,widget(n,'inference_method').value,'connection');
        return o;
    }
    function active(n){return n.inputs.filter(i=>i.link!=null).map(i=>({name:i.name,label:i.label,kind:c.connectedReferenceKind(i),origin:graph.links[i.link].origin_id,slot:graph.links[i.link].origin_slot}));}
    function checkGraph(n){
        const linked=n.inputs.filter(i=>i.link!=null);
        for(const i of linked){const l=graph.links[i.link];assert(l,'no orphan input');assert.equal(l.target_id,n.id);assert.equal(l.target_slot,n.inputs.indexOf(i),'actual target slot');assert(graph.nodes[l.origin_id]?.outputs[l.origin_slot].links.includes(i.link),'source owns link');}
        assert.equal(Object.values(graph.links).filter(l=>l.target_id===n.id).length,linked.length,'no hidden graph dependencies');
        assert.equal(new Set(n.inputs.map(i=>i.name)).size,n.inputs.length,'unique stable wire names');
    }
    function groups(n,topology){
        topology=c.applyTransportInputConstraints(topology,n.inputs.some(i=>i.name==="source_video"&&i.link!=null));
        const linked=refs(n).filter(i=>i.link!=null), current=linked.map(c.connectedReferenceKind);
        const free=refs(n).filter(i=>i.link==null);
        const possible=topology.constraint_state==='UNKNOWN'||topology.constraint_state==='CONFLICT'||topology.execution_domain==='UNVERIFIED'?[]:(topology.reference_kinds||[]).filter(k=>c.referencePartialAllowed(topology,[...current,k]));
        assert.deepEqual(free.map(i=>i.type.split(',').filter(t=>['IMAGE','VIDEO','AUDIO'].includes(t)).join(',')).sort(),possible.map(k=>k.toUpperCase()).sort(),'one typed trailing socket per extensible kind');
        const counters={};
        let rank=-1;
        for(const i of refs(n)){
            const kind=i.link==null?i.type.split(',').find(t=>['IMAGE','VIDEO','AUDIO'].includes(t))?.toLowerCase():c.connectedReferenceKind(i);
            assert(kind,'socket kind is known');assert(kinds.indexOf(kind)>=rank,'canonical visual group order');rank=kinds.indexOf(kind);
            counters[kind]=(counters[kind]||0)+1;assert.equal(i.label,`${kind}_${counters[kind]}`,'per-kind visible numbering');
        }
        assert.equal(new Set(refs(n).map(i=>i.label)).size,refs(n).length,'unique visible labels');checkGraph(n);
    }
    function register(n,nativeConfigure=false){
        function Type(){}
        if(nativeConfigure)Type.prototype.configure=function(info){
            // Pinned native order: properties, input callbacks, then onConfigure.
            // Source-node properties can still be absent at these callbacks.
            this.properties=plain(info.properties);
            for(let slot=0;slot<this.inputs.length;slot++){
                const input=this.inputs[slot];
                if(input.link!=null)this.onConnectionsChange?.(1,slot,true,graph.links[input.link],input);
            }
            this.onConfigure?.(info);
        };
        extension.beforeRegisterNodeDef(Type,{name:'OpenRouterVideoGenerate'});
        Object.setPrototypeOf(n,Type.prototype);
        // Isolate timer-driven local topology from catalogue I/O. Actual remote
        // lifecycle and browser task scheduling are separate qualification gates.
        c.projectSelectedModel=()=>{};
        return n;
    }
    function flush(){let count=0;while(timers.size){assert(count++<100,'bounded timer reconciliation');const pending=[...timers.values()];timers.clear();for(const fn of pending)fn();}}
    return {c,graph,node,apply,origin,add,refs,active,groups,checkGraph,unlink,register,flush};
}
function record(name,fn){test(name,()=>{const row={name,status:'FAIL'};rows.push(row);try{fn(row);row.status='PASS';}catch(error){row.error=error.message;throw error;}});}
after(()=>{
    if(!process.env.ORV_QA_OUTPUT)return;
    mkdirSync(process.env.ORV_QA_OUTPUT,{recursive:true});
    writeFileSync(`${process.env.ORV_QA_OUTPUT}/core-derived-projection.json`,JSON.stringify(projection,null,2));
    writeFileSync(`${process.env.ORV_QA_OUTPUT}/matrix.json`,JSON.stringify({
        scope:'OFFLINE_VM_GRAPH_CONTRACT',native_acceptance:'HOST_NATIVE_UNBOUND',
        suite_sha256:suiteSHA256,
        source_sha256:createHash('sha256').update(sourceBytes).digest('hex'),
        catalogue_sha256:createHash('sha256').update(catalogueBytes).digest('hex'),
        projection_sha256:createHash('sha256').update(JSON.stringify(projection)).digest('hex'),
        model_count:models.length,method_count:models.reduce((sum,m)=>sum+m.supported_inference_methods.length,0),
        limitations:['VM graph bookkeeping replaces native LiteGraph','Deterministic local timer queue; catalogue I/O disabled in callback probes','Property snapshots and copy provenance probes are not native save/load/undo/redo','Canonical dependency order is not actual Comfy prompt or paid-request serialization','No native browser or paid runtime acceptance'],
        rows,
    },null,2));
});

record('S1/S2 grouped empty MMR2V sockets: exact IMAGE VIDEO AUDIO groups',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MMR2V');h.groups(n,m.method_profiles.MMR2V.topology);
});
record('T01 connected labels follow actual kinds with independent numbering and stable canonical sequence',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MMR2V');
    const expected=['video','image','audio','image'].map(kind=>h.add(n,kind).id);
    h.groups(n,m.method_profiles.MMR2V.topology);
    const ordered=h.refs(n).filter(i=>i.link!=null).sort((a,b)=>h.c.referenceInputSuffix(a)-h.c.referenceInputSuffix(b)).map(i=>h.graph.links[i.link].origin_id);
    assert.deepEqual(ordered,expected,'wire order remains insertion order despite visual grouping');
});
record('T03/T05 explicit method round trip parks incompatible media and deterministically reuses frames',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');
    const originals=Array.from({length:3},()=>h.add(n,'image').id);
    h.apply(n,m,'T2V');assert.equal(h.active(n).length,0,'T2V has no active dependency');h.checkGraph(n);
    h.apply(n,m,'I2V');assert.deepEqual(h.active(n).map(i=>[i.name,i.origin]),[['first_frame',originals[0]]]);
    h.apply(n,m,'FLF2V');assert.deepEqual(h.active(n).map(i=>[i.name,i.origin]),[['first_frame',originals[0]],['last_frame',originals[1]]]);
    h.apply(n,m,'MI2V');assert.deepEqual(h.active(n).map(i=>i.origin),originals);h.checkGraph(n);
});
record('T04 Wan IMAGE sources never become active AUDIO labels',()=>{
    const h=harness(),m=model('alibaba/wan-3.0'),n=h.node(m,'MI2V');
    const ids=Array.from({length:3},()=>h.add(n,'image').id);
    h.apply(n,m,'AR2V');assert.equal(h.active(n).length,0,'IMAGE sources parked');h.groups(n,m.method_profiles.AR2V.topology);
    h.apply(n,m,'MI2V');assert.deepEqual(h.active(n).map(i=>i.origin),ids);
});
record('Owner capacity model round trip 20 -> 15 -> 20 -> original 20 with no manual disconnect',()=>{
    const h=harness(),wan=model('alibaba/wan-3.0'),seed=model('bytedance/seedance-2.0'),large=model('bytedance/seedance-2.5'),n=h.node(wan,'MMR2V');
    const ids=[];for(const [kind,count] of [['image',10],['video',5],['audio',5]])for(let i=0;i<count;i++)ids.push(h.add(n,kind).id);
    h.groups(n,wan.method_profiles.MMR2V.topology);assert.equal(h.refs(n).filter(i=>i.link==null).length,0);
    h.apply(n,seed,'MMR2V');assert.equal(h.active(n).length,15);assert.deepEqual(kinds.map(k=>h.active(n).filter(i=>i.kind===k).length),[9,3,3]);h.groups(n,seed.method_profiles.MMR2V.topology);
    for(const cap of [large,wan]){h.apply(n,cap,'MMR2V');assert.deepEqual(h.active(n).map(i=>i.origin).sort((a,b)=>a-b),[...ids].sort((a,b)=>a-b));h.groups(n,cap.method_profiles.MMR2V.topology);}
});
record('Explicit disconnection and deleted parked sources never resurrect on round trip',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');
    const removed=h.add(n,'image'),deleted=h.add(n,'image'),kept=h.add(n,'image');
    h.unlink(n.inputs.find(i=>i.link!=null&&h.graph.links[i.link].origin_id===removed.id).link);h.apply(n,m,'MI2V','connection');
    h.apply(n,m,'T2V');delete h.graph.nodes[deleted.id];h.apply(n,m,'MI2V');
    assert.deepEqual(h.active(n).map(i=>i.origin),[kept.id]);h.checkGraph(n);
});
record('Automatic capability shrink preserves intended links and remains fail closed',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');
    const ids=Array.from({length:3},()=>h.add(n,'image').id),shrunk=plain(m);
    shrunk.method_profiles.MI2V.topology.max=1;shrunk.method_profiles.MI2V.topology.per_kind_max.image=1;
    h.apply(n,shrunk,'MI2V','catalogue');assert.deepEqual(h.active(n).map(i=>i.origin),ids);assert.equal(n.__orvReferenceInvalid,true);h.checkGraph(n);
});
for(const m of models)for(const method of m.supported_inference_methods){
    record(`catalogue fresh grouped topology ${m.model_id} / ${method}`,()=>{const h=harness(),n=h.node(m,method),top=m.method_profiles[method].topology;h.groups(n,top);for(const role of top.fixed||[])assert(n.inputs.some(i=>i.name===role));});
}

function fill(h,n,m,method,state){
    const top=m.method_profiles[method].topology;
    if(state==='empty')return;
    for(const role of top.fixed||[]){const kind=role==='source_video'?'video':'image';if(n.inputs.some(i=>i.name===role&&i.link==null))h.add(n,kind,h.origin(kind),role);}
    const limit=state==='partial'?1:64;
    for(let count=0;count<limit;count++){
        const free=h.refs(n).filter(i=>i.link==null);
        const kind=kinds.map((_,index)=>kinds[(index+count)%kinds.length]).find(k=>free.some(i=>i.type.split(',').includes(k.toUpperCase())));
        if(!kind)break;
        h.add(n,kind);
    }
}
function origins(h,n){return h.active(n).map(i=>`${i.origin}:${i.slot}`).sort();}
function canonicalDependencies(h,n){
    const fixed=n.inputs.filter(i=>i.link!=null&&!h.refs(n).includes(i));
    const references=h.refs(n).filter(i=>i.link!=null).sort((a,b)=>h.c.referenceInputSuffix(a)-h.c.referenceInputSuffix(b));
    return [...fixed,...references].map(i=>{const l=h.graph.links[i.link];return {wire:i.name,origin:l.origin_id,output:l.origin_slot};});
}
for(const m of models)for(const from of m.supported_inference_methods)for(const to of m.supported_inference_methods){
    if(from===to)continue;
    for(const state of ['empty','partial','boundary'])record(`catalogue transition ${m.model_id} ${from} -> ${to} -> ${from} [${state}]`,row=>{
        const h=harness(),n=h.node(m,from);fill(h,n,m,from,state);
        const initial=origins(h,n),initialOrder=canonicalDependencies(h,n);row.before=h.active(n);row.canonical_before=initialOrder;
        h.apply(n,m,to);h.groups(n,m.method_profiles[to].topology);row.target=h.active(n);
        for(const input of h.active(n)){
            if(input.name==='first_frame'||input.name==='last_frame')assert.equal(input.kind,'image','frame media identity');
            else if(input.name==='source_video')assert.equal(input.kind,'video','source-video media identity');
            else assert(m.method_profiles[to].topology.reference_kinds.includes(input.kind),'active reference kind admitted');
        }
        const once=origins(h,n);
        for(let repeat=0;repeat<3;repeat++)h.apply(n,m,to);
        assert.deepEqual(origins(h,n),once,'idempotent repeated projection');h.checkGraph(n);
        h.apply(n,m,from);assert.deepEqual(origins(h,n),initial,'all original occurrences restored');
        assert.deepEqual(canonicalDependencies(h,n),initialOrder,'unsorted canonical dependency sequence and wire identities restored');
        h.groups(n,m.method_profiles[from].topology);row.restored=h.active(n);row.canonical_restored=canonicalDependencies(h,n);
    });
}
for(const m of models)for(const method of m.supported_inference_methods){
    if(!(m.method_profiles[method].topology.reference_kinds||[]).length)continue;
    record(`catalogue capacity boundary/disconnect/reconnect ${m.model_id} / ${method}`,row=>{
        const h=harness(),n=h.node(m,method);fill(h,n,m,method,'boundary');h.groups(n,m.method_profiles[method].topology);row.boundary=h.active(n);
        const input=h.refs(n).find(i=>i.link!=null);
        if(!input)return;
        const kind=h.c.connectedReferenceKind(input),o=h.graph.nodes[h.graph.links[input.link].origin_id];
        h.unlink(input.link);h.apply(n,m,method,'connection');h.groups(n,m.method_profiles[method].topology);
        assert(h.refs(n).some(i=>i.link==null&&i.type.split(',').includes(kind.toUpperCase())),'disconnection reopens its admissible kind');
        h.add(n,kind,o);h.groups(n,m.method_profiles[method].topology);
    });
}
record('Offline same-graph property snapshot: duplicate occurrences restore without duplication (not native save/load)',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V'),o=h.origin('image');
    h.add(n,'image',o);h.add(n,'image',o);h.apply(n,m,'T2V');assert.equal(h.active(n).length,0);
    const saved=plain({properties:n.properties,inputs:n.inputs,widgets:n.widgets.map(w=>[w.name,w.value])});
    const restored=h.node(m,'T2V');delete h.graph.nodes[restored.id];restored.id=n.id;h.graph.nodes[n.id]=restored;
    restored.properties=saved.properties;restored.inputs=saved.inputs;
    for(const [name,value]of saved.widgets)if(widget(restored,name))widget(restored,name).value=value;
    h.apply(restored,m,'MI2V');assert.deepEqual(h.active(restored).map(i=>i.origin),[o.id,o.id]);
    for(let i=0;i<4;i++)h.apply(restored,m,'MI2V');assert.equal(h.active(restored).length,2);h.checkGraph(restored);
});
record('Native AUDIO group admits AUDIO and never exposes AUDIO_ENCODER',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'AR2V');
    assert(h.refs(n).some(i=>i.type.split(',').includes('AUDIO')));
    assert(h.refs(n).every(i=>!i.type.split(',').includes('AUDIO_ENCODER')));
    h.add(n,'audio');assert.equal(h.active(n)[0].kind,'audio');h.groups(n,m.method_profiles.AR2V.topology);
});


for(const [id,caps]of [['alibaba/wan-3.0',[10,5,5]],['bytedance/seedance-2.0',[9,3,3]],['bytedance/seedance-2.5',[30,10,10]]]){
    record(`Owner independent numeric grouped capacities ${id}: ${caps.join('/')} total ${caps.reduce((a,b)=>a+b,0)}`,row=>{
        const h=harness(),m=model(id),n=h.node(m,'MMR2V');
        assert.deepEqual(h.refs(n).filter(i=>i.link==null).map(i=>i.label),['image_1','video_1','audio_1']);
        const added={image:0,video:0,audio:0};
        for(let index=0;index<Math.max(...caps);index++)for(let kindIndex=0;kindIndex<kinds.length;kindIndex++){
            const kind=kinds[kindIndex];if(index>=caps[kindIndex])continue;
            h.add(n,kind);added[kind]++;
            for(let k=0;k<kinds.length;k++){
                const empties=h.refs(n).filter(i=>i.link==null&&i.type.split(',').includes(kinds[k].toUpperCase()));
                assert.equal(empties.length,added[kinds[k]]<caps[k]?1:0,`independent ${kinds[k]} remaining after ${JSON.stringify(added)}`);
            }
            h.checkGraph(n);
        }
        assert.equal(h.active(n).length,caps.reduce((a,b)=>a+b,0));assert.equal(h.refs(n).filter(i=>i.link==null).length,0);row.active=h.active(n);row.canonical=canonicalDependencies(h,n);
    });
}
record('Shared transport total boundary is independent of per-kind spare capacity: Gemini Omni edit source plus six guides',()=>{
    const h=harness(),m=model('google/gemini-omni-1.2-flash'),n=h.node(m,'V2V_EDIT');
    h.add(n,'video',h.origin('video'),'source_video');
    for(let i=0;i<6;i++)h.add(n,'image');
    assert.equal(h.active(n).length,7);assert.equal(h.refs(n).filter(i=>i.link==null).length,0);h.checkGraph(n);
});

record('Explicit Last Frame role survives First Frame deletion/replacement through MI2V',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'FLF2V');
    const first=h.add(n,'image',h.origin('image'),'first_frame'),last=h.add(n,'image',h.origin('image'),'last_frame');
    h.apply(n,m,'MI2V');
    h.unlink(h.refs(n).find(i=>i.link!=null&&h.graph.links[i.link].origin_id===first.id).link);h.apply(n,m,'MI2V','connection');
    const replacement=h.add(n,'image');h.apply(n,m,'FLF2V');
    assert.equal(h.active(n).find(i=>i.name==='last_frame')?.origin,last.id,'explicit Last Frame reserved before fallback');
    assert.equal(h.active(n).find(i=>i.name==='first_frame')?.origin,replacement.id);h.checkGraph(n);
});
record('One explicitly removed duplicate occurrence is never restored by another occurrence of same source',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V'),o=h.origin('image');
    h.add(n,'image',o);h.add(n,'image',o);h.unlink(h.refs(n).find(i=>i.link!=null).link);h.apply(n,m,'MI2V','connection');
    h.apply(n,m,'T2V');h.apply(n,m,'MI2V');assert.equal(h.active(n).length,1);h.checkGraph(n);
});
record('Reused deleted parked source numeric ID cannot substitute a different source object',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V'),o=h.add(n,'image');
    h.apply(n,m,'T2V');delete h.graph.nodes[o.id];const replacement=h.origin('image');delete h.graph.nodes[replacement.id];replacement.id=o.id;h.graph.nodes[o.id]=replacement;
    h.apply(n,m,'MI2V');assert.equal(h.active(n).length,0);h.checkGraph(n);
});

record('Registered connection callbacks preserve rapid VIDEO then IMAGE wire chronology before debounce',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MMR2V'));
    const video=h.origin('video'),image=h.origin('image');
    for(const [kind,o]of [['video',video],['image',image]]){
        const slot=n.inputs.indexOf(h.refs(n).find(i=>i.link==null&&i.type.split(',').includes(kind.toUpperCase())));
        assert(slot>=0,'independent typed group exists');
        const link=o.connect(0,n,slot);n.onConnectionsChange(1,slot,true,link,n.inputs[slot]);
    }
    h.flush();
    assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),[video.id,image.id],'chronological canonical payload dependencies');
    h.groups(n,m.method_profiles.MMR2V.topology);
});
record('Registered disconnect callback updates intent before explicit method round trip',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const removed=h.add(n,'image'),kept=h.add(n,'image');
    const input=h.refs(n).find(i=>i.link!=null&&h.graph.links[i.link].origin_id===removed.id),slot=n.inputs.indexOf(input),link=h.graph.links[input.link];
    h.unlink(input.link);n.onConnectionsChange(1,slot,false,link,input);h.flush();
    h.apply(n,m,'T2V');h.apply(n,m,'MI2V');assert.deepEqual(h.active(n).map(i=>i.origin),[kept.id]);h.checkGraph(n);
});

record('Exact capture/Core executable model-method identities match retained b628912 wheel audit',row=>{
    // Exact identities from retained b628912 final-wheel-live-audit.json, not new profiles.
    const baselineExecutable={"google/gemini-omni-1.2-flash":["FLF2V","I2V","IR2V","MI2V","T2V","V2V_EDIT","V2V_EXTEND","VR2V"],"google/gemini-omni-1.1-flash":["FLF2V","I2V","IR2V","T2V","V2V_EDIT","V2V_EXTEND","VR2V"],"tbc/mischief-1":["I2V"],"x-ai/grok-imagine-video-1.5-lite":["I2V","T2V"],"heygen/heygen-video-1":["I2V","IR2V","MI2V","MMR2V","T2V","VR2V"],"black-forest-labs/flux-video-edit":["V2V_EDIT"],"minimax/hailuo-3-max":["FLF2V","I2V","T2V"],"alibaba/wan-3.0-prime":["FLF2V","I2V","T2V"],"alibaba/wan-3.0":["AR2V","FLF2V","I2V","IR2V","MI2V","MMR2V","T2V","VR2V"],"heygen/avatar-iv":["AVATAR_AUDIO","IR2V"],"black-forest-labs/flux-video-upscale":["V2V_UPSCALE"],"bytedance/seedance-2.0-mini":["FLF2V","I2V","IR2V","MI2V","MMR2V","T2V","VR2V"],"bytedance/seedance-2.5":["AR2V","FLF2V","I2V","IR2V","MI2V","MMR2V","T2V","V2V_EDIT","V2V_EXTEND","VR2V"],"black-forest-labs/flux-3-video":["FLF2V","I2V","T2V"],"minimax/hailuo-3":["FLF2V","I2V","T2V"],"runway/aleph-2":["V2V_EDIT"],"runway/gen-4.5":["I2V","T2V"],"x-ai/grok-imagine-video-1.5":["I2V","T2V"],"alibaba/happyhorse-1.1":["I2V","IR2V","MI2V","T2V"],"alibaba/happyhorse-1.0":["I2V","IR2V","MI2V","T2V"],"x-ai/grok-imagine-video":["I2V","IR2V","MI2V","T2V"],"kwaivgi/kling-v3.0-pro":["FLF2V","I2V","T2V"],"kwaivgi/kling-v3.0-std":["FLF2V","I2V","T2V"],"google/veo-3.1-fast":["FLF2V","I2V","T2V"],"google/veo-3.1-lite":["FLF2V","I2V","T2V"],"kwaivgi/kling-video-o1":["FLF2V","I2V","T2V"],"minimax/hailuo-2.3":["I2V","T2V"],"bytedance/seedance-2.0":["FLF2V","I2V","IR2V","MI2V","MMR2V","T2V","VR2V"],"alibaba/wan-2.7":["FLF2V","I2V","IR2V","MI2V","T2V"],"bytedance/seedance-2.0-fast":["FLF2V","I2V","IR2V","MI2V","MMR2V","T2V","VR2V"],"alibaba/wan-2.6":["I2V","T2V","VR2V"],"google/veo-3.1":["FLF2V","I2V","T2V"]};
    row.models=models.map(m=>({model_id:m.model_id,methods:[...m.supported_inference_methods].sort()}));
    for(const m of models)assert.deepEqual([...m.supported_inference_methods].sort(),[...baselineExecutable[m.model_id]].sort(),m.model_id);
    assert.equal(models.length,32);assert.equal(models.reduce((sum,m)=>sum+m.supported_inference_methods.length,0),124);
});
record('Registered onConnectInput rejects AUDIO_ENCODER/IMAGE on AUDIO group without mutating graph',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'AR2V'));
    const input=h.refs(n).find(i=>i.link==null&&i.type.split(',').includes('AUDIO')),slot=n.inputs.indexOf(input);
    assert(slot>=0);assert.equal(typeof n.onConnectInput,'function','actual registered type hook');
    const before=plain(h.graph.links);
    for(const kind of ['audio_encoder','image','video','model','clip','mask','string'])assert.equal(h.origin(kind).connect(0,n,slot),null,kind);
    assert.deepEqual(h.graph.links,before);assert.equal(input.link,null);
    const audio=h.origin('audio'),link=audio.connect(0,n,slot);assert(link);n.onConnectionsChange(1,slot,true,link,input);h.flush();
    assert.equal(h.active(n)[0].kind,'audio');h.checkGraph(n);
});
record('Reentrant registered disconnect callbacks during parking preserve occurrence intent and restore once',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MMR2V'));
    n.__qaReentrant=true;
    const ids=['image','video','audio','image'].map(kind=>h.add(n,kind).id);
    h.apply(n,m,'T2V');h.flush();assert.equal(h.active(n).length,0);h.checkGraph(n);
    h.apply(n,m,'MMR2V');h.flush();assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),ids);h.checkGraph(n);
});

for(let index=0;index<models.length;index++)for(const method of models[index].supported_inference_methods){
    const m=models[index],shape=JSON.stringify(m.method_profiles[method].topology);
    const target=models.slice(index+1).concat(models.slice(0,index+1)).flatMap(candidate=>candidate.supported_inference_methods.map(targetMethod=>({candidate,targetMethod}))).find(({candidate,targetMethod})=>candidate.model_id!==m.model_id&&JSON.stringify(candidate.method_profiles[targetMethod].topology)!==shape);
    if(!target)continue;
    record(`catalogue cross-model topology roundtrip ${m.model_id}/${method} -> ${target.candidate.model_id}/${target.targetMethod}`,row=>{
        const h=harness(),n=h.node(m,method);fill(h,n,m,method,'boundary');const before=canonicalDependencies(h,n);row.before=before;
        h.apply(n,target.candidate,target.targetMethod);h.groups(n,target.candidate.method_profiles[target.targetMethod].topology);row.target=h.active(n);
        h.apply(n,m,method);assert.deepEqual(canonicalDependencies(h,n),before,'cross-family source identity/wire sequence restoration');h.groups(n,m.method_profiles[method].topology);row.restored=canonicalDependencies(h,n);
    });
}

record('Offline copy provenance: fresh pasted active links remain valid across repeated capture',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');h.add(n,'image');h.add(n,'image');
    const copy=h.node(m,'MI2V');copy.properties=plain(n.properties);copy.inputs=plain(n.inputs).filter(i=>i.link!=null);
    for(const input of copy.inputs)input.link=null;
    const copiedSources=[];for(let slot=0;slot<copy.inputs.length;slot++){const o=h.origin('image');o.connect(0,copy,slot);copiedSources.push(o.id);}
    h.apply(copy,m,'MI2V','configure');h.apply(copy,m,'MI2V','catalogue');
    assert.equal(copy.__orvReferenceInvalid,false,'fresh active pasted sources retain independent valid identities');
    assert.deepEqual(h.active(copy).map(i=>i.origin),copiedSources);h.checkGraph(copy);
    h.apply(copy,m,'T2V');h.apply(copy,m,'MI2V');assert.deepEqual(h.active(copy).map(i=>i.origin),copiedSources);h.checkGraph(copy);
});
record('Offline copied parked intent cannot bind original same-graph sources to a different Generate node',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');h.add(n,'image');h.apply(n,m,'T2V');
    const copy=h.node(m,'T2V');copy.properties=plain(n.properties);h.apply(copy,m,'MI2V','configure');
    assert.equal(h.active(copy).length,0,'parked source provenance does not migrate by numeric graph ID');h.checkGraph(copy);
});

record('Disconnected first reference socket reused by new source preserves B then C canonical order and I2V fallback',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');
    const a=h.add(n,'image'),b=h.add(n,'image');
    const input=h.refs(n).find(i=>i.link!=null&&h.graph.links[i.link].origin_id===a.id);
    h.unlink(input.link);h.apply(n,m,'MI2V','connection');const c=h.add(n,'image');
    assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),[b.id,c.id],'new occurrence remains after retained source');
    h.apply(n,m,'I2V');assert.equal(h.active(n).find(i=>i.name==='first_frame')?.origin,b.id,'fallback matches canonical first occurrence');
    h.apply(n,m,'MI2V');assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),[b.id,c.id]);h.checkGraph(n);
});

record('Registered onConfigure defers link-intent capture until all saved links are restored',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const origins=[h.add(n,'image'),h.add(n,'image')],savedProperties=plain(n.properties);
    const savedInputs=plain(n.inputs).filter(i=>i.link!=null);
    for(const input of n.inputs)if(input.link!=null)h.unlink(input.link);
    n.properties=savedProperties;n.inputs=savedInputs;for(const input of n.inputs)input.link=null;
    n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    const before=plain(n.properties.orv_capability_intent.media);
    const first=origins[0].connect(0,n,0);n.onConnectionsChange(1,0,true,first,n.inputs[0]);
    assert.deepEqual(plain(n.properties.orv_capability_intent.media),before,'partially restored graph must not prune saved occurrences');
    const second=origins[1].connect(0,n,1);n.onConnectionsChange(1,1,true,second,n.inputs[1]);
    h.flush();h.apply(n,m,'MI2V','configure');
    assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),origins.map(o=>o.id));h.checkGraph(n);
});

record('Import-alias linked reference normalizes in place before capture and preserves output and named intent',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const origins=[h.add(n,'image'),h.add(n,'image')],inputs=h.refs(n).filter(i=>i.link!=null);
    h.c.captureMediaIntent(n);
    const links=inputs.map(i=>i.link),slots=inputs.map(i=>n.inputs.indexOf(i)),types=inputs.map(i=>i.type);
    const savedIntent=plain(n.properties.orv_capability_intent.media);
    for(const input of inputs)input.name=input.name.replace('direct_references.','');
    const outputs=n.outputs=[{name:'job_id',type:'STRING',links:[999]}];
    const named=Object.fromEntries(n.widgets.map(w=>[w.name,w.value]));named.generate_audio=false;named.seed=123;
    n.onConfigure({widgets_values_named:named});
    for(let i=0;i<inputs.length;i++){
        assert.equal(n.inputs[slots[i]],inputs[i],'same hydrated input and slot');
        assert.equal(inputs[i].name,savedIntent[i].reference_name);
        assert.equal(inputs[i].link,links[i]);assert.equal(inputs[i].type,types[i]);
    }
    assert.deepEqual(plain(n.properties.orv_capability_intent.media),savedIntent,'normalization does not rewrite stored intent');
    h.flush();h.apply(n,m,'MI2V','configure');
    assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),origins.map(o=>o.id));
    assert.deepEqual(plain(n.properties.orv_capability_intent.media),savedIntent,'capture retains occurrence identity and order');
    assert.equal(n.outputs,outputs);assert.equal(widget(n,'generate_audio').value,false);assert.equal(widget(n,'seed').value,123);
    h.groups(n,m.method_profiles.MI2V.topology);
});

record('Import-alias linked raw reference_0 without saved intent enters canonical capture and labels',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const sources=[h.add(n,'image'),h.add(n,'image')],inputs=h.refs(n).filter(i=>i.link!=null);
    inputs.forEach((input,index)=>{input.name=`reference_${index}`;delete input.orv_occurrence_id;});
    n.properties.orv_capability_intent.media=[];
    n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    assert.deepEqual(inputs.map(i=>i.name),['direct_references.reference_0','direct_references.reference_1']);
    h.flush();h.apply(n,m,'MI2V','configure');
    assert.deepEqual(canonicalDependencies(h,n).map(i=>[i.wire,i.origin]),sources.map((o,index)=>[`direct_references.reference_${index}`,o.id]));
    assert.deepEqual(plain(n.properties.orv_capability_intent.media).map(e=>[e.active_name,e.origin_id]),sources.map((o,index)=>[`direct_references.reference_${index}`,o.id]));
    assert.deepEqual(inputs.map(i=>i.label),['image_1','image_2']);h.groups(n,m.method_profiles.MI2V.topology);
});

for(const method of ['I2V','FLF2V'])record(`Import-alias unlinked reference is removed by existing ${method} reconciliation with frame links intact`,()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,method));
    const frames=(m.method_profiles[method].topology.fixed||[]).map(name=>h.add(n,'image',h.origin('image'),name));
    const frameInputs=n.inputs.filter(i=>i.link!=null),frameLinks=frameInputs.map(i=>i.link);
    n.addInput('reference_0','IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE');
    const alias=n.inputs.at(-1),slot=n.inputs.indexOf(alias),type=alias.type;
    n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    assert.equal(n.inputs[slot],alias);assert.equal(alias.name,'direct_references.reference_0');assert.equal(alias.type,type);assert.equal(alias.link,null);
    h.flush();h.apply(n,m,method,'configure');
    assert(!n.inputs.includes(alias),'existing non-reference topology removes empty socket');
    assert.deepEqual(h.active(n).map(i=>i.origin),frames.map(o=>o.id));
    frameInputs.forEach((input,index)=>{assert(n.inputs.includes(input));assert.equal(input.link,frameLinks[index]);});h.checkGraph(n);
});

record('Import-alias linked occurrences round trip through I2V and FLF2V without lost material',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const sources=Array.from({length:3},()=>h.add(n,'image'));
    for(const input of h.refs(n).filter(i=>i.link!=null))input.name=input.name.replace('direct_references.','');
    n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});h.flush();h.apply(n,m,'MI2V','configure');
    const saved=plain(n.properties.orv_capability_intent.media),canonical=canonicalDependencies(h,n);
    h.apply(n,m,'I2V');assert.deepEqual(h.active(n).map(i=>[i.name,i.origin]),[['first_frame',sources[0].id]]);h.checkGraph(n);
    h.apply(n,m,'FLF2V');assert.deepEqual(h.active(n).map(i=>[i.name,i.origin]),[['first_frame',sources[0].id],['last_frame',sources[1].id]]);h.checkGraph(n);
    h.apply(n,m,'MI2V');assert.deepEqual(canonicalDependencies(h,n),canonical);
    assert.deepEqual(plain(n.properties.orv_capability_intent.media).map(e=>[e.id,e.origin_id,e.reference_name]),saved.map(e=>[e.id,e.origin_id,e.reference_name]));h.checkGraph(n);
});

record('Import-alias canonical and unrelated names remain unchanged across repeated configure',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    h.add(n,'image');
    for(const name of ['reference_x','other.reference_0','reference_0_suffix'])n.addInput(name,'STRING');
    const inputs=[...n.inputs],before=plain(inputs);
    for(let repeat=0;repeat<2;repeat++){
        n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
        inputs.forEach((input,index)=>assert.equal(n.inputs[index],input));assert.deepEqual(plain(n.inputs),before);
    }
    h.flush();h.apply(n,m,'MI2V','configure');h.checkGraph(n);
});

for(const linked of [false,true])record(`Import-alias canonical collision allocates a distinct wire without material or link drops [linked=${linked}]`,()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const source=h.add(n,'image'),canonical=h.refs(n).find(i=>i.link!=null);
    n.addInput(canonical.name.replace('direct_references.',''),canonical.type);
    const alias=n.inputs.at(-1);if(linked)h.origin('image').connect(0,n,n.inputs.indexOf(alias));
    n.addInput('reference_99','IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE');
    const inputs=[...n.inputs],beforeLinks=plain(h.graph.links),canonicalName=canonical.name;
    n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    assert.equal(n.__orvReferenceAliasConflict,false);
    assert.equal(canonical.name,canonicalName);assert.notEqual(alias.name,canonicalName);
    assert.match(alias.name,/^direct_references\.reference_\d+$/);
    assert.equal(n.inputs.at(-1).name,'direct_references.reference_99');
    inputs.forEach((input,index)=>assert.equal(n.inputs[index],input));
    assert.deepEqual(plain(h.graph.links),beforeLinks);
    h.flush();h.apply(n,m,'MI2V','configure');
    const expected=Object.values(beforeLinks).map(l=>l.origin_id);
    assert.deepEqual(canonicalDependencies(h,n).map(e=>e.origin),expected);
    for(const method of ['I2V','FLF2V','MI2V'])h.apply(n,m,method);
    assert.deepEqual(canonicalDependencies(h,n).map(e=>e.origin),expected);
    assert(canonicalDependencies(h,n).some(e=>e.origin===source.id));h.checkGraph(n);
});

record('Import-alias duplicate raw names remain blocked atomically',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    n.addInput('reference_0','IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE');
    n.addInput('reference_0','IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE');
    const before=plain(n.inputs);
    n.onConfigure({widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    assert.equal(n.__orvReferenceAliasConflict,true);assert.deepEqual(plain(n.inputs),before);
});

for(const globalGraphConfigure of [true,false])record(`Native-order reconstruction target-first before source tokens [app.configuringGraph=${globalGraphConfigure}] retains parked5 and restores Wan20`,()=>{
    const h=harness(),wan=model('alibaba/wan-3.0'),seed=model('bytedance/seedance-2.0'),n=h.register(h.node(wan,'MMR2V'),true);
    const sources=[];
    for(const [kind,count]of [['image',10],['video',5],['audio',5]])for(let i=0;i<count;i++)sources.push(h.add(n,kind));
    h.apply(n,seed,'MMR2V');assert.equal(h.active(n).length,15);
    const properties=plain(n.properties),sourceProperties=sources.map(o=>plain(o.properties));
    assert.equal(properties.orv_capability_intent.media.filter(entry=>entry.active_name===null).length,5);
    for(const o of sources)delete o.properties;
    h.c.app.configuringGraph=globalGraphConfigure;
    n.configure({properties,widgets_values_named:Object.fromEntries(n.widgets.map(w=>[w.name,w.value]))});
    for(let i=0;i<sources.length;i++)sources[i].properties=sourceProperties[i];
    h.c.app.configuringGraph=false;h.flush();h.apply(n,seed,'MMR2V','configure');
    h.apply(n,wan,'MMR2V');
    assert.deepEqual(canonicalDependencies(h,n).map(i=>i.origin),sources.map(o=>o.id),'all original20 occurrences survive target-before-source reconstruction');
    h.checkGraph(n);
});

// Predictable Progress: model the independently installed host writer, not just
// the product's VM graph. This is a behavioral adversary, not copied host code.
function withHostWriter(h,n) {
    const groups={direct_references:{prefix:'reference_',min:0,max:100,inputSpecs:[{}]},unrelated:{marker:1}};
    n.comfyDynamic={autogrow:groups};
    const product=n.onConnectionsChange;
    let writes=0;
    n.onConnectionsChange=function(type,slot,connected,link,input){
        product.call(this,type,slot,connected,link,input);
        if(!groups.direct_references||!connected||!link)return;
        const current=this.inputs[slot];
        if(!current?.name.startsWith('direct_references.'))return;
        const last=h.refs(this).at(-1);
        if(current!==last)return;
        const name=`direct_references.reference_${h.c.referenceInputSuffix(current)+1}`;
        if(h.refs(this).some(i=>i.name===name))return;
        writes++;this.addInput(name,'IMAGE,VIDEO,AUDIO,OPENROUTER_VIDEO_INPUT_REFERENCE',{label:name.split('.').at(-1)});
    };
    return {groups,writes:()=>writes};
}
record('PP01 native writer cannot append raw reference on a live connection or at Gemini capacity',()=>{
    const h=harness(),m=model('google/gemini-omni-1.2-flash'),n=h.register(h.node(m,'MI2V'));
    const host=withHostWriter(h,n);
    h.apply(n,m,'MI2V','connection');
    for(let i=1;i<=6;i++){
        const input=h.refs(n).find(i=>i.link==null),slot=n.inputs.indexOf(input),o=h.origin('image');
        assert(input);const link=o.connect(0,n,slot);assert(link);n.onConnectionsChange(1,slot,true,link,input);
        assert.equal(host.writes(),0,'host must never add a second free reference');
        h.flush();h.groups(n,m.method_profiles.MI2V.topology);assert.equal(h.active(n).length,i);
    }
    assert.equal(h.refs(n).length,6);assert.equal(host.groups.unrelated.marker,1);
});
record('PP02 price metadata change cannot cancel pending socket reconciliation',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.register(h.node(m,'MI2V'));
    const input=h.refs(n)[0],slot=n.inputs.indexOf(input),o=h.origin('image');
    const link=o.connect(0,n,slot);n.onConnectionsChange(1,slot,true,link,input);
    n.__orvCostMetadataSignature='different';h.c.refreshEstimate=()=>{};
    h.c.checkNativeCostMetadata(n);h.flush();
    h.groups(n,m.method_profiles.MI2V.topology);assert.equal(h.refs(n).length,2);
});
record('PP03 live legacy alias captured, typed and included in count without link removal',()=>{
    const h=harness(),m=model('google/gemini-omni-1.2-flash'),n=h.register(h.node(m,'MI2V'));
    n.addInput('reference_32','IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE');
    const input=n.inputs.at(-1),slot=n.inputs.indexOf(input),o=h.origin('image');
    const link=o.connect(0,n,slot);n.onConnectionsChange(1,slot,true,link,input);h.flush();
    assert.equal(input.name,'direct_references.reference_32');assert.equal(input.label,'image_1');
    assert.equal(input.link,link.id);assert.equal(h.active(n).length,1);h.groups(n,m.method_profiles.MI2V.topology);
});
record('PP04 mixed pricing context follows wire order rather than visible group order',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MMR2V');
    for(const kind of ['video','image','audio','image'])h.add(n,kind);
    const expected=['video','image','audio','image'];
    assert.deepEqual(plain(h.c.selectedReferenceKinds(n)),expected);
    assert.deepEqual(plain(h.c.costMediaOccurrences(n,m.method_profiles.MMR2V.topology).map(i=>i.kind)),expected);
    h.groups(n,m.method_profiles.MMR2V.topology);
});
record('PP05 host writer excluded during 50-slot fill and model round trip; all occurrences retained',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),mini=model('bytedance/seedance-2.0-mini'),n=h.register(h.node(m,'MMR2V'));
    const host=withHostWriter(h,n);h.apply(n,m,'MMR2V','connection');
    for(const [kind,count] of [['image',30],['video',10],['audio',10]])for(let i=0;i<count;i++){
        const input=h.refs(n).find(i=>i.link==null&&i.type.split(',').includes(kind.toUpperCase()));assert(input);
        const slot=n.inputs.indexOf(input),o=h.origin(kind),link=o.connect(0,n,slot);assert(link);
        n.onConnectionsChange(1,slot,true,link,input);h.flush();h.groups(n,m.method_profiles.MMR2V.topology);
    }
    const before=canonicalDependencies(h,n);assert.equal(before.length,50);assert.equal(host.writes(),0);
    h.apply(n,mini,'MMR2V');assert.equal(h.active(n).length,15);h.groups(n,mini.method_profiles.MMR2V.topology);
    h.apply(n,m,'MMR2V');assert.deepEqual(canonicalDependencies(h,n),before);h.groups(n,m.method_profiles.MMR2V.topology);
});
record('PP06 full Seedance 2.5 input capacity must fit native reference_0..99 namespace',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MMR2V');
    for(const [kind,count] of [['image',30],['video',10],['audio',10]])for(let i=0;i<count;i++)h.add(n,kind);
    assert.equal(h.active(n).length,50);assert(h.refs(n).every(i=>h.c.referenceInputSuffix(i)<100));
    const before=canonicalDependencies(h,n),identities=plain(n.properties.orv_capability_intent.media).map(e=>[e.id,e.order,e.origin_id]);
    h.apply(n,m,'I2V');h.apply(n,m,'MMR2V');assert.deepEqual(canonicalDependencies(h,n),before);
    assert.deepEqual(plain(n.properties.orv_capability_intent.media).map(e=>[e.id,e.order,e.origin_id]),identities);h.groups(n,m.method_profiles.MMR2V.topology);
});
record('PP07 repeated replacement and mixed-group switches cannot exhaust wire names or rewrite retained order',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),mini=model('bytedance/seedance-2.0-mini'),n=h.node(m,'MI2V');
    const retained=h.add(n,'image').id;
    for(let i=0;i<115;i++){
        const o=h.add(n,'image'),input=h.refs(n).find(x=>x.link!=null&&h.graph.links[x.link].origin_id===o.id);
        assert(h.refs(n).every(x=>h.c.referenceInputSuffix(x)<100),'bounded while two active');
        h.unlink(input.link);h.apply(n,m,'MI2V','connection');
        if(i%10===0){h.apply(n,mini,'MI2V');h.apply(n,m,'MI2V');}
        assert.deepEqual(h.active(n).map(x=>x.origin),[retained]);
    }
    assert.equal(h.refs(n).length,2);h.groups(n,m.method_profiles.MI2V.topology);
});
record('PP08 compact wire names preserve more than 100 retained occurrences without submitting parked media',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');
    // Construct saved owner-intent entries with distinct sources. Only a small
    // compatible projection is active at any given time.
    const all=Array.from({length:110},()=>h.origin('image'));
    n.properties.orv_capability_intent.media=all.map((o,index)=>({id:`media_${index}`,order:index,owner_id:n.id,
        origin_id:o.id,origin_slot:0,kind:'image',reference_name:`direct_references.reference_${index}`,roles:[],collection:false,active_name:null}));
    h.apply(n,m,'MI2V');assert.equal(h.active(n).length,30);
    assert.equal(n.properties.orv_capability_intent.media.length,110);
    assert(h.refs(n).every(i=>h.c.referenceInputSuffix(i)<100));
    const before=canonicalDependencies(h,n);h.apply(n,m,'T2V');assert.equal(h.active(n).length,0);
    assert.equal(n.properties.orv_capability_intent.media.length,110);h.apply(n,m,'MI2V');
    assert.deepEqual(canonicalDependencies(h,n),before);h.groups(n,m.method_profiles.MI2V.topology);
});
record('PP09 high parked logical ordinals activate as bounded canonical wires, without dropping parked sources',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),n=h.node(m,'MI2V');
    const all=Array.from({length:110},(_,i)=>h.origin(i<100?'image':'video'));
    n.properties.orv_capability_intent.media=all.map((o,index)=>({id:`media_${index}`,order:index,owner_id:n.id,
        origin_id:o.id,origin_slot:0,kind:index<100?'image':'video',reference_name:`direct_references.reference_${index}`,roles:[],collection:false,active_name:null}));
    h.apply(n,m,'VR2V');assert.deepEqual(canonicalDependencies(h,n).map(e=>e.origin),all.slice(100).map(o=>o.id));
    assert(h.refs(n).every(i=>h.c.referenceInputSuffix(i)<100));assert.equal(n.properties.orv_capability_intent.media.length,110);
    const before=canonicalDependencies(h,n);h.apply(n,m,'MI2V');h.apply(n,m,'VR2V');assert.deepEqual(canonicalDependencies(h,n),before);
    h.groups(n,m.method_profiles.VR2V.topology);
});
record('PP10 stale model selection cannot accept a connection or apply old model method topology',()=>{
    const h=harness(),m=model('bytedance/seedance-2.5'),g=model('google/gemini-omni-1.2-flash'),n=h.register(h.node(m,'MI2V'));
    const retained=h.add(n,'image').id;h.c.bindInferenceMethod(n);
    widget(n,'model').value=g.model_id;n.__orvPendingMediaSelection={model:g.model_id,method:'MI2V',revision:1};
    const slot=n.inputs.findIndex(i=>i.link==null&&i.name.startsWith('direct_references.'));
    assert.equal(h.origin('image').connect(0,n,slot),null,'do not connect against old model');
    widget(n,'inference_method').value='I2V';widget(n,'inference_method').callback();
    assert.equal(n.__orvCapability.model_id,m.model_id,'old snapshot retained until new projection arrives');
    assert.equal(n.__orvProjectedKey,`${m.model_id}|MI2V`,'old topology not applied to new selection');
    assert.equal(n.__orvPendingMediaSelection.model,g.model_id);assert.equal(n.__orvPendingMediaSelection.method,'I2V');
    assert.deepEqual(h.active(n).map(i=>i.origin),[retained]);
});
