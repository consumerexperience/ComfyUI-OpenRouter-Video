async (page) => {
    const configuration = await page.evaluate(() =>
        Object.fromEntries(new URLSearchParams(location.hash.slice(1))),
    );
    const hostVersion = configuration.host || "unknown";
    const helperMode = configuration.helper || "enabled";
    const port = configuration.port || "8189";

    const observedAt = "2026-09-27T00:00:00Z";
    const projection = {
        observed_at: observedAt,
        models: [
            {
                model_id: "phase9/model-a",
                display_name: "Phase 9 Model A",
                supported_durations: [4, 5, 6],
                supported_resolutions: ["480p", "720p", "768p"],
                supported_aspect_ratios: ["16:9", "4:3", "5:4"],
                supported_sizes: null,
                supported_frame_types: ["first_frame", "last_frame"],
                supports_seed: true,
                generate_audio: false,
                normalized_reference_modes: [
                    { mode: "multi_image_reference", status: "ENFORCED" },
                    { mode: "video_reference", status: "ENFORCED" },
                    { mode: "image_plus_video_reference", status: "ENFORCED" },
                ],
                observed_at: observedAt,
            },
            {
                model_id: "phase9/model-b",
                display_name: "Phase 9 Model B",
                supported_durations: [4, 6, 8],
                supported_resolutions: ["720p", "1080p"],
                supported_aspect_ratios: ["1:1", "3:2"],
                supported_sizes: ["854x480"],
                supported_frame_types: ["first_frame"],
                supports_seed: false,
                generate_audio: true,
                normalized_reference_modes: [
                    { mode: "multi_image_reference", status: "UNSUPPORTED" },
                    { mode: "video_reference", status: "UNSUPPORTED" },
                    { mode: "image_plus_video_reference", status: "UNSUPPORTED" },
                ],
                observed_at: observedAt,
            },
        ],
    };

    if (helperMode === "disabled") {
        await page.route("**/extensions/**/openrouter_video.js", async (route) => {
            await route.fulfill({ status: 200, contentType: "text/javascript", body: "" });
        });
    }
    await page.route("**/openrouter-video/v1/ui-capabilities", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(projection),
        });
    });
    await page.route("**/openrouter-video/v1/models", async (route) => {
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(["SELECT MODEL", "phase9/model-a", "phase9/model-b"]),
        });
    });
    await page.route("**/openrouter-video/v1/cost-estimate", async (route) => {
        const request = JSON.parse(route.request().postData() || "{}");
        const amount = request.model_id === "phase9/model-b" ? "0.4200" : "0.1400";
        await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
                availability: "AVAILABLE",
                estimated_cost_usd: amount,
                observed_at: observedAt,
                provenance: "synthetic-loopback-ui-probe",
                applied_skus: ["probe-only"],
            }),
        });
    });

    await page.goto(`http://127.0.0.1:${port}`);
    await page.waitForFunction(() => document.title.includes("ComfyUI"));
    await page.waitForFunction(() => Boolean(window.comfyAPI?.app?.app?.graph));
    await page.waitForFunction(() => window.comfyAPI?.app?.app?.vueAppReady === true);
    await page.waitForTimeout(500);

    const evidence = await page.evaluate(async ({ hostVersion, helperMode }) => {
        const { app } = await import("/scripts/app.js");
        const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
        const getWidget = (node, name) => node.widgets?.find((item) => item.name === name);
        const snapshot = (node) => Object.fromEntries(
            (node.widgets || []).map((item) => [
                item.name,
                {
                    type: item.type,
                    value: item.value,
                    hidden: Boolean(item.hidden),
                    values: item.options?.values ?? null,
                    min: item.options?.min ?? null,
                    max: item.options?.max ?? null,
                    step: item.options?.step ?? null,
                    control_after_generate: item.options?.control_after_generate ?? null,
                },
            ]),
        );
        const createNode = async () => {
            const node = globalThis.LiteGraph.createNode("OpenRouterVideoGenerate");
            if (!node) throw new Error("OpenRouterVideoGenerate is not registered");
            app.graph.add(node);
            await wait(400);
            return node;
        };

        app.graph.clear();
        const node = await createNode();
        const initial = snapshot(node);

        if (helperMode === "disabled") {
            const model = getWidget(node, "model");
            model.value = "phase9/model-a";
            model.callback?.(model.value);
            await wait(500);
            const nativeOnly = {
                host_version: hostVersion,
                helper_mode: helperMode,
                initial,
                after_model_switch: snapshot(node),
                helper_controls_present: Boolean(getWidget(node, "CAPABILITY STATUS")),
                dependent_resolution_type: getWidget(node, "resolution")?.type ?? null,
                dependent_resolution_values: getWidget(node, "resolution")?.options?.values ?? null,
            };
            nativeOnly.checks = {
                unresolved_model_is_native: initial.model?.value === "SELECT MODEL",
                helper_is_absent: nativeOnly.helper_controls_present === false,
                resolution_remains_free_text:
                    nativeOnly.dependent_resolution_type === "text" &&
                    nativeOnly.dependent_resolution_values === null,
            };
            const failures = Object.entries(nativeOnly.checks)
                .filter(([, passed]) => !passed)
                .map(([name]) => name);
            if (failures.length) throw new Error(`native-only checks failed: ${failures.join(", ")}`);
            return nativeOnly;
        }

        const model = getWidget(node, "model");
        model.value = "phase9/model-a";
        model.callback?.(model.value);
        await wait(500);
        const modelA = snapshot(node);

        getWidget(node, "OUTPUT GEOMETRY").value = "RESOLUTION + ASPECT RATIO";
        getWidget(node, "OUTPUT GEOMETRY").callback?.("RESOLUTION + ASPECT RATIO");
        getWidget(node, "resolution").value = "480p";
        getWidget(node, "aspect_ratio").value = "16:9";
        getWidget(node, "DURATION MODE").value = "EXPLICIT DURATION";
        getWidget(node, "DURATION MODE").callback?.("EXPLICIT DURATION");
        getWidget(node, "duration").value = 4;
        getWidget(node, "duration").callback?.(4);
        getWidget(node, "seed").value = 42;
        await wait(300);
        const paidIntentBeforeSwitch = snapshot(node);

        const serializedModelA = app.graph.serialize();
        app.graph.clear();
        app.graph.configure(serializedModelA);
        await wait(600);
        const restoredModelA = app.graph._nodes.find(
            (item) => item.type === "OpenRouterVideoGenerate",
        );
        if (!restoredModelA) throw new Error("model-A workflow did not reload");
        const modelAReloaded = snapshot(restoredModelA);

        const restoredModel = getWidget(restoredModelA, "model");
        restoredModel.value = "phase9/model-b";
        restoredModel.callback?.(restoredModel.value);
        await wait(500);
        const modelB = snapshot(restoredModelA);

        const imageReference = globalThis.LiteGraph.createNode(
            "OpenRouterVideoImageReference",
        );
        const videoReference = globalThis.LiteGraph.createNode(
            "OpenRouterVideoVideoReference",
        );
        const collection = globalThis.LiteGraph.createNode(
            "OpenRouterVideoReferenceCollection",
        );
        const saveVideo = globalThis.LiteGraph.createNode("SaveVideo");
        for (const required of [imageReference, videoReference, collection, saveVideo]) {
            if (!required) throw new Error("required native/reference node is not registered");
            app.graph.add(required);
        }
        collection.connect(0, restoredModelA, 0);
        restoredModelA.connect(0, saveVideo, 0);
        await wait(300);
        const referenceAndVideo = {
            collection_output: collection.outputs?.[0]?.type ?? null,
            generate_reference_input: restoredModelA.inputs?.[0]?.type ?? null,
            generate_video_output: restoredModelA.outputs?.[0]?.type ?? null,
            save_video_input: saveVideo.inputs?.[0]?.type ?? null,
            reference_linked: restoredModelA.inputs?.[0]?.link != null,
            save_video_linked: saveVideo.inputs?.[0]?.link != null,
            estimate: getWidget(restoredModelA, "ESTIMATED COST")?.value ?? null,
            registered_reference_nodes: [
                imageReference.type,
                videoReference.type,
                collection.type,
            ],
        };

        const serialized = app.graph.serialize();
        app.graph.clear();
        app.graph.configure(serialized);
        await wait(600);
        const restored = app.graph._nodes.find((item) => item.type === "OpenRouterVideoGenerate");
        if (!restored) throw new Error("serialized Generate node did not reload");
        const reloaded = snapshot(restored);
        const saveVideoReloaded = app.graph._nodes.find((item) => item.type === "SaveVideo");
        const reloadedLinks = {
            reference_linked: restored.inputs?.[0]?.link != null,
            save_video_linked: saveVideoReloaded?.inputs?.[0]?.link != null,
        };

        const phase8 = await createNode();
        const legacy = phase8.serialize();
        legacy.widgets_values = [
            "phase9/model-a",
            false,
            "refresh",
            "legacy prompt",
            "6",
            "480p",
            "16:9",
            "",
            "77",
            "randomize",
            false,
            "https://assets.example/first.png",
            "",
        ];
        phase8.configure(legacy);
        await wait(600);
        const migrated = snapshot(phase8);

        const checks = {
            initial_model_unresolved: initial.model?.value === "SELECT MODEL",
            initial_estimate_unavailable:
                initial["ESTIMATED COST"]?.value === "ESTIMATE UNAVAILABLE — SELECT MODEL",
            complete_future_resolution_reachable:
                modelA.resolution?.values?.includes("768p") === true,
            complete_future_aspect_reachable:
                modelA.aspect_ratio?.values?.includes("5:4") === true,
            arithmetic_duration_exact:
                paidIntentBeforeSwitch.duration?.min === 4 &&
                paidIntentBeforeSwitch.duration?.max === 6 &&
                paidIntentBeforeSwitch.duration?.step === 1,
            seed_controls_complete:
                JSON.stringify(paidIntentBeforeSwitch.randomize?.values) ===
                JSON.stringify(["fixed", "increment", "decrement", "randomize"]),
            audio_and_frames_follow_model_a:
                modelA.generate_audio?.hidden === true &&
                modelA.first_frame_url?.hidden === false &&
                modelA.last_frame_url?.hidden === false,
            estimate_updates_for_model:
                modelA["ESTIMATED COST"]?.value === "≈ $0.1400 EST." &&
                modelB["ESTIMATED COST"]?.value === "≈ $0.4200 EST.",
            valid_paid_intent_survives_reload:
                modelAReloaded.model?.value === "phase9/model-a" &&
                modelAReloaded.duration?.value === 4 &&
                modelAReloaded.resolution?.value === "480p" &&
                modelAReloaded.aspect_ratio?.value === "16:9" &&
                modelAReloaded.seed?.value === 42,
            invalid_paid_intent_resets_visibly:
                modelB.resolution?.value === "AUTO / MODEL DEFAULT" &&
                modelB.aspect_ratio?.value === "AUTO / MODEL DEFAULT" &&
                modelB["CAPABILITY STATUS"]?.value.includes("unsupported saved value") === true,
            valid_duration_is_preserved_on_model_switch: modelB.duration?.value === 4,
            seed_audio_and_frames_follow_model_b:
                modelB.seed?.hidden === true &&
                modelB.generate_audio?.hidden === false &&
                modelB.last_frame_url?.hidden === true,
            typed_references_and_native_video_connect:
                referenceAndVideo.collection_output === "OPENROUTER_VIDEO_INPUT_REFERENCES" &&
                referenceAndVideo.generate_reference_input ===
                    "OPENROUTER_VIDEO_INPUT_REFERENCES" &&
                referenceAndVideo.generate_video_output === "VIDEO" &&
                referenceAndVideo.save_video_input === "VIDEO" &&
                referenceAndVideo.reference_linked === true &&
                referenceAndVideo.save_video_linked === true,
            reference_link_updates_estimate:
                referenceAndVideo.estimate ===
                "ESTIMATE UNAVAILABLE — REFERENCE SHAPE RESOLVES AT EXECUTION",
            links_survive_reload:
                reloadedLinks.reference_linked === true && reloadedLinks.save_video_linked === true,
            phase8_values_migrate_without_intent_drift:
                migrated.model?.value === "phase9/model-a" &&
                migrated.prompt?.value === "legacy prompt" &&
                migrated.duration?.value === 6 &&
                migrated.resolution?.value === "480p" &&
                migrated.aspect_ratio?.value === "16:9" &&
                migrated.seed?.value === 77 &&
                migrated.first_frame_url?.value === "https://assets.example/first.png",
        };
        const failures = Object.entries(checks)
            .filter(([, passed]) => !passed)
            .map(([name]) => name);
        if (failures.length) throw new Error(`helper checks failed: ${failures.join(", ")}`);

        return {
            host_version: hostVersion,
            helper_mode: helperMode,
            initial,
            model_a: modelA,
            paid_intent_before_switch: paidIntentBeforeSwitch,
            model_a_reloaded: modelAReloaded,
            model_b: modelB,
            reference_and_native_video: referenceAndVideo,
            reloaded,
            reloaded_links: reloadedLinks,
            phase8_migrated: migrated,
            checks,
            node_type: node.type,
            input_names: node.inputs?.map((item) => item.name) ?? [],
            output_types: node.outputs?.map((item) => item.type) ?? [],
        };
    }, { hostVersion, helperMode });

    return evidence;
}
