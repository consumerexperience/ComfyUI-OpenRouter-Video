// Real canonical catalogue. No fixture substitution, Generate, Resume, uploads or paid calls.
async (page) => {
    await page.setViewportSize({ width: 1700, height: 1150 });
    await page.waitForFunction(() => window.comfyAPI?.app?.app?.vueAppReady === true);
    const result = await page.evaluate(async () => {
        const { app } = await import('/scripts/app.js');
        const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const check = (ok, label) => { if (!ok) throw Error(label); };
        const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
        const widget = (node, name) => node.widgets.find((item) => item.name === name);
        const create = (type) => {
            const node = LiteGraph.createNode(type);
            check(node, `Missing ${type}`); app.graph.add(node); return node;
        };
        const select = async (node, name, value) => {
            const item = widget(node, name); item.value = value; item.callback?.(value);
            await wait(220);
        };
        const response = await fetch('/openrouter-video/v1/ui-capabilities', { cache: 'no-store' });
        check(response.ok, 'Production capability route');
        const projection = await response.json();
        const ids = await (await fetch('/openrouter-video/v1/models', { cache: 'no-store' })).json();
        check(same(projection.models.map((m) => m.model_id).sort(), ids.filter((id) => id !== 'SELECT MODEL').sort()), 'Complete current catalogue');
        app.graph.clear();
        const matrix = [];
        for (const capability of projection.models) {
            const node = create('OpenRouterVideoGenerate'); await wait(70);
            await select(node, 'model', capability.model_id);
            for (let i = 0; i < 30 && node.__orvCapability?.model_id !== capability.model_id; i++) await wait(100);
            check(node.__orvCapability?.model_id === capability.model_id, `Projection ${capability.model_id}`);
            for (const [name, key] of [['resolution', 'supported_resolutions'], ['aspect_ratio', 'supported_aspect_ratios'], ['duration', 'supported_durations']]) {
                const item = widget(node, name);
                check(item.type === 'combo', `${capability.model_id}: real ${name} combo`);
                const expected = capability[key] || [];
                const actual = item.options.values.filter((v) => v !== 0 && v !== 'AUTO / MODEL DEFAULT');
                check(same([...actual].sort(), [...expected].sort()), `${capability.model_id}: exhaustive ${name} values`);
            }
            check(same(widget(node, 'inference_method').options.values, capability.supported_inference_methods), 'Existing methods preserved');
            matrix.push({ model: capability.model_id, resolutions: capability.supported_resolutions,
                aspects: capability.supported_aspect_ratios, durations: capability.supported_durations,
                methods: capability.supported_inference_methods });
            app.graph.remove(node);
        }
        const node = create('OpenRouterVideoGenerate'); await wait(80);
        await select(node, 'model', 'minimax/hailuo-3');
        await select(node, 'resolution', '2K'); await select(node, 'duration', 10);
        await select(node, 'model', 'bytedance/seedance-2.0-mini');
        check(widget(node, 'resolution').value === '2K', 'Saved incompatible intent preserved');
        check(String(node.__orvCapabilityStatus.value).includes('incompatible'), 'Incompatibility visible');
        const incompatible = { resolution: widget(node, 'resolution').value, status: node.__orvCapabilityStatus.value };
        await select(node, 'resolution', '480p'); await select(node, 'duration', 4);
        await select(node, 'aspect_ratio', '16:9');
        await select(node, 'inference_method', 'MMR2V');
        const image = create('LoadImage'), video = create('LoadVideo'), audio = create('LoadAudio');
        const slots = () => node.inputs.map((input, slot) => ({ input, slot })).filter(({ input }) => input.name.startsWith('direct_references.'));
        const connect = (source) => {
            const slot = slots().find(({ input }) => input.link == null);
            check(slot && source.connect(0, node, slot.slot), 'Native reference connection');
        };
        connect(image); await wait(250); connect(video); await wait(250);
        connect(audio); await wait(250); connect(video); await wait(250);
        const linked = (target) => target.inputs.filter((input) => input.name.startsWith('direct_references.') && input.link != null)
            .map((input) => {
                const link = app.graph.links[input.link]; return app.graph.getNodeById(link.origin_id).type;
            });
        check(same(linked(node), ['LoadImage', 'LoadVideo', 'LoadAudio', 'LoadVideo']), 'Native order and duplicate VIDEO');
        check(!node.__orvReferenceInvalid, 'Mini accepted MMR2V topology');
        const nativeTopology = { before: linked(node), inference_method: widget(node, 'inference_method').value };
        // Explicit method changes preserve connected intent and do not reinterpret media.
        await select(node, 'inference_method', 'AR2V');
        check(widget(node, 'inference_method').value === 'MMR2V', 'Incompatible method switch rejected');
        check(same(linked(node), nativeTopology.before), 'Links preserved');
        widget(node, 'prompt').value = 'Adaptive generation controls: zero-paid canonical QA';
        image.pos = [40, 130]; video.pos = [40, 480]; audio.pos = [40, 870]; node.pos = [610, 130];
        const workflow = app.graph.serialize();
        const name = `workflows/ORV_Adaptive_Controls_QA_${Date.now()}.json`;
        const url = '/userdata/' + encodeURIComponent(name);
        const saved = await fetch(url + '?overwrite=false', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(workflow) });
        check(saved.ok, 'Save workflow');
        const readback = await (await fetch(url)).json(); check(same(workflow, readback), 'Exact save/readback');
        await app.loadGraphData(readback); await wait(750);
        const restored = app.graph._nodes.find((n) => n.type === 'OpenRouterVideoGenerate');
        for (const [name, value] of [['model', 'bytedance/seedance-2.0-mini'], ['inference_method', 'MMR2V'], ['resolution', '480p'], ['aspect_ratio', '16:9'], ['duration', 4]]) {
            check(widget(restored, name).value === value, `Reload ${name}`);
        }
        check(same(linked(restored), nativeTopology.before), 'Reload native order and duplicates');
        app.canvas.ds.scale = .85; app.canvas.ds.offset = [35, 40]; app.canvas.setDirty(true, true);
        return { observed_at: projection.observed_at, catalog_model_count: projection.models.length,
            exact_model_ids: projection.models.map((m) => m.model_id), matrix, incompatible,
            nativeTopology, nativeTopologyAfterReload: linked(restored), saved_workflow: name,
            workflow, fixture_catalogue_overrides: 0, queues: 0, paid_posts: 0,
            no_separate_mode_control: !widget(restored, 'mode'),
            configuration_relations_published: projection.models.filter((m) => m.configuration_relations?.length).map((m) => m.model_id) };
    });
    await page.screenshot({ path: 'output/playwright/adaptive-controls-canonical.png', fullPage: true });
    // File writing is performed by the CLI caller from the returned result.
    return result;
}
