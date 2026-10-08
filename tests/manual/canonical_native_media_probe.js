// Zero-submit canonical QA. No catalogue/capability overrides and no Queue.
async (page) => {
    await page.setViewportSize({width:1700,height:1150});
    await page.waitForFunction(() => window.comfyAPI?.app?.app?.vueAppReady === true);
    const result = await page.evaluate(async () => {
        const {app} = await import('/scripts/app.js');
        const wait = ms => new Promise(r => setTimeout(r,ms));
        const check = (ok,label) => {if(!ok) throw Error(label);};
        const same = (a,b) => JSON.stringify(a)===JSON.stringify(b);
        const widget = (n,k) => n.widgets.find(w=>w.name===k);
        const fresh = type => {const n=LiteGraph.createNode(type);check(n,`Missing ${type}`);app.graph.add(n);return n;};
        const select = async (n,key,value) => {const w=widget(n,key);w.value=value;w.callback?.(value);await wait(180);};
        const response = await fetch('/openrouter-video/v1/ui-capabilities',{cache:'no-store'});
        check(response.ok,'Production projection unavailable');
        const projection = await response.json();
        check(projection.models.length===30,'Expected 30 production models');
        check(projection.ui_contract_version===4,'UI contract');
        const expectedOrder=[...projection.models].sort((a,b)=>String(a.display_name||a.model_id).localeCompare(String(b.display_name||b.model_id))).map(m=>m.model_id);
        app.graph.clear();
        const matrix=[];
        for(const capability of projection.models){
            const n=fresh('OpenRouterVideoGenerate');await wait(60);
            await select(n,'model',capability.model_id);
            for(let t=0;t<30&&n.__orvCapability?.model_id!==capability.model_id;t++) await wait(100);
            check(n.__orvCapability?.model_id===capability.model_id,`Model projection ${capability.model_id}`);
            const picker=widget(n,'model').options.values.filter(v=>v!=='SELECT MODEL');
            check(same(picker,expectedOrder),'Complete model ordering');
            const methods=widget(n,'inference_method').options.values;
            check(same(methods,capability.supported_inference_methods),`Methods ${capability.model_id}`);
            const ready=capability.inference_method_statuses.filter(s=>s.status==='READY').map(s=>s.method);
            check(same(methods,ready),'READY derivation');
            for(const [key,source] of [['resolution','supported_resolutions'],['aspect_ratio','supported_aspect_ratios']]){
                const actual=widget(n,key).options.values.filter(v=>v!=='AUTO / MODEL DEFAULT');
                check(same(actual,capability[source]||[]),`${key} ${capability.model_id}`);
            }
            check(same(n.__orvDurationValues,capability.supported_durations),`Duration ${capability.model_id}`);
            matrix.push({model:capability.model_id,methods,resolution:widget(n,'resolution').options.values,aspect_ratio:widget(n,'aspect_ratio').options.values,duration:n.__orvDurationValues});
            app.graph.remove(n);
        }
        const n=fresh('OpenRouterVideoGenerate');await wait(100);
        const switches=[];
        for(const id of ['bytedance/seedance-2.5','google/veo-3.1','alibaba/wan-3.0','bytedance/seedance-2.5']){
            if(n.__orvCapability) await select(n,'inference_method','T2V');
            await select(n,'model',id);
            const cap=projection.models.find(m=>m.model_id===id);
            check(same(widget(n,'inference_method').options.values,cap.supported_inference_methods),'Switch methods');
            switches.push({model:id,methods:widget(n,'inference_method').options.values});
        }
        const topology=[];
        for(const method of projection.models.find(m=>m.model_id==='bytedance/seedance-2.5').supported_inference_methods){
            await select(n,'inference_method',method);
            const inputs=n.inputs.map(i=>({name:i.name,type:i.type}));
            const roles=inputs.filter(i=>['first_frame','last_frame','source_video'].includes(i.name)).map(i=>i.name);
            const expected={I2V:['first_frame'],FLF2V:['first_frame','last_frame'],V2V_EDIT:['source_video'],V2V_EXTEND:['source_video']}[method]||[];
            check(same(roles,expected),`Topology ${method}`);
            check(inputs.some(i=>i.name.startsWith('direct_references.'))===['IR2V','MI2V','VR2V','AR2V','MMR2V','V2V_EDIT','V2V_EXTEND'].includes(method),`Reference topology ${method}`);
            topology.push({method,inputs});
        }
        const image=fresh('LoadImage'),video=fresh('LoadVideo'),audio=fresh('LoadAudio');
        const legacy=fresh('OpenRouterVideoVideoReference');
        await select(n,'inference_method','V2V_EDIT');
        let sourceSlot=n.inputs.findIndex(i=>i.name==='source_video');
        check(video.connect(0,n,sourceSlot),'Native Source Video');n.disconnectInput(sourceSlot);
        check(legacy.connect(0,n,sourceSlot),'Legacy Source Video');n.disconnectInput(sourceSlot);
        app.graph.remove(legacy);
        await select(n,'inference_method','MMR2V');
        for(const [index,input] of [image,video,audio,video].entries()){
            const slot=n.inputs.findIndex(i=>i.name===`direct_references.reference_${index}`);
            check(slot>=0&&input.connect(0,n,slot),`Native ${index}`);await wait(80);
        }
        const linked=node=>node.inputs.filter(i=>i.name.startsWith('direct_references.')&&i.link!=null).map(i=>({name:i.name,label:i.label,type:i.type,origin:app.graph.getNodeById(app.graph.links[i.link].origin_id).type}));
        await wait(500);
        const before=linked(n);check(same(before.map(i=>i.origin),['LoadImage','LoadVideo','LoadAudio','LoadVideo']),'Mixed order/duplicates');
        check(!n.__orvReferenceInvalid,'Mixed reference validity');
        // An incompatible switch must preserve the accepted mixed links.
        await select(n,'inference_method','AR2V');
        check(widget(n,'inference_method').value==='MMR2V'&&same(linked(n),before),'Incompatible switch preserved links');
        await select(n,'duration',4);await select(n,'resolution','480p');await select(n,'aspect_ratio','16:9');
        widget(n,'prompt').value='Canonical native media zero-submit QA';
        image.pos=[50,130];video.pos=[50,495];audio.pos=[50,930];n.pos=[630,130];
        const resume=fresh('OpenRouterVideoResume');resume.pos=[1280,180];
        const save=fresh('SaveVideo');save.pos=[1280,550];check(n.connect(0,save,save.inputs.findIndex(i=>i.name==='video')),'SaveVideo');
        const workflow=app.graph.serialize();
        const name=`workflows/ORV_Canonical_Native_Media_QA_${Date.now()}.json`;
        const url='/userdata/'+encodeURIComponent(name);
        const stored=await fetch(url+'?overwrite=false',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(workflow)});
        check(stored.ok,`Save workflow ${stored.status}`);
        const loaded=await fetch(url);check(loaded.ok,'Read saved workflow');
        const persisted=await loaded.json();check(same(persisted,workflow),'Exact save/readback');
        await app.loadGraphData(persisted);await wait(600);
        const restored=app.graph._nodes.find(x=>x.type==='OpenRouterVideoGenerate');
        check(same(linked(restored),before),'Reload links/order/kinds');
        for(const [key,value] of [['model','bytedance/seedance-2.5'],['inference_method','MMR2V'],['duration',4],['resolution','480p'],['aspect_ratio','16:9']]) check(widget(restored,key).value===value,`Reload ${key}`);
        check(!restored.__orvReferenceInvalid,'Reload compatible state');
        app.canvas.ds.scale=.85;app.canvas.ds.offset=[35,40];app.canvas.setDirty(true,true);
        return {host:'canonical DEV 8189',fixture_product_overrides:0,production_projection:projection,model_order:expectedOrder,matrix,switches,topology,native_source_video:true,legacy_source_video:true,before,after:linked(restored),saved_workflow:name,workflow,workflow_queues:0,paid_posts:0,widgets:restored.widgets.map(w=>({name:w.name,y:w.last_y||w.y}))};
    });
    await page.screenshot({path:'output/playwright/canonical-native-media-connections.png',fullPage:true});
    return result;
}
