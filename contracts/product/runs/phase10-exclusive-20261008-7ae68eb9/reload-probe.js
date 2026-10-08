async page => {
    let queueAttempts = 0;
    await page.route('**/prompt', async route => {queueAttempts++; await route.abort();});
    // Full page reload was executed immediately before this readback; the
    // browser's beforeunload confirmation was explicitly accepted by CLI.
    await page.waitForFunction(() => window.comfyAPI?.app?.app?.vueAppReady === true);
    const proof = await page.evaluate(async () => {
        const {app} = await import('/scripts/app.js');
        const name = 'workflows/ORV_Canonical_Native_Media_QA_1791486753787.json';
        const response = await fetch('/userdata/'+encodeURIComponent(name), {cache:'no-store'});
        if(!response.ok) throw Error('Persisted workflow missing after full page reload');
        const workflow = await response.json();
        await app.loadGraphData(workflow);
        await new Promise(resolve => setTimeout(resolve,800));
        const n = app.graph._nodes.find(x => x.type==='OpenRouterVideoGenerate');
        if(!n) throw Error('Generate node not restored');
        const linked = n.inputs.filter(i=>i.name.startsWith('direct_references.') && i.link!=null)
            .map(i=>({name:i.name, origin:app.graph.getNodeById(app.graph.links[i.link].origin_id).type}));
        if(JSON.stringify(linked.map(i=>i.origin))!==JSON.stringify(['LoadImage','LoadVideo','LoadAudio','LoadVideo']))
            throw Error('Mixed order/duplicates lost after full reload');
        const widget = key => n.widgets.find(w=>w.name===key);
        const values = {model:'bytedance/seedance-2.5',inference_method:'MMR2V',resolution:'480p',aspect_ratio:'16:9',duration:4};
        for(const [key,value] of Object.entries(values)) if(widget(key)?.value!==value) throw Error('Reload '+key);
        if(n.__orvReferenceInvalid) throw Error('Restored references invalid');
        const resume = app.graph._nodes.find(x=>x.type==='OpenRouterVideoResume');
        if(!resume || resume.widgets.some(w=>['model','prompt','inference_method'].includes(w.name))) throw Error('Resume generation controls drifted');
        app.canvas.ds.scale=.85; app.canvas.ds.offset=[35,40]; app.canvas.setDirty(true,true);
        return {run_id:'phase10-exclusive-20261008-7ae68eb9',full_page_reload:true,saved_workflow:name,linked,values,
                resume_widgets:resume.widgets.map(w=>w.name),workflow_queues:0,paid_posts:0,completed_at:new Date().toISOString()};
    });
    if(queueAttempts) throw Error('Forbidden queue attempt');
    await page.screenshot({path:'output/playwright/phase10-exclusive-7ae68eb9-reloaded.png',fullPage:true});
    return {...proof,queue_attempts:queueAttempts};
}
