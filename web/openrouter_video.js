import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
const EXTENSION = "openrouter-video.capability-driven-ui";
const GENERATE_NODE = "OpenRouterVideoGenerate";
const SELECT_MODEL = "SELECT MODEL";
const AUTO = "AUTO / MODEL DEFAULT";
const UI_CONTRACT_VERSION = 5;
const CONNECTION_ROUTE = "/openrouter-video/v1/connection";
const AUTH_START_ROUTE = "/openrouter-video/v1/auth/start";
const COMPACT_LAYOUT = Object.freeze({ width: 400, row: 20, gap: 4, section: 8, prompt: 42, domInset: 16, inset: 15 });
const SELECT_METHOD = "Select model first";
const METHODS = [
    "T2V", "I2V", "FLF2V", "IR2V", "MI2V", "VR2V", "AR2V", "MMR2V",
    "V2V_EDIT", "V2V_EXTEND",
];
const METHOD_LABELS = {
    T2V: "T2V — Text → Video",
    I2V: "I2V — First Frame → Video",
    FLF2V: "FLF2V — First + Last Frame → Video",
    IR2V: "IR2V — Single Image Reference → Video",
    MI2V: "MI2V — Multiple Image References → Video",
    VR2V: "VR2V — Video Reference → Video",
    AR2V: "AR2V — Audio Reference → Video",
    MMR2V: "MMR2V — Mixed Multimodal References → Video",
    V2V_EDIT: "V2V_EDIT — Source Video → Edited Video",
    V2V_EXTEND: "V2V_EXTEND — Source Video → Extended Video",
};
let capabilityPromise;
let connectionPromise;
const connectionListeners = new Set();

function connectionNodes() {
    return app.graph?._nodes || Object.values(app.graph?.nodes || {});
}

function setConnectionPresentation(state) {
    for (const paint of connectionListeners) paint(state);
    const connected = state?.state === "CONNECTED";
    for (const node of connectionNodes()) {
        if (node?.type !== GENERATE_NODE) continue;
        if (node.__orvConnectionCta) setVisible(node.__orvConnectionCta, !connected);
        if (!connected && node.__orvCapabilityStatus) {
            node.__orvCapabilityStatus.value = "OpenRouter connection required";
            setVisible(node.__orvCapabilityStatus, true);
        }
        node.setDirtyCanvas?.(true, true);
    }
}

async function loadConnection(force = false) {
    if (!connectionPromise || force) {
        connectionPromise = api.fetchApi(CONNECTION_ROUTE, { cache: "no-store" })
            .then(async (response) => {
                if (!response.ok) throw new Error("connection status unavailable");
                return response.json();
            })
            .then((state) => { setConnectionPresentation(state); return state; })
            .catch(() => {
                const state = { state: "DISCONNECTED", source: "NONE" };
                setConnectionPresentation(state);
                return state;
            });
    }
    return connectionPromise;
}

function showConnectionPanel() {
    if (document.getElementById("orv-connection-panel")) return;
    connectionStyles();
    const overlay = document.createElement("dialog");
    overlay.id = "orv-connection-panel";
    overlay.className = "orv-connection orv-dialog";
    overlay.setAttribute("aria-labelledby", "orv-connect-title");
    const panel = document.createElement("div"); panel.className = "orv-stack";
    const title = document.createElement("h2"); title.id = "orv-connect-title"; title.textContent = "Connect OpenRouter";
    const description = document.createElement("p"); description.className = "orv-helper";
    description.textContent = "Sign in with OpenRouter to connect this installation securely.";
    panel.append(title, description);
    const status = document.createElement("div"); status.className = "orv-helper";
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    const key = document.createElement("input");
    key.type = "password"; key.autocomplete = "off"; key.placeholder = "OpenRouter API key";
    key.setAttribute("aria-label", "OpenRouter API key"); key.className = "p-inputtext p-component orv-key";
    const actions = document.createElement("div"); actions.className = "orv-actions";
    const oauth = connectionButton("Sign in with OpenRouter", "primary");
    const save = connectionButton("Connect", "secondary");
    const cancel = connectionButton("Cancel", "text");
    const close = () => { key.value = ""; overlay.close(); overlay.remove(); };
    overlay.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
    cancel.onclick = close;
    save.onclick = async () => {
        const value = key.value;
        if (!value.trim()) { status.textContent = "Paste an OpenRouter API key."; return; }
        save.disabled = true; oauth.disabled = true; status.textContent = "Checking the key with the model catalogue…";
        try {
            const response = await api.fetchApi(CONNECTION_ROUTE, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ api_key: value }),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.message || "OpenRouter rejected the API key.");
            key.value = ""; close(); await loadConnection(true); capabilityPromise = null;
            for (const node of connectionNodes()) if (node?.type === GENERATE_NODE) projectSelectedModel(node, true);
        } catch (error) {
            status.textContent = error?.message || "OpenRouter connection failed.";
            save.disabled = false; oauth.disabled = false;
        }
    };
    oauth.onclick = async () => {
        oauth.disabled = true; save.disabled = true; status.textContent = "Opening OpenRouter sign-in…";
        try {
            const response = await api.fetchApi(AUTH_START_ROUTE, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.message || "OpenRouter sign-in is unavailable.");
            window.open(payload.authorization_url, "openrouter-video-auth", "popup,width=520,height=700");
            status.textContent = "Complete sign-in in the OpenRouter window…";
            let attempts = 0;
            const poll = setInterval(async () => {
                attempts += 1;
                const state = await loadConnection(true);
                if (state.state === "CONNECTED" || attempts >= 120) {
                    clearInterval(poll); oauth.disabled = false; save.disabled = false;
                    if (state.state === "CONNECTED") { close(); capabilityPromise = null; for (const node of connectionNodes()) if (node?.type === GENERATE_NODE) projectSelectedModel(node, true); }
                }
            }, 1000);
        } catch (error) {
            status.textContent = error?.message || "OpenRouter sign-in failed.";
            oauth.disabled = false; save.disabled = false;
        }
    };
    const advanced = document.createElement("details");
    const summary = document.createElement("summary"); summary.textContent = "Use existing API key";
    advanced.append(summary, key, save);
    advanced.className = "orv-advanced";
    actions.append(oauth, cancel); panel.append(actions, status, advanced); overlay.append(panel); document.body.append(overlay); overlay.showModal(); oauth.focus();
}

function connectionStyles() {
    if (document.getElementById("orv-connection-styles")) return;
    const style = document.createElement("style"); style.id = "orv-connection-styles";
    style.textContent = `
.orv-connection{color:var(--fg-color);font:inherit;line-height:1.5;max-width:32rem}
.orv-stack{display:flex;flex-direction:column;gap:12px}.orv-connection h2,.orv-connection p{margin:0}
.orv-connection h2{font-size:1.1rem;font-weight:600}.orv-helper{color:var(--descrip-text);font-size:.875rem}
.orv-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.orv-status{font-size:.875rem}
.orv-button{font:inherit;font-size:.875rem;padding:7px 12px;border-radius:var(--p-border-radius-md,6px);border:1px solid var(--border-color);background:var(--comfy-input-bg);color:var(--input-text);cursor:pointer}
.orv-button[data-variant=primary]{background:var(--p-primary-color,var(--primary-background,var(--fg-color)));color:var(--p-primary-contrast-color,var(--primary-color,var(--bg-color)));border-color:transparent}
.orv-button[data-variant=text],.orv-button[data-variant=danger]{background:transparent;border-color:transparent}
.orv-button[data-variant=danger]{color:var(--p-red-400,var(--error-text))}.orv-button:hover{filter:brightness(1.12)}
.orv-button:focus-visible,.orv-key:focus-visible,.orv-advanced summary:focus-visible{outline:2px solid var(--p-primary-color,var(--fg-color));outline-offset:2px}
.orv-button:disabled{opacity:.5;cursor:wait}.orv-dialog{width:min(420px,calc(100vw - 40px));padding:24px;background:var(--comfy-menu-bg);border:1px solid var(--border-color);border-radius:12px;box-shadow:0 16px 48px #0005}
.orv-dialog::backdrop{background:#0008}.orv-key{display:block;box-sizing:border-box;width:100%;margin:12px 0;padding:9px;background:var(--comfy-input-bg);color:var(--input-text);border:1px solid var(--border-color);border-radius:6px}
.orv-advanced{border-top:1px solid var(--border-color);padding-top:12px}.orv-advanced summary{cursor:pointer;font-size:.875rem;color:var(--descrip-text)}
.orv-badge{display:inline-block;border:1px solid var(--border-color);padding:2px 8px;border-radius:12px;font-size:.75rem;color:var(--descrip-text)}
.orv-about{gap:4px}.orv-about strong{font-weight:600}
`;
    document.head.append(style);
}

function connectionButton(text, variant) {
    const button = document.createElement("button"); button.type = "button";
    button.className = "p-button p-component p-button-sm orv-button";
    button.dataset.variant = variant; button.textContent = text; return button;
}

function connectionLabel(state) {
    if (state?.needs_attention && state?.source !== "ENVIRONMENT") return "Connection needs attention";
    if (state?.state !== "CONNECTED") return "Not connected";
    return state.source === "INTERACTIVE" && !state.persistent ? "Connected for this session" : "Connected ✓";
}

function connectionSettingRenderer() {
    connectionStyles();
    const root = document.createElement("div"); root.className = "orv-connection orv-stack";
    const name = document.createElement("strong"); name.textContent = "OpenRouter";
    const label = document.createElement("div"); label.className = "orv-status"; label.setAttribute("role", "status");
    const helper = document.createElement("div"); helper.className = "orv-helper";
    const actions = document.createElement("div"); actions.className = "orv-actions";
    const connect = connectionButton("Connect OpenRouter", "primary");
    const disconnect = connectionButton("Disconnect", "danger");
    const paint = (state) => {
        label.textContent = connectionLabel(state);
        const managed = state?.source === "ENVIRONMENT";
        helper.textContent = managed ? "Managed by environment" : state?.needs_attention ? "Reconnect to continue." : state?.state !== "CONNECTED" ? "Connect OpenRouter to load available video models." : !state.persistent ? "Reconnect required after ComfyUI restarts" : "";
        helper.className = managed ? "orv-badge" : "orv-helper"; helper.hidden = !helper.textContent;
        disconnect.hidden = managed || (state?.source !== "INTERACTIVE" && !state?.needs_attention);
        connect.hidden = managed;
        connect.textContent = state?.state === "CONNECTED" || state?.needs_attention ? "Reconnect" : "Connect OpenRouter";
        connect.dataset.variant = state?.state === "CONNECTED" ? "secondary" : "primary";
    };
    connectionListeners.add(paint);
    connect.onclick = () => showConnectionPanel();
    disconnect.onclick = async () => {
        disconnect.disabled = true;
        try {
            const response = await api.fetchApi(CONNECTION_ROUTE, { method: "DELETE" });
            await loadConnection(true);
            if (!response.ok) helper.textContent = "Connection needs attention. Reconnect to continue.";
        } finally { disconnect.disabled = false; }
    };
    actions.append(connect, disconnect); root.append(name, label, helper, actions); loadConnection().then(paint); return root;
}

