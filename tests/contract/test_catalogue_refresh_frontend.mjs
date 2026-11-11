import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source = readFileSync(new URL('../../web/openrouter_video.js', import.meta.url), 'utf8').replace(/^import .*;\r?\n/gm, '');
const clone = value => JSON.parse(JSON.stringify(value));
function harness() {
    const events = {}, timers = new Map(), calls = [], projections = [];
    let serial = 0, snapshot = {models: [], ui_contract_version: 7};
    let fetchImpl = async () => ({ok: true, json: async () => clone(snapshot)});
    const node = {type:'OpenRouterVideoGenerate', properties:{}, widgets:[
        {name:'model',value:'old/model',options:{}}, {name:'prompt',value:'KEEP PROMPT', options:{}}
    ], inputs:[{name:'first_frame',link:42}], __orvCapabilityStatus:{}, setDirtyCanvas(){}};
    const context = {
        app:{graph:{_nodes:[node]},registerExtension(){}},
        document:{visibilityState:'visible',addEventListener:(k,f)=>events[k]=f},
        navigator:{onLine:true},window:{addEventListener:(k,f)=>events[k]=f},
        api:{fetchApi:async url=>{
            calls.push(url);
            if (url.endsWith('/connection')) return {ok:true,json:async()=>({state:'CONNECTED'})};
            return fetchImpl();
        }},
        setTimeout(f,ms){const id=++serial;timers.set(id,{f,ms});return id;},
        clearTimeout(id){timers.delete(id);}
    };
    vm.runInNewContext(source,context);
    // Scheduler/HTTP unit seam. Real semantic reprojection is covered by the
    // existing public-projection and Nodes2 contracts, not mocked into UI proof.
    context.capture = (n,p)=>{projections.push(clone(p));context.configureModelPicker(n,p);};
    vm.runInNewContext('projectSelectedModel = async (node,force,projection) => capture(node,projection);',context);
    return {c:context,events,timers,calls,projections,node,
        snapshot(value){snapshot=value;},fetch(fn){fetchImpl=fn;}};
}

test('R17/R18 new eligible IDs appear live, backend-only exclusions do not',async()=>{
    const h=harness();h.snapshot({models:[{model_id:'new/model',display_name:'New',supported_inference_methods:['T2V']}],unavailable_models:[{model_id:'hidden/model'}]});
    await h.c.refreshCatalogue();
    assert.deepEqual(clone(h.node.widgets[0].options.values),['SELECT MODEL','new/model']);
    assert.equal(h.node.widgets[0].value,'old/model');
    assert.equal(h.projections.length,1);
});

test('semantic revision ignores observation clock but tracks contract and fallback changes', async()=>{
    const h=harness();
    const base={models:[{model_id:'old/model'}],catalogue_revision:'same',source_state:'FRESH'};
    h.snapshot({...base,observed_at:'first'}); await h.c.refreshCatalogue();
    h.snapshot({...base,observed_at:'later'}); await h.c.refreshCatalogue();
    assert.equal(h.projections.length,1);
    h.snapshot({...base,catalogue_revision:'changed-domain'}); await h.c.refreshCatalogue();
    assert.equal(h.projections.length,2);
    h.snapshot({...base,catalogue_revision:'changed-domain',source_state:'STALE_FALLBACK'});
    await h.c.refreshCatalogue(); assert.equal(h.projections.length,3);
});

test('Settings accounts for unavailable models safely without exposing raw JSON controls',async()=>{
    const h=harness();
    const element=()=>({children:[],value:'hidden/model',append(...v){this.children.push(...v);},
        setAttribute(){},replaceChildren(){this.children=[];}});
    h.c.document.createElement=element;
    h.snapshot({models:[],source_state:'FRESH',capability_completeness:{
        discovered_model_count:1,executable_method_count:0,models:[{model_id:'hidden/model',rows:[{
            path:'new_control',disposition:'EVIDENCE_GAP',reason:'<script>untrusted</script>'}]}]}});
    const root=h.c.capabilitySettingRenderer();
    await h.c.loadCapabilities(); await Promise.resolve();
    assert(root.children[0].textContent.includes('Accounted capabilities are not proof'));
    assert.equal(root.children[1].children[0].textContent,'hidden/model');
    assert(root.children[2].children[0].textContent.includes('EVIDENCE_GAP'));
    assert.equal(root.children[2].children[0].innerHTML,undefined);
});

test('R19/R20/R24 capability-only upgrade/downgrade is reprojected',async()=>{
    const h=harness();
    for (const methods of [[],['T2V'],['T2V','I2V'],['T2V']]) {
        h.snapshot({models:[{model_id:'old/model',supported_inference_methods:methods}]});
        await h.c.refreshCatalogue();
    }
    assert.equal(h.projections.length,4);
    assert.deepEqual(h.projections.map(p=>p.models[0].supported_inference_methods.length),[0,1,2,1]);
});

test('R21/R08 unavailable selection survives picker and save/reload without prompt/link loss',()=>{
    const h=harness();
    assert.equal(h.c.configureModelPicker(h.node,{models:[]}), 'old/model');
    const saved=clone(h.node);
    h.c.configureModelPicker(saved,{models:[{model_id:'replacement'}]});
    assert.equal(saved.widgets[0].value,'old/model');
    assert.equal(saved.widgets[1].value,'KEEP PROMPT');
    assert.equal(saved.inputs[0].link,42);
});

test('R22 concurrent force requests deduplicate; obsolete response cannot replace new cache',async()=>{
    const h=harness();let release;
    h.fetch(()=>new Promise(resolve=>{release=resolve;}));
    const a=h.c.loadCapabilities(true), b=h.c.loadCapabilities(true);
    assert.equal(h.calls.length,1);
    h.c.setConnectionPresentation({state:'CONNECTED'});
    h.c.setConnectionPresentation({state:'DISCONNECTED'});
    h.fetch(async()=>({ok:true,json:async()=>({models:[{model_id:'newest'}]})}));
    const newest=await h.c.loadCapabilities(true);
    release({ok:true,json:async()=>({models:[{model_id:'obsolete'}]})});
    await assert.rejects(a,/obsolete/);await assert.rejects(b,/obsolete/);
    assert.equal((await h.c.loadCapabilities()).models[0].model_id,newest.models[0].model_id);
});

test('R23 active polling is bounded; hidden/offline pauses and foreground/online recover',async()=>{
    const h=harness();h.c.startCatalogueLifecycle();
    await h.c.refreshCatalogue();
    assert.equal([...h.timers.values()][0].ms,300000);
    h.c.document.visibilityState='hidden';h.events.visibilitychange();
    assert.equal(h.timers.size,0);
    const before=h.calls.length;await h.c.refreshCatalogue();assert.equal(h.calls.length,before);
    h.c.document.visibilityState='visible';h.events.visibilitychange();await h.c.refreshCatalogue();
    assert(h.calls.length>before);
    h.c.navigator.onLine=false;h.events.offline();assert.equal(h.timers.size,0);
    h.c.navigator.onLine=true;h.events.online();await h.c.refreshCatalogue();
    assert.equal(h.timers.size,1);
});

test('temporary catalogue failure is not cached forever and recovers on next trigger',async()=>{
    const h=harness();h.fetch(async()=>({ok:false}));
    await h.c.refreshCatalogue();assert.equal(h.node.__orvCatalogueFailed,true);
    h.fetch(async()=>({ok:true,json:async()=>({models:[{model_id:'old/model'}]})}));
    await h.c.refreshCatalogue();assert.equal(h.projections.length,1);
    assert.equal(h.node.widgets[1].value,'KEEP PROMPT');
});
