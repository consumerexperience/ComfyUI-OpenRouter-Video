// Preconditions: governed supervisor launch; no persistent S3 variables present.
// The actual production node must fail storage configuration before any PUT/POST.
async (page) => {
    const result=await page.evaluate(async()=>{
        const {app}=await import('/scripts/app.js');
        const {api}=await import('/scripts/api.js');
        const nodes=app.graph._nodes;
        const generate=nodes.find(n=>n.type==='OpenRouterVideoGenerate');
        const w=(n,key)=>n.widgets.find(w=>w.name===key);
        w(nodes.find(n=>n.type==='LoadImage'),'image').value='ORV_Canonical_QA_synthetic.png';
        w(nodes.find(n=>n.type==='LoadVideo'),'file').value='ORV_Canonical_QA_synthetic.mp4';
        w(nodes.find(n=>n.type==='LoadAudio'),'audio').value='ORV_Canonical_QA_synthetic.wav';
        const resume=nodes.find(n=>n.type==='OpenRouterVideoResume');
        app.graph.remove(resume); // No remote job observation is authorized here.
        const workflow=app.graph.serialize();
        const name=`workflows/ORV_Canonical_Native_Media_Inputs_${Date.now()}.json`;
        const path='/userdata/'+encodeURIComponent(name);
        const saved=await fetch(path+'?overwrite=false',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(workflow)});
        if(!saved.ok) throw Error('Synthetic workflow save failed');
        const readback=await (await fetch(path)).json();
        await app.loadGraphData(readback);
        await new Promise(r=>setTimeout(r,800));
        const capture=new Promise((resolve,reject)=>{
            const timer=setTimeout(()=>{api.removeEventListener('execution_error',handler);reject(Error('Expected configuration error timeout'));},30000);
            const handler=event=>{
                api.removeEventListener('execution_error',handler);clearTimeout(timer);
                const message=String(event.detail?.exception_message||'');
                if(!message.includes('STORAGE_UPLOAD_FAILED: Configure local S3 endpoint, region, bucket and credentials.')) {
                    reject(Error('Unexpected execution failure; inspect safe product category'));return;
                }
                resolve({error:'STORAGE_UPLOAD_FAILED: Configure local S3 endpoint, region, bucket and credentials.',node_type:event.detail.node_type});
            };
            api.addEventListener('execution_error',handler);
        });
        await app.queuePrompt(0,1);
        const error=await capture;
        return {...error,workflow,saved_workflow:name,negative_workflow_queues:1,storage_puts:0,paid_video_posts:0,catalogue_override:false};
    });
    await page.screenshot({path:'output/playwright/canonical-native-media-storage-error.png',fullPage:true});
    return result;
}