function aboutSettingRenderer() {
    connectionStyles();
    const root = document.createElement("div"); root.className = "orv-connection orv-stack orv-about";
    root.setAttribute("aria-label", "OpenRouter Video 0.1.0-rc.2 by ARENAS®lab");
    const title = document.createElement("strong"); title.textContent = "OpenRouter Video";
    const version = document.createElement("span"); version.textContent = "0.1.0-rc.2";
    const author = document.createElement("span"); author.className = "orv-helper"; author.textContent = "by ARENAS®lab";
    root.append(title, version, author); return root;
}

function widget(node, name) {
    return node.widgets?.find((item) => item.name === name);
}

function createGeometryCombos(node) {
    // A String widget's event handler survives a later `type = "combo"`.
    // Create the correct renderer before callback binding and preserve its
    // named/positional serialization slot and the backend STRING contract.
    for (const name of ["resolution", "aspect_ratio", "size", "duration"]) {
        const previous = widget(node, name);
        if (!previous || previous.type === "combo" || previous.type === "slider") continue;
        if (name === "duration") {
            createDurationSlider(node, previous);
            continue;
        }
        const index = node.widgets.indexOf(previous);
        const replacement = node.addWidget(
            "combo", name, name === "size" && (!previous.value || previous.value === AUTO) ? "" : previous.value || AUTO, previous.callback,
            { ...previous.options, values: [name === "size" ? "" : AUTO] },
        );
        const appended = node.widgets.indexOf(replacement);
        node.widgets.splice(appended, 1);
        node.widgets[index] = replacement;
        if (previous.serializeValue) replacement.serializeValue = previous.serializeValue;
    }
}

function setVisible(item, visible) {
    if (!item) return;
    item.hidden = !visible;
    item.options ||= {};
    Object.assign(item.options, { hidden: !visible });
    item.computeSize = visible ? item.__orvComputeSize : () => [0, -4];
}

function addReadOnlyWidget(node, name, initial) {
    const item = node.addWidget("text", name, initial, null, { multiline: false });
    item.serialize = false;
    item.options = item.options || {};
    item.options.readOnly = true;
    item.options.read_only = true;
    return item;
}

function setMinimumWidgetHeight(item, minimum) {
    if (!item || item.__orvSized) return;
    item.__orvSized = true;
    const original = item.computeSize;
    item.__orvComputeSize = (...args) => {
        const measured = original?.apply(item, args) || [0, 20];
        return [measured[0], Math.max(Number(measured[1]) || 0, minimum)];
    };
    setVisible(item, !item.hidden);
}

function sizePrimaryControls(node) {
    for (const item of node.widgets || []) {
        if (["model", "inference_method", "resolution", "aspect_ratio", "duration", "seed", "generate_audio", "size", "randomize"].includes(item.name)) {
            const section = ["inference_method", "duration"].includes(item.name);
            item.__orvComputeSize = () => [0, COMPACT_LAYOUT.row + (section ? COMPACT_LAYOUT.section - COMPACT_LAYOUT.gap : 0)];
            setVisible(item, !item.hidden);
        }
    }
    const prompt = widget(node, "prompt");
    if (prompt) {
        prompt.__orvComputeSize = () => {
            const minimum = COMPACT_LAYOUT.prompt + COMPACT_LAYOUT.domInset;
            if (node.__orvMeasuringMinimum) return [0, minimum];
            const contentHeight = node.computeSize?.()?.[1] || node.size?.[1] || 0;
            return [0, minimum + Math.max(0, (node.size?.[1] || 0) - contentHeight)];
        };
        setVisible(prompt, !prompt.hidden);
    }
}

function stylePrompt(node) {
    const element = widget(node, "prompt")?.element;
    if (!element?.style) return;
    element.placeholder = "Prompt";
    element.style.background = "#20272a";
    element.style.border = "1px solid #354540";
    element.style.borderRadius = "4px";
    element.style.color = "#e4ece9";
    element.style.fontSize = "12px";
    element.style.padding = "4px 6px";
}

function orderPresentationWidgets(node) {
    // LiteGraph paints widgets in array order. Keep the summary directly below
    // sockets and place advanced-only controls below their disclosure. Saved
    // positional values from the prior order are restored by name on configure.
    const control = (node.widgets || []).find((item) =>
        /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`),
    );
    const leading = [
        node.__orvSummary,
        widget(node, "model"), widget(node, "inference_method"), widget(node, "prompt"),
        widget(node, "resolution"), widget(node, "aspect_ratio"),
        widget(node, "duration"), widget(node, "seed"),
        widget(node, "generate_audio"), node.__orvAdvanced,
        widget(node, "size"), control,
    ].filter(Boolean);
    const used = new Set(leading);
    const ordered = [...leading, ...(node.widgets || []).filter((item) => !used.has(item))];
    if (ordered.some((item, index) => item !== node.widgets[index])) {
        // Keep the array identity: Comfy's widget layer may retain the
        // original array while the node definition is being configured.
        node.widgets.splice(0, node.widgets.length, ...ordered);
        return true;
    }
    return false;
}

function applyPresentation(node) {
    node.color = "#173c33";
    node.bgcolor = "#1b2024";
    node.boxcolor = "#45dca5";
    const labels = {
        model: "Model", inference_method: "Inference Method",
        resolution: "Resolution", aspect_ratio: "Aspect Ratio", duration: "Duration",
        seed: "Seed", generate_audio: "Generate Audio", size: "Exact Size",
    };
    for (const item of node.widgets || []) {
        if (labels[item.name]) item.label = labels[item.name];
    }
    // Preserve the backend-supported -1 sentinel when native Beta inputs blur.
    const seed = widget(node, "seed");
    if (seed?.options) seed.options.min = -1;
    sizePrimaryControls(node);
    installResponsiveHeight(node);
    installBetaPresentation(node);
    stylePrompt(node);
    syncAdvancedControls(node);
    if (node.__orvCapabilityStatus) node.__orvCapabilityStatus.label = " ";
    if (node.__orvPresentationDrawInstalled) return;
    node.__orvPresentationDrawInstalled = true;
    const previousDraw = node.onDrawForeground;
    node.onDrawForeground = function (ctx, ...args) {
        const reordered = orderPresentationWidgets(this);
        const advancedChanged = syncAdvancedControls(this);
        if (reordered || advancedChanged) {
            fitPresentationWidth(this);
        }
        previousDraw?.call(this, ctx, ...args);
        if (this.flags?.collapsed) return;
        const width = this.size?.[0] || 460;
        const badge = String(this.__orvEstimate?.value || "ESTIMATE UNAVAILABLE");
        const available = badge.startsWith("≈ $");
        ctx.save();
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(0.75, -29, width - 1.5, (this.size?.[1] || 0) + 28, 10);
        else ctx.rect(0.75, -29, width - 1.5, (this.size?.[1] || 0) + 28);
        ctx.strokeStyle = "#328761";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.font = "12px sans-serif";
        const badgeWidth = Math.min(230, ctx.measureText(badge).width + 24);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(width - badgeWidth - 10, -27, badgeWidth, 21, 9);
        else ctx.rect(width - badgeWidth - 10, -27, badgeWidth, 21);
        ctx.fillStyle = available ? "#133c30" : "#27302f";
        ctx.strokeStyle = available ? "#45dca5" : "#60706c";
        ctx.fill();
        ctx.stroke();
        ctx.textAlign = "right";
        ctx.fillStyle = available ? "#73e9b8" : "#aeb8b6";
        ctx.fillText(badge, width - 22, -12, badgeWidth - 18);
        ctx.restore();
    };
}

function syncAdvancedControls(node) {
    // Projection finishes here after setting support-specific widget metadata.
    const seed = widget(node, "seed");
    if (seed?.options) seed.options.min = -1;
    setVisible(node.__orvAdvanced, false);
    setVisible(widget(node, "geometry_authority"), false);
    let changed = false;
    for (const item of node.widgets || []) {
        if (/control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`)) {
            item.options ||= {};
            Object.assign(item.options, { advanced: false });
            // Native Beta normally embeds this local control in the Seed row.
            // When Seed is omitted, expose the same public widget independently.
            item.options.canvasOnly = Boolean(seed && !seed.hidden);
            if (item.hidden) { setVisible(item, true); changed = true; }
        }
    }
    for (const item of node.widgets || []) {
        const signature = JSON.stringify(item.options);
        if (item.__orvPresentationOptions === signature) continue;
        item.__orvPresentationOptions = signature;
        // Public label setter invalidates native Beta's cached display projection.
        // Preserve the label and value; never write private renderer stores.
        const label = item.label;
        item.label = `${label ?? item.name} `;
        item.label = label;
    }
    return changed;
}

function installResponsiveHeight(node) {
    if (node.__orvResponsiveHeightInstalled) return;
    node.__orvResponsiveHeightInstalled = true;
    const previousCompute = node.computeSize;
    node.computeSize = function (...args) {
        // Native content sizing measures current sockets and fixed widget rows.
        // Keep that minimum independent of the user's flexible height.
        this.__orvMeasuringMinimum = true;
        try { return previousCompute?.apply(this, args); }
        finally { this.__orvMeasuringMinimum = false; }
    };
    const previousResize = node.onResize;
    node.onResize = function (size, ...args) {
        const minimum = this.computeSize?.()?.[1];
        if (Number.isFinite(minimum)) size[1] = Math.max(size[1], minimum);
        previousResize?.call(this, size, ...args);
    };
}

function fitPresentationWidth(node) {
    const measured = node.computeSize?.();
    if (measured) node.setSize?.([COMPACT_LAYOUT.width, Math.max(node.size?.[1] || 0, measured[1])]);
}

function createEstimateState() {
    let value = "ESTIMATE UNAVAILABLE — SELECT MODEL";
    return Object.defineProperty({}, "value", {
        get: () => value,
        set: (next) => { value = next; scheduleBetaPresentation(); },
    });
}

function scheduleBetaPresentation() {
    if (!installBetaPresentation.nodes || installBetaPresentation.pending) return;
    installBetaPresentation.pending = true;
    queueMicrotask(() => {
        installBetaPresentation.pending = false;
        for (const node of installBetaPresentation.nodes) syncBetaPresentation(node);
    });
}

function installBetaPresentation(node) {
    if (typeof document === "undefined" || typeof MutationObserver === "undefined") return;
    if (!installBetaPresentation.nodes) {
        installBetaPresentation.nodes = new Set();
        // Nodes 2.0 has no public arbitrary-USD header badge slot. Its generic
        // badges are footer content; price_badge converts USD to Comfy credits.
        // This guarded adapter inserts a normal-flow header span, not an overlay.
        const style = document.createElement("style");
        style.textContent = `
            .orv-nodes2 .orv-estimate { flex:0 1 auto; max-width:50%; overflow:hidden;
                text-overflow:ellipsis; white-space:nowrap; border:1px solid #328761;
                border-radius:9px; padding:2px 6px; color:#73e9b8; font-size:12px; }
            .orv-nodes2 .orv-prompt-row { min-height:42px; }
            .orv-nodes2 .orv-prompt-row textarea { min-height:42px; height:100%;
                padding:20px 6px 4px; font-size:12px; overflow:auto; }
        `;
        document.head.append(style);
        installBetaPresentation.observer = new MutationObserver(scheduleBetaPresentation);
        installBetaPresentation.observer.observe(document.body, { childList: true, subtree: true });
    }
    if (!installBetaPresentation.nodes.has(node)) {
        installBetaPresentation.nodes.add(node);
        const previousRemoved = node.onRemoved;
        node.onRemoved = function (...args) {
            installBetaPresentation.nodes.delete(this);
            return previousRemoved?.apply(this, args);
        };
    }
    scheduleBetaPresentation();
}

