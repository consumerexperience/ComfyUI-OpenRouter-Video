async (page) => {
    await page.setViewportSize({width:1600,height:1100});
    const state = await page.evaluate(async () => {
        const { app } = await import("/scripts/app.js");
        const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));
        const byType = type => app.graph._nodes.find(n => n.type === type);
        const types = ["LoadImage","LoadVideo","LoadAudio","OpenRouterVideoGenerate","SaveVideo"];
        if (!types.every(type => byType(type))) {
            app.graph.clear();
            for (const type of types) {
                const node = globalThis.LiteGraph.createNode(type);
                if (!node) throw Error(`Missing native node ${type}`);
                app.graph.add(node);
            }
        }
        const widget = (node, name) => node.widgets.find(w => w.name === name);
        const image = byType("LoadImage"), video = byType("LoadVideo"), audio = byType("LoadAudio");
        const generate = byType("OpenRouterVideoGenerate"), save = byType("SaveVideo");
        if (![image,video,audio,generate,save].every(Boolean)) throw Error("Expected native nodes");
        image.pos = [90,160]; video.pos = [90,524]; audio.pos = [90,957];
        generate.pos = [600,160]; save.pos = [1250,160];
        widget(image,"image").value="synthetic.png";
        widget(video,"file").value="synthetic.mp4";
        widget(audio,"audio").value="synthetic.wav";
        widget(generate,"prompt").value="Synthetic native media bridge proof";
        widget(generate,"model").value="bytedance/seedance-2.5";
        widget(generate,"model").callback?.("bytedance/seedance-2.5");
        await wait(500);
        widget(generate,"inference_method").value="MMR2V";
        widget(generate,"inference_method").callback?.("MMR2V");
        await wait(300);
        for (const [index,source] of [image,video,audio,video].entries()) {
            const slot = generate.inputs.findIndex(i => i.name === `direct_references.reference_${index}`);
            if (slot < 0 || !source.connect(0,generate,slot)) throw Error(`Native connection ${index} rejected`);
            await wait(250);
        }
        generate.connect(0,save,save.inputs.findIndex(i=>i.name==="video"));
        const linked = () => generate.inputs.filter(i=>i.name.startsWith("direct_references.") && i.link!=null).map(i=>({name:i.name,type:i.type,label:i.label,origin:app.graph.getNodeById(app.graph.links[i.link].origin_id).type}));
        const before=linked();
        if (before.map(i=>i.origin).join()!=="LoadImage,LoadVideo,LoadAudio,LoadVideo") throw Error("Order or duplicates changed");
        const workflow=app.graph.serialize();
        await app.loadGraphData(workflow);
        await wait(600);
        const loaded=byType("OpenRouterVideoGenerate");
        const after=loaded.inputs.filter(i=>i.name.startsWith("direct_references.") && i.link!=null).map(i=>({name:i.name,type:i.type,label:i.label,origin:app.graph.getNodeById(app.graph.links[i.link].origin_id).type}));
        if (JSON.stringify(before)!==JSON.stringify(after)) throw Error("Reload changed native references");
        if (widget(loaded,"inference_method").value!=="MMR2V") throw Error("Method lost on reload");
        app.canvas.ds.scale=.85;app.canvas.ds.offset=[40,80];app.canvas.setDirty(true,true);
        return {host:"ComfyUI v0.37.0 fixture",frontend:"1.52.7",before,after,workflow,reference_summary:loaded.__orvReferenceSummary,invalid:loaded.__orvReferenceInvalid};
    });
    await page.screenshot({path:"output/playwright/native-media-connections.png",fullPage:true});
    return state;
}
