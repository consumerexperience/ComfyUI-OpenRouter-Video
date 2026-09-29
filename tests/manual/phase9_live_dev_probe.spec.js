// Manual zero-cost live acceptance: never queues a workflow or calls the paid Video API.
const { test, expect } = require("playwright/test");

const executablePath = process.env.ORV_PLAYWRIGHT_CHROMIUM;
if (executablePath) test.use({ launchOptions: { executablePath } });

test("canonical DEV catalogue and picker remain coherent", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push({ method: request.method(), url: request.url() }));

  await page.goto("http://127.0.0.1:8189/");
  await page.waitForFunction(() => document.title.includes("ComfyUI"));
  await page.waitForFunction(() => Boolean(window.comfyAPI?.app?.app?.graph));
  await page.waitForFunction(() => window.comfyAPI?.app?.app?.vueAppReady === true);
  await page.waitForTimeout(500);

  const evidence = await page.evaluate(async () => {
    const { app } = await import("/scripts/app.js");
    const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
    const projectionResponse = await fetch("/openrouter-video/v1/ui-capabilities", { cache: "no-store" });
    if (!projectionResponse.ok) throw new Error(`projection failed: ${projectionResponse.status}`);
    const projection = await projectionResponse.json();
    const backendIds = projection.models.map((item) => item.model_id);

    app.graph.clear();
    const generate = globalThis.LiteGraph.createNode("OpenRouterVideoGenerate");
    if (!generate) throw new Error("OpenRouterVideoGenerate is not registered");
    app.graph.add(generate);
    await wait(1200);

    const model = generate.widgets?.find((item) => item.name === "model");
    const selectable = (model?.options?.values || []).filter((value) => value !== "SELECT MODEL");
    const selected = selectable[Math.min(16, selectable.length - 1)];
    if (!selected) throw new Error("model picker has no selectable values");
    model.value = selected;
    model.callback?.(selected);
    await wait(700);

    const serialized = app.graph.serialize();
    app.graph.clear();
    app.graph.configure(serialized);
    await wait(900);
    const restored = app.graph._nodes.find((item) => item.type === "OpenRouterVideoGenerate");
    if (!restored) {
      throw new Error(`Generate node did not reload; types=${JSON.stringify(app.graph._nodes.map((item) => item.type))}`);
    }
    const restoredModel = restored?.widgets?.find((item) => item.name === "model")?.value ?? null;

    const saveVideo = globalThis.LiteGraph.createNode("SaveVideo");
    if (!saveVideo) throw new Error("SaveVideo is not registered");
    app.graph.add(saveVideo);
    restored.connect(0, saveVideo, 0);

    return {
      host_version: window.comfyAPI?.app?.app?.version ?? "0.34.3",
      ui_contract_version: projection.ui_contract_version,
      backend_model_count: backendIds.length,
      selectable_model_count: selectable.length,
      exact_model_set: JSON.stringify([...backendIds].sort()) === JSON.stringify([...selectable].sort()),
      selected_model: selected,
      restored_model: restoredModel,
      generate_output: restored.outputs?.[0]?.type ?? null,
      save_video_input: saveVideo.inputs?.[0]?.type ?? null,
      save_video_linked: saveVideo.inputs?.[0]?.link != null,
    };
  });

  expect(evidence.ui_contract_version).toBe(3);
  expect(evidence.backend_model_count).toBeGreaterThan(0);
  expect(evidence.selectable_model_count).toBe(evidence.backend_model_count);
  expect(evidence.exact_model_set).toBe(true);
  expect(evidence.restored_model).toBe(evidence.selected_model);
  expect(evidence.generate_output).toBe("VIDEO");
  expect(evidence.save_video_input).toBe("VIDEO");
  expect(evidence.save_video_linked).toBe(true);

  const modelRouteRequests = requests.filter((item) => item.url.endsWith("/openrouter-video/v1/models"));
  const paidSubmits = requests.filter((item) => item.method === "POST" && item.url.includes("/api/v1/videos"));
  const workflowQueues = requests.filter((item) => item.method === "POST" && item.url.endsWith("/prompt"));
  expect(modelRouteRequests).toHaveLength(0);
  expect(paidSubmits).toHaveLength(0);
  expect(workflowQueues).toHaveLength(0);

  console.log(JSON.stringify({ ...evidence, model_route_requests: 0, paid_submits: 0, workflow_queues: 0 }));
});