function syncBetaPresentation(node) {
    const root = [...document.querySelectorAll(".lg-node[data-node-id]")].find(
        (element) => element.dataset.nodeId === String(node.id),
    );
    if (!root) return; // Classic has no Vue node DOM; never touch its canvas.
    root.classList.add("orv-nodes2");
    const header = root.querySelector(".lg-node-header > div");
    if (header) {
        let badge = header.querySelector(".orv-estimate");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "orv-estimate";
            header.append(badge);
        }
        const text = String(node.__orvEstimate?.value || "ESTIMATE UNAVAILABLE");
        if (badge.textContent !== text) badge.textContent = text;
        if (badge.title !== text) badge.title = text;
    }
    const grid = root.querySelector('[data-testid="node-widgets"]');
    if (!grid) return;
    const rows = [...grid.querySelectorAll(':scope > [data-testid="node-widget"]')];
    const templates = rows.map((row) => {
        const textarea = row.querySelector("textarea");
        if (!textarea) return "max-content";
        row.classList.add("orv-prompt-row");
        if (textarea.rows !== 2) textarea.rows = 2;
        return "minmax(42px, 1fr)";
    });
    const template = templates.join(" ");
    if (grid.style.gridTemplateRows !== template) grid.style.gridTemplateRows = template;
    if (grid.style.flex !== "1 1 auto") grid.style.flex = "1 1 auto";
}

function canonicalModel(node) {
    const item = widget(node, "model");
    const value = item?.value;
    return typeof value === "string" && value !== SELECT_MODEL ? value : null;
}

function configureModelPicker(node, projection) {
    const item = widget(node, "model");
    if (!item) return null;
    const models = [...(projection.models || [])].sort((left, right) =>
        String(left.display_name || left.model_id).localeCompare(
            String(right.display_name || right.model_id),
        ),
    );
    const nameCounts = new Map();
    for (const model of models) {
        const name = String(model.display_name || model.model_id);
        nameCounts.set(name, (nameCounts.get(name) || 0) + 1);
    }
    const entries = models.map((model) => {
        const name = String(model.display_name || model.model_id);
        return {
            id: model.model_id,
            label: nameCounts.get(name) > 1 ? `${name} — ${model.model_id}` : name,
        };
    });
    item.__orvIdToLabel = new Map(entries.map((entry) => [entry.id, entry.label]));
    const currentId = canonicalModel(node);
    item.options = item.options || {};
    item.options.values = [SELECT_MODEL, ...entries.map((entry) => entry.id)];
    item.options.getOptionLabel = (value) => item.__orvIdToLabel.get(value) ?? value;
    if (currentId && item.__orvIdToLabel.has(currentId)) {
        item.value = currentId;
    } else {
        item.value = SELECT_MODEL;
    }
    return currentId && !item.__orvIdToLabel.has(currentId) ? currentId : null;
}

function migratePhase8Values(node) {
    const seed = widget(node, "seed");
    if (seed?.value === "") seed.value = -1;
    else if (typeof seed?.value === "string" && /^-?\d+$/.test(seed.value.trim())) {
        seed.value = Number(seed.value);
    }
    const duration = widget(node, "duration");
    if (typeof duration?.value === "string" && /^\d+$/.test(duration.value.trim())) {
        duration.value = Number(duration.value);
    }
}

function restorePhase8RemoteOptionsValues(node, serializedValues) {
    if (
        !Array.isArray(serializedValues) ||
        serializedValues.length < 13 ||
        typeof serializedValues[1] !== "boolean" ||
        serializedValues[2] !== "refresh"
    ) {
        return false;
    }
    // Phase 8 serialized these fields in a different order. Restore by field
    // identity so Phase 10's inserted method and reordered geometry controls
    // cannot turn a saved duration into prompt text or seed into audio state.
    const legacyFields = [
        ["model", 0], ["prompt", 3], ["duration", 4], ["resolution", 5],
        ["aspect_ratio", 6], ["size", 7], ["seed", 8],
        ["generate_audio", 10], ["first_frame_url", 11], ["last_frame_url", 12],
    ];
    for (const [name, index] of legacyFields) {
        const item = widget(node, name);
        if (item && index < serializedValues.length &&
            (name !== "model" || typeof serializedValues[index] === "string")) {
            item.value = serializedValues[index];
        }
    }
    const seedMode = (node.widgets || []).find((item) =>
        /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`),
    );
    if (seedMode && typeof serializedValues[9] === "string") {
        seedMode.value = serializedValues[9];
    }
    return true;
}

function restorePhase9Values(node, serializedValues) {
    if (!Array.isArray(serializedValues) ||
        METHODS.includes(serializedValues[1]) || METHODS.includes(serializedValues[2])) return false;
    const fields = [
        ["model", 0], ["duration", 2], ["resolution", 3], ["aspect_ratio", 4],
        ["size", 5], ["seed", 6], ["generate_audio", 7], ["first_frame_url", 8],
        ["last_frame_url", 9],
    ];
    for (const [name, index] of fields) {
        const item = widget(node, name);
        if (item && index < serializedValues.length) item.value = serializedValues[index];
    }
    const multiline = node.widgets?.find((item) => item.options?.multiline === true);
    if (multiline && serializedValues.length > 1) multiline.value = serializedValues[1];
    return true;
}

function restorePhase10Values(node, serializedValues) {
    if (!Array.isArray(serializedValues)) return false;
    const previousOrder = METHODS.includes(serializedValues[1]);
    const presentationOrder = !previousOrder && METHODS.includes(serializedValues[2]);
    if (!previousOrder && !presentationOrder) return false;
    const fields = previousOrder ? [
        ["model", 0], ["inference_method", 1], ["prompt", 2],
        ["resolution", 3], ["aspect_ratio", 4], ["duration", 5],
        ["size", 6], ["seed", 7], ["generate_audio", 9],
        ["first_frame_url", 10], ["last_frame_url", 11],
    ] : [
        ["model", 1], ["inference_method", 2], ["prompt", 3],
        ["resolution", 4], ["aspect_ratio", 5], ["duration", 6],
        ["seed", 7], ["generate_audio", 8], ["size", 10],
        ["first_frame_url", 12], ["last_frame_url", 13],
    ];
    for (const [name, index] of fields) {
        const item = widget(node, name);
        if (item && index < serializedValues.length) item.value = serializedValues[index];
    }
    const control = (node.widgets || []).find((item) =>
        /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`),
    );
    const controlIndex = previousOrder ? 8 : 11;
    if (control && controlIndex < serializedValues.length) {
        control.value = serializedValues[controlIndex];
    }
    return true;
}

function restorePhase10NamedValues(node, namedValues) {
    if (!namedValues || typeof namedValues !== "object" ||
        !(METHODS.includes(namedValues.inference_method) || namedValues.inference_method === SELECT_METHOD)) return false;
    for (const name of [
        "model", "inference_method", "prompt", "resolution", "aspect_ratio",
        "duration", "size", "seed", "generate_audio", "first_frame_url",
        "last_frame_url", "geometry_authority",
    ]) {
        if (Object.hasOwn(namedValues, name)) {
            const item = widget(node, name);
            if (item) item.value = namedValues[name];
        }
    }
    const control = (node.widgets || []).find((item) =>
        /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`),
    );
    if (control && Object.hasOwn(namedValues, control.name)) {
        control.value = namedValues[control.name];
    }
    return true;
}

function inferLegacyMethodFromNode(node) {
    const first = inputByName(node, "first_frame")?.link != null ||
        normalizedValue(widget(node, "first_frame_url")) !== null;
    const last = inputByName(node, "last_frame")?.link != null ||
        normalizedValue(widget(node, "last_frame_url")) !== null;
    if (first && last) return "FLF2V";
    if (first) return "I2V";
    const connected = directReferenceInputs(node).filter((item) => item.link != null);
    const kinds = connected.map(connectedReferenceKind).filter(Boolean);
    if (kinds.length === 0) return "T2V";
    const distinct = new Set(kinds);
    if (distinct.size > 1) return "MMR2V";
    if (distinct.has("image")) return kinds.length === 1 ? "IR2V" : "MI2V";
    if (distinct.has("video")) return "VR2V";
    if (distinct.has("audio")) return "AR2V";
    return "T2V";
}

async function loadCapabilities(force = false) {
    if (!capabilityPromise || force) {
        capabilityPromise = api.fetchApi("/openrouter-video/v1/ui-capabilities", {
            cache: "no-store",
        }).then(async (response) => {
            if (!response.ok) throw new Error("capability projection unavailable");
            return response.json();
        });
    }
    return capabilityPromise;
}

function normalizedValue(item) {
    if (!item || item.value === "" || item.value === AUTO || item.value === 0
        || (item.name === "resolution" && item.value === "—")) return null;
    return item.value;
}

function disclose(node, message) {
    if (!message) return;
    const status = node.__orvCapabilityStatus;
    const current = String(status.value || "");
    const replacesTransient =
        current === "" ||
        current === "LOADING CAPABILITIES" ||
        current === "SELECT MODEL" ||
        current.startsWith("CATALOGUE ");
    if (replacesTransient) status.value = message;
    else if (!current.split("; ").includes(message)) status.value = `${current}; ${message}`;
    setVisible(status, true);
    node.setDirtyCanvas?.(true, true);
}

function canonicalOptions(axis, values) {
    if (values === null) return null;
    const key = (value) => {
        const text = String(value);
        if (value === AUTO || (axis === "duration" && value === 0)) return [-1, 0, 0, 0, 0, text];
        let match;
        if (axis === "resolution" && (match = /^([0-9]+(?:\.[0-9]+)?)(p|k)$/i.exec(text))) {
            const nominal = Number(match[1]) * (match[2].toLowerCase() === "k" ? 1000 : 1);
            // Nominal class ranking only; never a preset-to-pixel mapping.
            if (Number.isFinite(nominal) && nominal > 0) return [0, nominal, 0, 0, 0, text];
        } else if (["aspect_ratio", "size"].includes(axis)) {
            match = (axis === "size" ? /^([0-9]+)[x×]([0-9]+)$/ : /^([0-9]+):([0-9]+)$/).exec(text);
            if (match) {
                const [width, height] = [Number(match[1]), Number(match[2])];
                const ratio = width / height, area = axis === "size" ? width * height : ratio;
                if (width > 0 && height > 0 && Number.isFinite(area) && Number.isFinite(ratio))
                    return [0, area, ratio, width, height, text];
            }
        } else if (axis === "duration" && /^[0-9]+(?:\.[0-9]+)?$/.test(text)) {
            const seconds = Number(text);
            if (Number.isFinite(seconds) && seconds > 0) return [0, seconds, 0, 0, 0, text];
        }
        return [1, 0, 0, 0, 0, text];
    };
    return [...values].sort((left, right) => {
        const a = key(left), b = key(right);
        for (let i = 0; i < a.length; i++) {
            if (a[i] < b[i]) return -1;
            if (a[i] > b[i]) return 1;
        }
        return 0;
    });
}

function productDefault(axis, values, confirmedDefault) {
    if (!Array.isArray(values) || !values.length) return null;
    if (values.includes(confirmedDefault)) return confirmedDefault;
    if (axis === "resolution") return values.includes("720p") ? "720p" : canonicalOptions(axis, values)[0];
    if (axis === "aspect_ratio") {
        const ratio = value => { const match = /^([0-9]+):([0-9]+)$/.exec(String(value)); return match && Number(match[2]) > 0 ? Number(match[1]) / Number(match[2]) : null; };
        const candidates = canonicalOptions(axis, values).filter(value => ratio(value) !== null);
        return candidates.sort((a, b) => Math.abs(ratio(a) - 16 / 9) - Math.abs(ratio(b) - 16 / 9))[0] ?? values[0];
    }
    if (axis === "duration") return canonicalOptions(axis, values)[0];
    return null;
}

function configureEnum(node, item, supported, label) {
    if (!item) return;
    const current = normalizedValue(item);
    item.type = "combo";
    item.options = item.options || {};
    const optional = item.name === "size";
    if (supported === null) {
        item.options.values = [];
        return;
    }
    item.options.values = canonicalOptions(item.name, optional ? ["", ...supported] : supported);
    if (optional) {
        if (current !== null && !supported.includes(current)) {
            item.value = "";
        } else item.value = current ?? "";
    } else if (!supported.includes(current)) item.value = productDefault(item.name, supported) ?? "";
}

function arithmeticStep(values) {
    if (values.length < 2) return null;
    const step = values[1] - values[0];
    if (step <= 0) return null;
    for (let index = 2; index < values.length; index += 1) {
        if (values[index] - values[index - 1] !== step) return null;
    }
    return step;
}

// UI domain only: finite evidence is never inferred to be continuous.
function durationDomain(evidence) {
    if (Array.isArray(evidence)) {
        const values = canonicalOptions("duration", evidence);
        if (!values.length || values.some(v => typeof v !== "number" || !Number.isFinite(v) || v <= 0)) {
            return { kind: "UNKNOWN" };
        }
        return { kind: "DISCRETE", allowed_values: values, min: values[0], max: values.at(-1) };
    }
    if (!evidence || !Number.isFinite(evidence.min) || !Number.isFinite(evidence.max)
        || evidence.min <= 0 || evidence.max < evidence.min) return { kind: "UNKNOWN" };
    // Reserved structured UI contract. Current projection supplies lists only.
    if (evidence.kind === "STEPPED_RANGE" && Number.isFinite(evidence.step) && evidence.step > 0) {
        const count = (evidence.max - evidence.min) / evidence.step;
        if (Math.abs(count - Math.round(count)) > 1e-8 || count > 10000) return { kind: "UNKNOWN" };
        const precision = evidence.precision ?? 8;
        if (!Number.isInteger(precision) || precision < 0 || precision > 8) return { kind: "UNKNOWN" };
        const values = Array.from({ length: Math.round(count) + 1 }, (_, i) =>
            Number((evidence.min + i * evidence.step).toFixed(precision)));
        if (new Set(values).size !== values.length) return { kind: "UNKNOWN" };
        return { kind: "STEPPED_RANGE", allowed_values: values, min: evidence.min, max: evidence.max, step: evidence.step };
    }
    if (evidence.kind === "CONTINUOUS_RANGE" && evidence.continuous === true
        && Number.isInteger(evidence.precision) && evidence.precision >= 0 && evidence.precision <= 8) {
        return { kind: "CONTINUOUS_RANGE", min: evidence.min, max: evidence.max, precision: evidence.precision };
    }
    return { kind: "UNKNOWN" };
}

function durationAtPosition(domain, position) {
    if (domain.allowed_values) {
        return domain.allowed_values[Math.max(0, Math.min(domain.allowed_values.length - 1, Math.round(position)))];
    }
    if (domain.kind === "CONTINUOUS_RANGE") {
        return Number(Math.max(domain.min, Math.min(domain.max, position)).toFixed(domain.precision));
    }
    return null;
}

function createDurationSlider(node, previous) {
    const index = node.widgets.indexOf(previous);
    const item = node.addWidget("slider", "duration", previous.value ?? 0, null, { min: 0, max: 1, step: 1, precision: 0 });
    let valueOwner = item;
    while (valueOwner && !Object.getOwnPropertyDescriptor(valueOwner, "value")) valueOwner = Object.getPrototypeOf(valueOwner);
    const nativeValue = valueOwner && Object.getOwnPropertyDescriptor(valueOwner, "value");
    let fallbackValue = item.value;
    Object.defineProperty(item, "value", { configurable: true, get() {
        return nativeValue?.get ? nativeValue.get.call(item) : fallbackValue;
    }, set(next) {
        const values = item.__orvDomain?.allowed_values;
        const numeric = Number(next);
        if (values?.length && Number.isFinite(numeric) && !values.includes(numeric)) {
            next = values.reduce((best, value) => Math.abs(value - numeric) < Math.abs(best - numeric) ? value : best, values[0]);
        }
        if (nativeValue?.set) nativeValue.set.call(item, next);
        else fallbackValue = next;
    } });
    const nativeOptions = () => item.__orvDomain?.allowed_values ?
        { ...item.options, min: 0, max: Math.max(1, item.__orvDomain.allowed_values.length - 1), step: 1 } : item.options;
    const nativeDraw = item.drawWidget;
    const nativeClick = item.onClick;
    const nativeDrag = item.onDrag;
    const view = Object.create(item);
    Object.defineProperty(view, "value", { get() {
        const domain = item.__orvDomain;
        return domain?.allowed_values ? Math.max(0, domain.allowed_values.indexOf(Number(item.value))) : Number(item.value);
    } });
    Object.defineProperty(view, "height", { value: COMPACT_LAYOUT.row });
    view.setValue = position => {
        const next = durationAtPosition(item.__orvDomain || { kind: "UNKNOWN" }, position);
        if (next == null) return;
        item.value = next;
        item.callback?.(next);
        node.setDirtyCanvas?.(true, true);
    };
    // Delegate geometry, fill and pointer interaction to the public native slider.
    // Only its display coordinate differs from the product's semantic seconds.
    if (nativeDraw) item.drawWidget = function (ctx, options) {
        view.y = item.y;
        view.options = nativeOptions();
        view.width = item.width;
        view.label = "Duration";
        const text = Number(item.value) > 0 ? `Duration ${item.value}s` : "Duration —";
        const drawContext = new Proxy(ctx, { get(target, key) {
            if (key === "fillText") return (_nativeText, ...args) => target.fillText(text, ...args);
            const value = Reflect.get(target, key, target);
            return typeof value === "function" ? value.bind(target) : value;
        }, set(target, key, value) { target[key] = value; return true; } });
        nativeDraw.call(view, drawContext, options);
    };
    if (nativeClick) item.onClick = event => { view.options = nativeOptions(); view.width = item.width; nativeClick.call(view, event); };
    if (nativeDrag) item.onDrag = event => { view.options = nativeOptions(); view.width = item.width; return nativeDrag.call(view, event); };
    const appended = node.widgets.indexOf(item);
    node.widgets.splice(appended, 1);
    node.widgets[index] = item;
    item.serializeValue = function () { return this.value; };
    item.__orvSelectPosition = position => view.setValue(position);
}

function configureDuration(node, supported) {
    const item = widget(node, "duration");
    if (!item) return;
    node.__orvDurationValues = supported;
    item.options = item.options || {};
    const domain = durationDomain(supported);
    item.__orvDomain = domain;
    item.type = "slider";
    setVisible(item, true);
    const values = domain.allowed_values || [];
    const current = Number(item.value || 0);
    const valid = values.length ? values.includes(current) : domain.kind !== "UNKNOWN" && current >= domain.min && current <= domain.max;
    if (!valid && domain.kind !== "UNKNOWN") item.value = productDefault("duration", values) ?? domain.min;
    item.options.values = values;
    item.options.min = domain.min ?? 0;
    item.options.max = domain.max === domain.min ? domain.max + 1 : domain.max ?? 1;
    item.options.step = values.length ? arithmeticStep(values) ?? 1 : 10 ** -(domain.precision ?? 0);
    item.options.read_only = domain.kind === "UNKNOWN";
    if (domain.kind === "UNKNOWN" && current > 0) disclose(node, "DURATION: saved value is not verified by catalogue");
}

function configurationScope(relation, context) {
    let unknown = false;
    for (const [key, domain] of Object.entries(relation.when || {})) {
        const value = context[key];
        if (value == null) unknown = true;
        else if (key === "reference_kinds") {
            if (!Array.isArray(value) || value.some((v) => !domain.includes(v))) return false;
        } else if (!domain.includes(value)) return false;
    }
    return unknown ? null : true;
}

function configurationStatus(relations, selections, context) {
    let unknown = false;
    for (const relation of relations) {
        const scope = configurationScope(relation, context);
        if (scope === false) continue;
        if (scope === null || relation.conflict ||
            relation.axes.some((axis) => selections[axis] == null)) {
            unknown = true;
            continue;
        }
        const matches = (row) => relation.axes.every((axis) => row[axis].includes(selections[axis]));
        if (relation.forbidden.some(matches)) return "CONFIRMED_INCOMPATIBLE";
        if (relation.allowed.some(matches)) continue;
        if (relation.complete) return "CONFIRMED_INCOMPATIBLE";
        if (relation.allowed.length) unknown = true;
    }
    return unknown ? "UNKNOWN_COMBINATION" : "READY";
}

function configurationOptions(capability, selections, context) {
    const relations = capability.configuration_relations || [];
    const names = {
        resolution: "supported_resolutions", aspect_ratio: "supported_aspect_ratios",
        duration: "supported_durations", size: "supported_sizes",
    };
    const domains = Object.fromEntries(Object.entries(names).map(([axis, key]) =>
        [axis, capability[key] ?? null]));
    const applicable = relations.filter((r) => configurationScope(r, context) !== false);
    for (const axis of Object.keys(names)) {
        if (domains[axis] === null) {
            const confirmed = [...new Set(applicable.flatMap((r) => r.allowed.flatMap((row) => row[axis] || [])))];
            if (confirmed.length) domains[axis] = confirmed;
        }
    }
    const involved = [...new Set(applicable.flatMap((r) => r.axes))].sort();
    const permitsCompletion = (selected) => {
        const missing = involved.filter((axis) => selected[axis] == null);
        if (missing.reduce((n, axis) => n * (domains[axis]?.length || 0), 1) > 100000) return false;
        const visit = (index, current) => {
            if (index === missing.length) return configurationStatus(relations, current, context) === "READY";
            const axis = missing[index];
            return (domains[axis] || []).some((value) => visit(index + 1, { ...current, [axis]: value }));
        };
        return visit(0, selected);
    };
    return {
        options: Object.fromEntries(Object.entries(domains).map(([axis, values]) =>
            [axis, values === null ? null : canonicalOptions(axis, values.filter((value) => permitsCompletion({ ...selections, [axis]: value })))])),
        status: configurationStatus(relations, selections, context),
    };
}

function configureGenerationConfiguration(node, capability) {
    if (!geometryAuthority(node)) {
        const size = normalizedValue(widget(node, "size"));
        const resolution = normalizedValue(widget(node, "resolution"));
        const aspect = normalizedValue(widget(node, "aspect_ratio"));
        const matches = (capability.geometry_profile?.tuples || []).filter(tuple =>
            tuple.confidence === "CONFIRMED" && tuple.size === size &&
            tuple.resolution === resolution && tuple.aspect_ratio === aspect);
        setGeometryAuthority(node, size && (resolution || aspect)
            ? matches.length === 1 ? "EXACT" : "AMBIGUOUS" : size ? "EXACT" : "NORMALIZED");
    }
    const selections = Object.fromEntries(["resolution", "aspect_ratio", "duration", "size"].map(
        (axis) => [axis, normalizedValue(widget(node, axis))]));
    const kinds = selectedReferenceKinds(node);
    const context = {
        geometry_authority: geometryAuthority(node),
        inference_method: widget(node, "inference_method")?.value,
        mode: widget(node, "mode")?.value ?? null,
        generate_audio: Boolean(widget(node, "generate_audio")?.value),
        reference_kinds: kinds === null ? null : [
            ...kinds, ...(inputByName(node, "source_video")?.link != null ? ["video"] : []),
        ],
        reference_count: kinds === null ? null : kinds.length + Number(inputByName(node, "source_video")?.link != null),
        source_video_present: inputByName(node, "source_video")?.link != null,
    };
    const unconstrained = configurationOptions(capability, {}, context);
    const exact = geometryAuthority(node) === "EXACT";
    if (!exact) selections.size = null;
    if (exact) { selections.resolution = null; selections.aspect_ratio = null; }
    const axes = exact ? ["duration"] : ["resolution", "aspect_ratio", "duration"];
    for (const axis of axes) {
        const values = unconstrained.options[axis];
        if (values !== null && !values.includes(selections[axis])) selections[axis] = null;
    }
    if (configurationOptions(capability, selections, context).status === "CONFIRMED_INCOMPATIBLE") {
        for (const axis of axes) selections[axis] = null;
    }
    for (const axis of axes) {
        const options = configurationOptions(capability, selections, context).options[axis];
        if (options !== null && !options.includes(selections[axis])) {
            selections[axis] = productDefault(axis, options);
            const item = widget(node, axis);
            if (item) item.value = selections[axis] ?? (axis === "duration" ? 0 : "");
        }
    }
    const projected = configurationOptions(capability, selections, context);
    const explicitSizeDurationRelation = (capability.configuration_relations || [])
        .some(relation => relation.axes?.includes("size") && relation.axes?.includes("duration"));
    if (node.__orvGeometryEdited !== "size" || explicitSizeDurationRelation) {
        configureDuration(node, projected.options.duration);
    }
    configureGeometry(node, {
        ...capability, supported_resolutions: projected.options.resolution,
        supported_aspect_ratios: projected.options.aspect_ratio,
        supported_sizes: projected.options.size,
    });
    node.__orvConfigurationStatus = projected.status;
    if (projected.status !== "READY") disclose(node, `${projected.status}: select a compatible configuration; Generate blocked`);
    if ((capability.unmapped_upstream_capabilities || []).includes("configuration_constraints")) {
        disclose(node, "UNMAPPED_UPSTREAM_CAPABILITY: configuration constraints require review; Generate blocked");
    }
}

function isDirectReferenceInput(item) {
    return String(item?.name || "").startsWith("direct_references.reference_");
}

function capabilityIntent(node) {
    node.properties ||= {};
    return node.properties.orv_capability_intent ||= { controls: {}, media: [], methods: {} };
}

function referenceShapeValid(topology, kinds) {
    return Array.isArray(kinds) && kinds.length >= topology.min && kinds.length <= topology.max &&
        topology.kind_sets.some(set => new Set(kinds).size === set.length && set.every(kind => kinds.includes(kind))) &&
        !Object.entries(topology.per_kind_max).some(([kind, max]) => kinds.filter(value => value === kind).length > max);
}

function legacyReferenceKinds(input, savedOrigin = null) {
    const link = savedOrigin || app.graph?.links?.[input?.link];
    const origin = link ? app.graph?.getNodeById?.(link.origin_id) : null;
    if ((origin?.type || origin?.comfyClass) !== "OpenRouterVideoReferenceCollection") return null;
    const linked = (origin.inputs || []).filter(item => item.link != null && /(^|\.)reference_\d+$/.test(item.name));
    linked.sort((a, b) => referenceInputSuffix(a) - referenceInputSuffix(b));
    const kinds = linked.map(connectedReferenceKind);
    return kinds.every(Boolean) ? kinds : null;
}

function reprojectReferenceConsumers(origin) {
    for (const node of app.graph?.findNodesByType?.(GENERATE_NODE) || []) {
        const input = inputByName(node, "input_references");
        const active = app.graph?.links?.[input?.link]?.origin_id === origin.id;
        const parked = capabilityIntent(node).media.some(item => item.origin_id === origin.id);
        if (!active && !parked) continue;
        clearTimeout(node.__orvEstimateTimer);
        node.__orvEstimateTimer = setTimeout(() => projectSelectedModel(node), 120);
    }
}

function scopedCapability(capability, method) {
    const profile = capability?.method_profiles?.[method] || { state: "UNKNOWN", controls: {}, topology: {} };
    const fields = { duration: "supported_durations", resolution: "supported_resolutions",
        aspect_ratio: "supported_aspect_ratios", size: "supported_sizes",
        seed: "supports_seed", generate_audio: "generate_audio" };
    const result = { ...capability, __methodProfile: profile,
        configuration_relations: profile.configuration_relations || [],
        max_reference_count: profile.topology?.max ?? 0,
        supported_reference_kinds: profile.topology?.reference_kinds || [] };
    for (const [name, field] of Object.entries(fields)) {
        const control = profile.controls?.[name];
        result[field] = control?.state === "SUPPORTED"
            ? ["seed", "generate_audio"].includes(name) ? true : control.values
            : ["seed", "generate_audio"].includes(name) ? false : [];
    }
    result.geometry_profile = { ...capability?.geometry_profile,
        tuples: (capability?.geometry_profile?.tuples || []).filter(tuple =>
            result.supported_sizes.includes(tuple.size) &&
            (tuple.resolution === null || result.supported_resolutions.includes(tuple.resolution))) };
    return result;
}

function publishSemanticProjection(node) {
    const signature = JSON.stringify({
        widgets: (node.widgets || []).map(item => [item.name, item.hidden, item.type, item.label,
            item.options?.hidden, item.options?.advanced, item.options?.min, item.options?.max, item.options?.values]),
        inputs: (node.inputs || []).map(input => [input.name, input.type, input.label]),
    });
    if (node.__orvPublishedProjection === signature) return;
    node.__orvPublishedProjection = signature;
    // The pinned native manager extracts metadata from shallow-reactive public
    // collections. Nested POJO edits alone do not invalidate that projection.
    // Notify through those collections; retain objects, order, links and values.
    for (const collection of [node.widgets, node.inputs]) {
        if (!collection?.length) continue;
        const last = collection.pop();
        collection.push(last);
    }
}

function reprojectNodeSemantics(node, capability, method) {
    const key = `${capability.model_id}|${method || ""}`;
    const intent = capabilityIntent(node);
    const fields = ["resolution", "aspect_ratio", "duration", "size", "seed", "generate_audio", "geometry_authority"];
    if (node.__orvProjectedKey !== key) {
        if (node.__orvProjectedKey) intent.controls[node.__orvProjectedKey] = Object.fromEntries(fields.map(name => [name, widget(node, name)?.value]));
        const saved = intent.controls[key];
        if (saved) for (const name of fields) { if (widget(node, name)) widget(node, name).value = saved[name]; }
        node.__orvProjectedKey = key;
    }
    const scoped = scopedCapability(capability, method);
    node.__orvCapability = scoped;
    if (!scoped.supported_sizes.length && geometryAuthority(node) === "EXACT") setGeometryAuthority(node, "NORMALIZED");
    configureReferenceTopology(node, scoped, method);
    configureGenerationConfiguration(node, scoped);
    for (const name of ["prompt", "duration", "resolution", "aspect_ratio", "size", "seed", "generate_audio"]) {
        setVisible(widget(node, name), scoped.__methodProfile.controls?.[name]?.state === "SUPPORTED");
    }
    if (scoped.supports_seed) Object.assign(widget(node, "seed").options,
        { min: scoped.__methodProfile.controls.seed.integer_range.min,
            max: scoped.__methodProfile.controls.seed.integer_range.max, step: 1 });
    if (scoped.supports_seed) {
        const seed = widget(node, "seed");
        const value = Number(seed.value);
        const bounds = scoped.__methodProfile.controls.seed.integer_range;
        if (seed.value !== -1 && (!Number.isInteger(value) || value < bounds.min || value > bounds.max)) {
            intent.inactive ||= {};
            intent.inactive[key] ||= {};
            intent.inactive[key].seed = seed.value;
            seed.value = -1;
        }
    }
    setVisible(node.__orvCapabilityStatus, false);
    fitPresentationWidth(node);
    publishSemanticProjection(node);
    return scoped;
}

function parkIncompatibleMedia(node, topology) {
    const intent = capabilityIntent(node);
    let references = 0;
    const fixed = topology.fixed || [];
    const legacy = inputByName(node, "input_references");
    const legacyValid = legacy?.link != null && referenceShapeValid(topology, legacyReferenceKinds(legacy));
    const currentKinds = directReferenceInputs(node).filter(input => input.link != null).map(connectedReferenceKind);
    const invalidFallback = node.__orvMethodFallback && currentKinds.length && !referenceShapeValid(topology, currentKinds);
    for (const input of [...(node.inputs || [])]) {
        const direct = isDirectReferenceInput(input);
        if (!direct && !["first_frame", "last_frame", "source_video", "input_references"].includes(input.name)) continue;
        const kind = connectedReferenceKind(input);
        const allowed = direct ? !legacyValid && !invalidFallback && topology.reference_kinds?.includes(kind) && references < (topology.max || 0)
            : input.name === "input_references" ? legacyValid
            : fixed.includes(input.name) && (kind === null || kind === (input.name === "source_video" ? "video" : "image"));
        if (input.link != null && !allowed) {
            const link = app.graph?.links?.[input.link];
            if (link && !intent.media.some(item => item.name === input.name && item.origin_id === link.origin_id && item.origin_slot === link.origin_slot)) {
                intent.media.push({ name: input.name, kind, type: input.type, origin_id: link.origin_id, origin_slot: link.origin_slot });
            }
            node.removeInput?.(node.inputs.indexOf(input));
        } else if (direct && input.link != null) references += 1;
    }
    for (const saved of [...intent.media]) {
        const direct = String(saved.name).startsWith("direct_references.reference_");
        const allowed = direct ? !invalidFallback && inputByName(node, "input_references")?.link == null && topology.reference_kinds?.includes(saved.kind) && references < (topology.max || 0)
            : saved.name === "input_references" ? references === 0 && referenceShapeValid(topology, legacyReferenceKinds(null, saved))
            : fixed.includes(saved.name) && saved.kind === (saved.name === "source_video" ? "video" : "image");
        const origin = app.graph?.getNodeById?.(saved.origin_id);
        if (!allowed || !origin || inputByName(node, saved.name)?.link != null) continue;
        if (!inputByName(node, saved.name)) node.addInput?.(saved.name, saved.type);
        origin.connect?.(saved.origin_slot, node, node.inputs.indexOf(inputByName(node, saved.name)));
        if (inputByName(node, saved.name)?.link != null) {
            intent.media.splice(intent.media.indexOf(saved), 1);
            if (direct) references += 1;
        }
    }
}

function projectedWidgetValue(node, name) {
    const control = node.__orvCapability?.__methodProfile?.controls?.[name];
    if (control?.state !== "SUPPORTED") return null;
    const value = normalizedValue(widget(node, name));
    return control.values && !control.values.includes(value) ? null : value;
}

function referenceSocketType(topology, connectedKinds) {
    const valid = (topology.reference_kinds || []).filter(kind => {
        const next = [...connectedKinds, kind];
        if (next.length > topology.max || next.filter(value => value === kind).length > (topology.per_kind_max?.[kind] ?? topology.max)) return false;
        return (topology.kind_sets || []).some(set => next.every(value => set.includes(value)) &&
            next.length + set.filter(value => !next.includes(value)).length <= topology.max);
    });
    return [...valid.map(kind => kind.toUpperCase()), "OPENROUTER_VIDEO_INPUT_REFERENCE"].join(",");
}

function directReferenceInputs(node) {
    return (node.inputs || []).filter(isDirectReferenceInput);
}

function referenceInputSuffix(item) {
    const match = String(item?.name || "").match(/reference_(\d+)$/);
    return match ? Number(match[1]) : -1;
}

function inputByName(node, name) {
    return node.inputs?.find((item) => item.name === name);
}

function connectedReferenceKind(input) {
    if (input?.link == null) return null;
    const link = app.graph?.links?.[input.link];
    const origin = link ? app.graph?.getNodeById?.(link.origin_id) : null;
    const outputType = origin?.outputs?.[link?.origin_slot]?.type || link?.type;
    if (outputType === "IMAGE") return "image";
    if (outputType === "VIDEO") return "video";
    if (outputType === "AUDIO") return "audio";
    const type = String(origin?.type || origin?.comfyClass || "");
    if (type.includes("ImageReference")) return "image";
    if (type.includes("VideoReference")) return "video";
    if (type.includes("AudioReference")) return "audio";
    return null;
}

function fixedRolesForMethod(method) {
    if (method === "I2V") return ["first_frame"];
    if (method === "FLF2V") return ["first_frame", "last_frame"];
    if (method === "V2V_EDIT" || method === "V2V_EXTEND") return ["source_video"];
    return [];
}

function methodUsesReferences(method) {
    return ["IR2V", "MI2V", "VR2V", "AR2V", "MMR2V", "V2V_EDIT", "V2V_EXTEND"].includes(method);
}

function referencePrefix(method, input) {
    if (method === "IR2V" || method === "MI2V") return "image";
    if (method === "VR2V") return "video";
    if (method === "AR2V") return "audio";
    return connectedReferenceKind(input) || "reference";
}

function connectedRoles(node) {
    return (node.inputs || [])
        .filter((input) => input.link != null)
        .map((input) =>
            isDirectReferenceInput(input) || input.name === "input_references"
                ? "references"
                : input.name,
        );
}

function switchWouldOrphan(node, method) {
    const allowed = new Set([...fixedRolesForMethod(method)]);
    if (methodUsesReferences(method)) allowed.add("references");
    if (connectedRoles(node).some((role) =>
        ["first_frame", "last_frame", "source_video", "references"].includes(role) &&
        !allowed.has(role),
    )) return true;
    const references = directReferenceInputs(node).filter((input) => input.link != null);
    if (method === "IR2V" && references.length > 1) return true;
    const requiredKind = {
        IR2V: "image", MI2V: "image", VR2V: "video", AR2V: "audio",
    }[method];
    return Boolean(requiredKind) && references.some(
        (input) => connectedReferenceKind(input) !== requiredKind,
    );
}

function ensureFixedInput(node, name) {
    if (!inputByName(node, name)) node.addInput?.(
        name,
        name === "source_video"
            ? "VIDEO,OPENROUTER_VIDEO_INPUT_REFERENCE"
            : "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE",
    );
    const input = inputByName(node, name);
    if (input) {
        input.type = name === "source_video"
            ? "VIDEO,OPENROUTER_VIDEO_INPUT_REFERENCE" : "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE";
        input.label = name;
    }
}

function moveInputToFrontPreservingLinks(node, name) {
    const index = node.inputs?.findIndex((input) => input.name === name) ?? -1;
    if (index <= 0) return;
    const [input] = node.inputs.splice(index, 1);
    node.inputs.unshift(input);
    for (let slot = 0; slot < node.inputs.length; slot += 1) {
        const linkId = node.inputs[slot].link;
        const link = linkId == null ? null : app.graph?.links?.[linkId];
        if (link && link.target_id === node.id) link.target_slot = slot;
    }
}

function removeUnusedFixedInputs(node, keep) {
    const fixed = new Set(["first_frame", "last_frame", "source_video"]);
    const removable = (node.inputs || [])
        .map((input, index) => ({ input, index }))
        .filter(({ input }) => fixed.has(input.name) && !keep.has(input.name) && input.link == null)
        .map(({ index }) => index)
        .sort((left, right) => right - left);
    for (const index of removable) node.removeInput?.(index);
}

function addTrailingReferenceInput(node, current, socketType = "OPENROUTER_VIDEO_INPUT_REFERENCE") {
    if (!node.addInput) return;
    if (current.length === 0) {
        node.addInput(
            "direct_references.reference_0",
            socketType,
        );
        return;
    }
    const last = [...current].sort(
        (left, right) => referenceInputSuffix(left) - referenceInputSuffix(right),
    ).at(-1);
    const suffix = referenceInputSuffix(last) + 1;
    const name = String(last.name).replace(/reference_\d+$/, `reference_${suffix}`);
    node.addInput(name, last.type);
}

function configureReferenceTopology(node, capability, method) {
    const topology = capability.__methodProfile?.topology || { fixed: [], reference_kinds: [], max: 0 };
    parkIncompatibleMedia(node, topology);
    const keepFixed = new Set(topology.fixed || []);
    for (const name of keepFixed) ensureFixedInput(node, name);
    removeUnusedFixedInputs(node, keepFixed);
    for (const name of [...keepFixed].reverse()) moveInputToFrontPreservingLinks(node, name);
    const legacy = inputByName(node, "input_references");
    if (legacy && legacy.link == null) {
        const legacyIndex = node.inputs.indexOf(legacy);
        if (legacyIndex >= 0) node.removeInput?.(legacyIndex);
    }

    const inputs = directReferenceInputs(node);
    const socketType = [...(topology.reference_kinds || []).map(kind => kind.toUpperCase()), "OPENROUTER_VIDEO_INPUT_REFERENCE"].join(",");
    for (const input of inputs) input.type = socketType;
    const linked = inputs.filter((item) => item.link != null);
    const unlinked = inputs.filter((item) => item.link == null);
    const limit = capability.max_reference_count;
    const effectiveLimit = Number.isInteger(limit) && limit >= 0 ? limit : null;
    const sourceCount = inputByName(node, "source_video")?.link != null ? 1 : 0;
    const reservedSourceCount = keepFixed.has("source_video") ? 1 : 0;
    const usesReferences = topology.max > 0;
    const exactOne = method === "IR2V";
    const keepTrailing = usesReferences &&
        legacy?.link == null &&
        (effectiveLimit === null || linked.length + reservedSourceCount < effectiveLimit) &&
        (!exactOne || linked.length === 0);

    if (node.removeInput && unlinked.length > (keepTrailing ? 1 : 0)) {
        const keep = keepTrailing ? unlinked[0] : null;
        const removable = unlinked
            .filter((item) => item !== keep)
            .map((item) => node.inputs.indexOf(item))
            .filter((index) => index >= 0)
            .sort((left, right) => right - left);
        for (const index of removable) node.removeInput(index);
    }
    const afterTrim = directReferenceInputs(node);
    if (keepTrailing && afterTrim.every((item) => item.link != null)) {
        addTrailingReferenceInput(node, afterTrim, socketType);
    }
    const finalInputs = directReferenceInputs(node).sort(
        (left, right) => referenceInputSuffix(left) - referenceInputSuffix(right),
    );
    for (const input of finalInputs) input.type = referenceSocketType(topology,
        finalInputs.filter(other => other !== input && other.link != null).map(connectedReferenceKind).filter(Boolean));
    // Comfy uses slot indexes for canvas hit-testing. Widget-backed inputs are
    // hidden from the socket drawing, so media sockets must lead the actual
    // inputs array as well as the visual order. Otherwise dragging image_1 can
    // select a hidden STRING widget instead of the visible reference socket.
    const fixedNames = [
        ...keepFixed,
        ...["first_frame", "last_frame", "source_video"].filter(
            (name) => !keepFixed.has(name) && inputByName(node, name),
        ),
    ];
    const legacyNames = legacy?.link != null ? ["input_references"] : [];
    const mediaNames = [...fixedNames, ...legacyNames, ...finalInputs.map((item) => item.name)];
    for (const name of mediaNames.reverse()) moveInputToFrontPreservingLinks(node, name);
    for (let index = 0; index < finalInputs.length; index += 1) {
        finalInputs[index].label = `${referencePrefix(method, finalInputs[index])}_${index + 1}`;
    }

    const currentCount = finalInputs.filter((item) => item.link != null).length +
        (legacy?.link != null ? legacyReferenceKinds(legacy)?.length || 0 : 0);
    node.__orvReferenceSummary = usesReferences && effectiveLimit !== null
        ? `${currentCount + sourceCount} connected · ${
            currentCount + sourceCount >= effectiveLimit
                ? "maximum reached"
                : `${effectiveLimit - currentCount - sourceCount} remaining`
        }`
        : "";
    if (node.__orvSummary) {
        node.__orvSummary.value = node.__orvReferenceSummary;
        setVisible(node.__orvSummary, Boolean(node.__orvReferenceSummary));
    }
    const expectedKind = {
        IR2V: "image", MI2V: "image", VR2V: "video", AR2V: "audio",
    }[method];
    const wrongReferenceKind = Boolean(expectedKind) && linked.some(
        (input) => connectedReferenceKind(input) !== expectedKind,
    );
    const wrongFixedKind = ["first_frame", "last_frame", "source_video"].some((name) => {
        const input = inputByName(node, name);
        return input?.link != null && connectedReferenceKind(input) !==
            (name === "source_video" ? "video" : "image");
    });
    node.__orvReferenceInvalid = wrongReferenceKind || wrongFixedKind ||
        (effectiveLimit !== null && currentCount + sourceCount > effectiveLimit);
    if ((wrongReferenceKind || wrongFixedKind) && !node.__orvMethodBlocked) {
        node.__orvCapabilityStatus.value = "INCOMPATIBLE · media kind · links preserved";
        setVisible(node.__orvCapabilityStatus, true);
    }
    if (node.__orvReferenceInvalid) {
        disclose(node, `REFERENCES ${currentCount + sourceCount}/${effectiveLimit}: preserve links; reduce explicitly before Generate`);
    }
}

function methodStatus(capability, method) {
    return capability.inference_method_statuses?.find((item) => item.method === method)?.status;
}

function configureInferenceMethod(node, capability) {
    const item = widget(node, "inference_method");
    if (!item) return null;
    const supported = (capability?.supported_inference_methods || []).filter(method => capability.method_profiles?.[method]?.state === "SUPPORTED");
    const current = METHODS.includes(item.value) ? item.value : null;
    item.options = item.options || {};
    item.options.getOptionLabel = (value) => METHOD_LABELS[value] || value;
    if (!capability) {
        item.disabled = true;
        item.options.values = [SELECT_METHOD];
        item.value = SELECT_METHOD;
        item.label = `Inference Method · ${SELECT_METHOD}`;
        return null;
    }
    item.disabled = supported.length === 0;
    setVisible(item, supported.length > 0);
    item.label = "Inference Method";
    let selected = current;
    node.__orvMethodFallback = Boolean(current && !supported.includes(current));
    const hasConnections = connectedRoles(node).some((role) =>
        ["first_frame", "last_frame", "source_video", "references"].includes(role),
    );
    if (
        !supported.includes(selected) ||
        (
            node.__orvIsNewNode &&
            !node.__orvMethodInitialized &&
            !node.__orvMethodExplicit &&
            !hasConnections
        )
    ) {
        selected = capability.preferred_inference_method || supported[0] || null;
    }
    if (current && !supported.includes(current)) capabilityIntent(node).methods[capability.model_id] = current;
    item.options.values = [...supported];
    item.value = selected || SELECT_METHOD;
    if (selected && methodStatus(capability, selected) !== "READY") {
        node.__orvMethodBlocked = true;
        node.__orvCapabilityStatus.value = `INCOMPATIBLE · ${selected} · links preserved`;
        setVisible(node.__orvCapabilityStatus, true);
    } else {
        node.__orvMethodBlocked = false;
    }
    node.__orvLastMethod = selected;
    if (selected) node.__orvMethodInitialized = true;
    return selected;
}

function bindInferenceMethod(node) {
    const item = widget(node, "inference_method");
    if (!item) return;
    const previous = item.callback;
    item.callback = function (...args) {
        const next = item.value;
        const prior = node.__orvLastMethod;
        if (!node.__orvModelCapability?.supported_inference_methods?.includes(next)) return;
        previous?.apply(this, args);
        node.__orvMethodExplicit = true;
        node.__orvLastMethod = next;
        if (node.__orvModelCapability) reprojectNodeSemantics(node, node.__orvModelCapability, next);
        fitPresentationWidth(node);
    };
}

function geometryAuthority(node) {
    return widget(node, "geometry_authority")?.value || node.__orvGeometryAuthority || "";
}

function setGeometryAuthority(node, authority) {
    node.__orvGeometryAuthority = authority;
    const item = widget(node, "geometry_authority");
    if (item) item.value = authority;
    setVisible(item, false);
}

function orderedGeometryTuples(tuples) {
    const axes = ["resolution", "aspect_ratio", "size"];
    const orders = Object.fromEntries(axes.map(axis => [axis, canonicalOptions(axis,
        [...new Set(tuples.map(tuple => tuple[axis]).filter(value => value !== null))])]));
    return [...tuples].sort((a, b) => {
        for (const axis of axes) {
            const difference = orders[axis].indexOf(a[axis]) - orders[axis].indexOf(b[axis]);
            if (difference) return difference;
        }
        return 0;
    });
}

function configureGeometry(node, capability) {
    const resolution = widget(node, "resolution"), aspect = widget(node, "aspect_ratio"), size = widget(node, "size");
    const old = { resolution: normalizedValue(resolution), aspect_ratio: normalizedValue(aspect), size: normalizedValue(size) };
    const tuples = orderedGeometryTuples((capability.geometry_profile?.tuples || [])
        .filter(tuple => ["CONFIRMED", "SAFE_DERIVED"].includes(tuple.confidence)));
    const confirmed = tuples.filter(tuple => tuple.confidence === "CONFIRMED" && tuple.resolution !== null);
    const modelChanged = node.__orvGeometryModel != null && node.__orvGeometryModel !== canonicalModel(node);
    let authority = geometryAuthority(node);
    if (!authority) {
        if (old.size && (old.resolution || old.aspect_ratio)) {
            const matching = confirmed.filter(tuple => tuple.size === old.size && tuple.resolution === old.resolution && tuple.aspect_ratio === old.aspect_ratio);
            authority = matching.length === 1 ? "EXACT" : "AMBIGUOUS";
        } else authority = old.size ? "EXACT" : "NORMALIZED";
    }
    configureEnum(node, resolution, capability.supported_resolutions, "RESOLUTION");
    configureEnum(node, aspect, capability.supported_aspect_ratios, "ASPECT RATIO");
    if (modelChanged && old.size && Array.isArray(capability.supported_sizes) && !capability.supported_sizes.includes(old.size)) {
        if (size) size.value = authority === "EXACT" ? canonicalOptions("size", capability.supported_sizes)[0] ?? "" : "";
    }
    configureEnum(node, size, capability.supported_sizes, "EXACT SIZE");
    const edited = node.__orvGeometryEdited;
    if (authority === "EXACT" && normalizedValue(size)) {
        const matching = tuples.filter(tuple => tuple.size === normalizedValue(size));
        const full = matching.filter(tuple => tuple.confidence === "CONFIRMED" && tuple.resolution !== null);
        const preferred = full.find(tuple => tuple.resolution === normalizedValue(resolution) && tuple.aspect_ratio === normalizedValue(aspect)) || full[0];
        if (preferred) { if (resolution) resolution.value = preferred.resolution; if (aspect) aspect.value = preferred.aspect_ratio; }
        else {
            const provenAspects = [...new Set(matching.map(tuple => tuple.aspect_ratio).filter(Boolean))];
            if (provenAspects.length === 1 && aspect) aspect.value = provenAspects[0];
            else if (old.aspect_ratio === null && aspect) {
                aspect.value = "";
                aspect.options.values = ["", ...(capability.supported_aspect_ratios || [])];
            }
            if (resolution) {
                resolution.value = "—";
                resolution.options.values = ["—", ...canonicalOptions("resolution", capability.supported_resolutions || [])];
            }
        }
    } else if (authority === "NORMALIZED" && size) {
        let compatible = confirmed.filter(tuple => tuple.resolution === normalizedValue(resolution) && tuple.aspect_ratio === normalizedValue(aspect));
        if (!compatible.length && edited === "resolution") {
            const alternatives = confirmed.filter(tuple => tuple.resolution === normalizedValue(resolution));
            const next = canonicalOptions("aspect_ratio", [...new Set(alternatives.map(tuple => tuple.aspect_ratio))])[0];
            if (next && aspect) aspect.value = next;
        } else if (!compatible.length && edited === "aspect_ratio") {
            const alternatives = confirmed.filter(tuple => tuple.aspect_ratio === normalizedValue(aspect));
            const next = canonicalOptions("resolution", [...new Set(alternatives.map(tuple => tuple.resolution))])[0];
            if (next && resolution) resolution.value = next;
        }
        compatible = confirmed.filter(tuple => tuple.resolution === normalizedValue(resolution) && tuple.aspect_ratio === normalizedValue(aspect));
        const sizes = canonicalOptions("size", [...new Set(compatible.map(tuple => tuple.size))]);
        size.value = sizes.includes(normalizedValue(size)) ? size.value : sizes[0] ?? "";
        size.options.values = ["", ...sizes];
        // Keep all current confirmed sizes selectable as explicit EXACT intent, even
        // when normalized-to-pixel mapping is unknown. No automatic tuple promotion.
        if (!sizes.length && Array.isArray(capability.supported_sizes)) size.options.values = ["", ...canonicalOptions("size", capability.supported_sizes)];
        size.options.__orvProjection = sizes.length ? "CONFIRMED" : "UNKNOWN_RESOLUTION_SIZE_RELATION";
    }
    setVisible(resolution, Boolean(capability.supported_resolutions?.length) ||
        (capability.supported_resolutions === null && Boolean(old.resolution)));
    setVisible(aspect, Boolean(capability.supported_aspect_ratios?.length) ||
        (capability.supported_aspect_ratios === null && Boolean(old.aspect_ratio)));
    if (size) { size.options.advanced = false; setVisible(size, Boolean(capability.supported_sizes?.length) || Boolean(old.size)); }
    node.__orvGeometryAlternative = false;
    setGeometryAuthority(node, authority);
    node.__orvGeometryModel = canonicalModel(node);
    node.__orvGeometryEdited = null;
    if (authority === "AMBIGUOUS") disclose(node, "UNRESOLVED LEGACY GEOMETRY: explicitly edit Resolution, Aspect Ratio or Exact Size; Generate blocked");
}

function selectedReferenceKinds(node) {
    const legacy = inputByName(node, "input_references");
    if (legacy?.link != null) return legacyReferenceKinds(legacy);
    const connected = directReferenceInputs(node).filter((item) => item.link != null);
    const kinds = connected.map(connectedReferenceKind);
    return kinds.some((kind) => kind === null) ? null : kinds;
}

async function refreshEstimate(node) {
    if (geometryAuthority(node) === "AMBIGUOUS") {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
        return;
    }
    const model = canonicalModel(node);
    if (!model) {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — SELECT MODEL";
        return;
    }
    const referenceKinds = selectedReferenceKinds(node);
    if (referenceKinds === null) {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — REFERENCE SHAPE RESOLVES AT EXECUTION";
        return;
    }
    const profile = node.__orvCapability?.__methodProfile;
    const topology = profile?.topology;
    if (profile?.state !== "SUPPORTED" || !topology || !referenceShapeValid(topology, referenceKinds)) {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
        return;
    }
    const payload = {
        model_id: model,
        duration: projectedWidgetValue(node, "duration"),
        resolution: geometryAuthority(node) === "EXACT" ? null : projectedWidgetValue(node, "resolution"),
        aspect_ratio: geometryAuthority(node) === "EXACT" ? null : projectedWidgetValue(node, "aspect_ratio"),
        size: geometryAuthority(node) === "NORMALIZED" ? null : projectedWidgetValue(node, "size"),
        generate_audio: projectedWidgetValue(node, "generate_audio") === true,
        inference_method: widget(node, "inference_method")?.value,
        reference_kinds: referenceKinds,
        reference_count: referenceKinds.length,
        source_video_present: inputByName(node, "source_video")?.link != null,
    };
    try {
        const response = await api.fetchApi("/openrouter-video/v1/cost-estimate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error("estimate unavailable");
        const result = await response.json();
        node.__orvEstimate.value =
            result.availability === "AVAILABLE"
                ? `≈ $${result.estimated_cost_usd} EST.`
                : "ESTIMATE UNAVAILABLE";
    } catch {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
    }
    node.setDirtyCanvas?.(true, true);
}

function bindEstimateRefresh(node) {
    for (const item of node.widgets || []) {
        if (item.name === "COST" || item.name === "Advanced") continue;
        const previous = item.callback;
        item.callback = function (...args) {
            previous?.apply(this, args);
            if (["resolution", "aspect_ratio", "size"].includes(item.name)) {
                node.__orvGeometryEdited = item.name;
                setGeometryAuthority(node, item.name === "size" && normalizedValue(item) ? "EXACT" : "NORMALIZED");
            }
            if (node.__orvCapability && !["model", "inference_method"].includes(item.name)) {
                configureGenerationConfiguration(node, node.__orvCapability);
            }
            if (item.name === "model") {
                projectSelectedModel(node);
                return;
            }
            if (item.name === "duration" && Number(item.value) > 0) {
                configureDuration(node, node.__orvDurationValues);
            }
            clearTimeout(node.__orvEstimateTimer);
            node.__orvEstimateTimer = setTimeout(() => {
                if (["resolution", "aspect_ratio", "size"].includes(item.name)) refreshEstimate(node);
                else projectSelectedModel(node);
            }, 120);
        };
    }
}

function setLifecycleState(nodeId, state) {
    const node = app.graph?.getNodeById?.(nodeId);
    if (
        !node ||
        ![node.comfyClass, node.type].includes(GENERATE_NODE) ||
        !node.__orvCapabilityStatus
    ) return;
    node.__orvCapabilityStatus.value = state;
    setVisible(node.__orvCapabilityStatus, Boolean(state));
    node.setDirtyCanvas?.(true, true);
}

function presentationPhase(detail) {
    const value = Number(detail?.value);
    if (value === 1) return "VALIDATING";
    if (value === 2) return "SUBMITTING";
    if (value === 3 || value === 4) return "GENERATING";
    if (value === 5 || value === 6) return "DOWNLOADING";
    if (value === 7) return "DONE";
    return null;
}

async function projectSelectedModel(node, force = false) {
    orderPresentationWidgets(node);
    node.__orvCapabilityStatus.value = "";
    setVisible(node.__orvCapabilityStatus, false);
    try {
        const connection = await loadConnection(force);
        if (connection.state !== "CONNECTED") {
            setVisible(node.__orvConnectionCta, true);
            node.__orvCapabilityStatus.value = "OpenRouter connection required";
            setVisible(node.__orvCapabilityStatus, true);
            fitPresentationWidth(node);
            return;
        }
        setVisible(node.__orvConnectionCta, false);
        const projection = await loadCapabilities(force);
        if (projection.ui_contract_version !== UI_CONTRACT_VERSION) {
            node.__orvCapabilityStatus.value =
                `FRONTEND/BACKEND CONTRACT MISMATCH: UI ${UI_CONTRACT_VERSION} / BACKEND ${projection.ui_contract_version ?? "UNKNOWN"}`;
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
            return;
        }
        const missingSavedModel = configureModelPicker(node, projection);
        if ((projection.models || []).length === 0) {
            node.__orvCapabilityStatus.value = "CATALOGUE EMPTY — NO SELECTABLE MODELS";
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
            return;
        }
        if (missingSavedModel) {
            node.__orvCapabilityStatus.value =
                `SAVED MODEL NOT IN CURRENT CATALOGUE: ${missingSavedModel} — SELECT MODEL`;
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — SELECT MODEL";
            return;
        }
        const model = canonicalModel(node);
        if (!model) {
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — SELECT MODEL";
            configureInferenceMethod(node, null);
            configureReferenceTopology(node, { max_reference_count: 0 }, "T2V");
            for (const name of [
                "resolution", "aspect_ratio", "duration", "size", "seed",
                "generate_audio", "first_frame_url", "last_frame_url",
            ]) {
                setVisible(widget(node, name), false);
            }
            setVisible(node.__orvAdvanced, false);
            syncAdvancedControls(node);
            fitPresentationWidth(node);
            node.setDirtyCanvas?.(true, true);
            return;
        }
        const capability = projection.models.find((item) => item.model_id === model);
        if (!capability) {
            widget(node, "model").value = SELECT_MODEL;
            disclose(node, "SAVED MODEL IS NOT PRESENT IN CURRENT CATALOGUE");
            return;
        }
        node.__orvCapabilityStatus.value = "";
        setVisible(node.__orvCapabilityStatus, false);
        setVisible(widget(node, "first_frame_url"), false);
        setVisible(widget(node, "last_frame_url"), false);
        node.__orvModelCapability = capability;
        const method = configureInferenceMethod(node, capability);
        reprojectNodeSemantics(node, capability, method);
        await refreshEstimate(node);
    } catch {
        node.__orvCapabilityStatus.value = "ERROR — CAPABILITIES UNAVAILABLE";
        setVisible(node.__orvCapabilityStatus, true);
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
    }
    setVisible(node.__orvAdvanced, false);
    syncAdvancedControls(node);
    fitPresentationWidth(node);
    publishSemanticProjection(node);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: EXTENSION,
    settings: [
        {
            id: "OpenRouter Video.Connection",
            name: "Connection",
            category: ["OpenRouter Video", "Connection"],
            type: connectionSettingRenderer,
            defaultValue: null,
            telemetry: { trackChanges: false },
        },
        {
            id: "OpenRouter Video.About",
            name: "About",
            category: ["OpenRouter Video", "About"],
            type: aboutSettingRenderer,
            defaultValue: null,
            telemetry: { trackChanges: false },
        },
    ],
    setup() {
        loadConnection();
        api.addEventListener("progress", (event) => {
            const detail = event.detail || {};
            const phase = presentationPhase(detail);
            if (phase) setLifecycleState(detail.node, phase);
        });
        api.addEventListener("execution_error", (event) => {
            const detail = event.detail || {};
            setLifecycleState(detail.node_id ?? detail.node, "ERROR");
        });
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name === "OpenRouterVideoReferenceCollection") {
            const previous = nodeType.prototype.onConnectionsChange;
            nodeType.prototype.onConnectionsChange = function (...args) {
                const result = previous?.apply(this, args);
                reprojectReferenceConsumers(this);
                return result;
            };
            return;
        }
        if (nodeData?.name !== GENERATE_NODE) return;
        const previousConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = previousConnectionsChange?.apply(this, args);
            const hasReferences = this.inputs?.some(
                (item) => item.name === "input_references" || isDirectReferenceInput(item),
            );
            if (hasReferences) {
                clearTimeout(this.__orvEstimateTimer);
                this.__orvEstimateTimer = setTimeout(() => {
                    if (this.__orvCapability) {
                        configureReferenceTopology(
                            this,
                            this.__orvCapability,
                            widget(this, "inference_method")?.value,
                        );
                    }
                    projectSelectedModel(this);
                }, 120);
            }
            return result;
        };
        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = previousCreated?.apply(this, args);
            createGeometryCombos(this);
            this.__orvIsNewNode = true;
            // Hidden nonserialized compatibility slot preserves legacy positional order.
            this.__orvAdvanced = this.addWidget("button", "Advanced", "", null);
            this.__orvAdvanced.serialize = false;
            setVisible(this.__orvAdvanced, false);
            this.__orvSummary = addReadOnlyWidget(this, "REFERENCES", "");
            this.__orvSummary.label = " ";
            this.__orvSummary.__orvComputeSize = () => [0, 22];
            this.__orvSummary.draw = (ctx, node, width, y) => {
                ctx.save();
                ctx.font = "12px sans-serif";
                ctx.fillStyle = "#b8c8c4";
                ctx.textAlign = "left";
                ctx.fillText(String(node.__orvReferenceSummary || ""), 12, y + 15, width - 24);
                ctx.restore();
            };
            setVisible(this.__orvSummary, false);
            this.__orvCapabilityStatus = addReadOnlyWidget(this, "STATE", "");
            setVisible(this.__orvCapabilityStatus, false);
            this.__orvConnectionCta = this.addWidget("button", "Connect OpenRouter", "", () => showConnectionPanel());
            this.__orvConnectionCta.serialize = false;
            this.__orvConnectionCta.options ||= {};
            this.__orvConnectionCta.options.primary = true;
            setVisible(this.__orvConnectionCta, false);
            // Estimate is presentation state, never a workflow/body widget.
            this.__orvEstimate = createEstimateState();
            orderPresentationWidgets(this);
            applyPresentation(this);
            migratePhase8Values(this);
            bindEstimateRefresh(this);
            bindInferenceMethod(this);
            setVisible(widget(this, "first_frame_url"), false);
            setVisible(widget(this, "last_frame_url"), false);
            setTimeout(() => projectSelectedModel(this), 0);
            return result;
        };
        const previousConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            this.__orvIsNewNode = false;
            this.__orvMethodExplicit = true;
            const serializedValues = args[0]?.widgets_values;
            const namedValues = args[0]?.widgets_values_named;
            const modelIndex = this.widgets?.findIndex((item) => item.name === "model") ?? -1;
            const previousPhase10Order = METHODS.includes(serializedValues?.[1]);
            const serializedModel = typeof namedValues?.model === "string"
                ? namedValues.model
                : previousPhase10Order
                    ? serializedValues?.[0]
                    : serializedValues?.[modelIndex];
            const persistedMethod = METHODS.includes(namedValues?.inference_method)
                ? namedValues.inference_method
                : METHODS.includes(serializedValues?.[1])
                ? serializedValues[1]
                : METHODS.includes(serializedValues?.[2])
                    ? serializedValues[2]
                : null;
            const configuredModel =
                typeof serializedModel === "string" && serializedModel !== SELECT_MODEL
                    ? serializedModel
                    : widget(this, "model")?.value;
            const result = previousConfigure?.apply(this, args);
            orderPresentationWidgets(this);
            applyPresentation(this);
            const restoredNamed = restorePhase10NamedValues(this, namedValues);
            const restoredRemote = !restoredNamed &&
                restorePhase8RemoteOptionsValues(this, serializedValues);
            const restoredPhase10 = !restoredNamed && !restoredRemote &&
                restorePhase10Values(this, serializedValues);
            const restoredPhase9 = !restoredNamed && !restoredRemote && !restoredPhase10 &&
                restorePhase9Values(this, serializedValues);
            migratePhase8Values(this);
            setTimeout(() => {
                if (configuredModel && configuredModel !== SELECT_MODEL) {
                    widget(this, "model").value = configuredModel;
                }
                const method = persistedMethod ||
                    (restoredRemote || restoredPhase9 ? inferLegacyMethodFromNode(this) : null);
                if (method) {
                    widget(this, "inference_method").value = method;
                    this.__orvLastMethod = method;
                }
                projectSelectedModel(this);
            }, 200);
            return result;
        };
    },
});
