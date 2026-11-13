import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
const EXTENSION = "openrouter-video.capability-driven-ui";
const GENERATE_NODE = "OpenRouterVideoGenerate";
const SELECT_MODEL = "SELECT MODEL";
const AUTO = "AUTO / MODEL DEFAULT";
const UI_CONTRACT_VERSION = 7;
const CONNECTION_ROUTE = "/openrouter-video/v1/connection";
const AUTH_START_ROUTE = "/openrouter-video/v1/auth/start";
const COMPACT_LAYOUT = Object.freeze({ width: 400, row: 20, gap: 4, section: 8, prompt: 42, domInset: 16, inset: 15 });
const SELECT_METHOD = "Select model first";
const METHODS = [
    "T2V", "I2V", "FLF2V", "IR2V", "MI2V", "VR2V", "AR2V", "MMR2V",
    "V2V_EDIT", "V2V_EXTEND", "V2V_UPSCALE", "AVATAR_AUDIO",
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
    V2V_UPSCALE: "Upscale Video",
    AVATAR_AUDIO: "Photo + Audio → Talking Avatar",
};
let capabilityPromise;
let capabilityInFlight;
let capabilityEpoch = 0;
let catalogueRefreshInFlight;
let catalogueRefreshTimer;
let catalogueLifecycleStarted = false;
let catalogueConnected = false;
let catalogueSignature;
const CATALOGUE_REFRESH_MS = 5 * 60 * 1000;
let connectionPromise;
const connectionListeners = new Set();

function connectionNodes() {
    return app.graph?._nodes || Object.values(app.graph?.nodes || {});
}

function setConnectionPresentation(state) {
    for (const paint of connectionListeners) paint(state);
    const connected = state?.state === "CONNECTED";
    if (catalogueConnected && !connected) {
        capabilityEpoch += 1;
        capabilityPromise = null;
        capabilityInFlight = null;
    }
    const newlyConnected = connected && !catalogueConnected;
    catalogueConnected = connected;
    for (const node of connectionNodes()) {
        if (node?.type !== GENERATE_NODE) continue;
        if (node.__orvConnectionCta) setVisible(node.__orvConnectionCta, !connected);
        if (!connected && node.__orvCapabilityStatus) {
            node.__orvCapabilityStatus.value = "OpenRouter connection required";
            setVisible(node.__orvCapabilityStatus, true);
        }
        node.setDirtyCanvas?.(true, true);
    }
    if (newlyConnected && catalogueLifecycleStarted) void refreshCatalogue();
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
        // A missing saved choice remains explicit user intent, including API export.
        item.value = currentId || SELECT_MODEL;
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
    if (capabilityInFlight) return capabilityInFlight;
    if (!capabilityPromise || force) {
        const epoch = capabilityEpoch;
        const request = api.fetchApi("/openrouter-video/v1/ui-capabilities", {
            cache: "no-store",
        }).then(async (response) => {
            if (!response.ok) throw new Error("capability projection unavailable");
            const projection = await response.json();
            if (epoch !== capabilityEpoch) throw new Error("obsolete capability response");
            return projection;
        });
        capabilityPromise = request;
        capabilityInFlight = request;
        request.catch(() => {
            if (capabilityPromise === request) capabilityPromise = null;
        }).finally(() => {
            if (capabilityInFlight === request) capabilityInFlight = null;
        });
    }
    return capabilityPromise;
}

function catalogueActive() {
    return (typeof document === "undefined" || document.visibilityState !== "hidden") &&
        (typeof navigator === "undefined" || navigator.onLine !== false);
}

function scheduleCatalogueRefresh() {
    clearTimeout(catalogueRefreshTimer);
    if (!catalogueLifecycleStarted || !catalogueActive()) return;
    catalogueRefreshTimer = setTimeout(() => {
        void refreshCatalogue().finally(scheduleCatalogueRefresh);
    }, CATALOGUE_REFRESH_MS);
}

function refreshCatalogue() {
    if (catalogueRefreshInFlight) return catalogueRefreshInFlight;
    if (!catalogueActive()) return Promise.resolve();
    const task = (async () => {
        const connection = await loadConnection(true);
        if (connection.state !== "CONNECTED") return;
        const projection = await loadCapabilities(true);
        // Include profiles, not just model IDs or observation timestamps.
        const signature = projection.catalogue_revision ? JSON.stringify({
            revision: projection.catalogue_revision, source_state: projection.source_state,
        }) : JSON.stringify({ models: projection.models,
            unavailable_models: projection.unavailable_models,
            ui_contract_version: projection.ui_contract_version });
        const changed = signature !== catalogueSignature;
        catalogueSignature = signature;
        const nodes = connectionNodes().filter(node => node?.type === GENERATE_NODE);
        await Promise.all(nodes.filter(node => changed || node.__orvCatalogueFailed)
            .map(node => projectSelectedModel(node, false, projection)));
    })().catch(() => {
        for (const node of connectionNodes()) {
            if (node?.type !== GENERATE_NODE || !node.__orvCapabilityStatus) continue;
            node.__orvCatalogueFailed = true;
            node.__orvCapabilityStatus.value = "CATALOGUE UNAVAILABLE — retrying; saved settings preserved";
            setVisible(node.__orvCapabilityStatus, true);
            node.setDirtyCanvas?.(true, true);
        }
    });
    catalogueRefreshInFlight = task;
    task.finally(() => { if (catalogueRefreshInFlight === task) catalogueRefreshInFlight = null; });
    return task;
}

function startCatalogueLifecycle() {
    if (catalogueLifecycleStarted) return;
    catalogueLifecycleStarted = true;
    const resume = () => {
        if (catalogueActive()) void refreshCatalogue();
        scheduleCatalogueRefresh();
    };
    if (typeof document !== "undefined") document.addEventListener?.("visibilitychange", resume);
    if (typeof window !== "undefined") {
        window.addEventListener?.("online", resume);
        window.addEventListener?.("offline", scheduleCatalogueRefresh);
    }
    resume();
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
        if (value === AUTO || (axis === "duration" && (value === 0 || value === -1))) return [-1, 0, 0, 0, 0, text];
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
        if (!values.length || values.some(v => typeof v !== "number" || !Number.isFinite(v) || (v <= 0 && v !== -1))) {
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

function durationValueAllowed(domain, value) {
    if (domain.allowed_values) return domain.allowed_values.includes(value);
    return domain.kind !== "UNKNOWN" && value >= domain.min && value <= domain.max;
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
        const text = Number(item.value) === -1 ? "Duration Auto" : Number(item.value) > 0 ? `Duration ${item.value}s` : "Duration —";
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
    const valid = durationValueAllowed(domain, current);
    if (!valid && domain.kind !== "UNKNOWN") item.value = productDefault("duration", values.filter(value => value > 0)) ?? domain.min;
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
        let value = context[key];
        if (value == null && key.startsWith("reference_count_") && Array.isArray(context.reference_kinds) && context.reference_kinds.every(v => typeof v === "string")) {
            value = context.reference_kinds.filter(v => v === key.slice("reference_count_".length)).length;
        }
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

function applyTransportInputConstraints(topology, sourcePresent) {
    const projected = { ...topology,
        per_kind_min: { ...(topology?.per_kind_min || {}) },
        per_kind_max: { ...(topology?.per_kind_max || {}) },
        required_kinds: [...(topology?.required_kinds || [])],
        mutually_exclusive: [...(topology?.mutually_exclusive || [])],
    };
    const consumesSource = Boolean(sourcePresent && (topology?.fixed || []).includes("source_video"));
    let sourceOverflow = false;
    const intersectMaximum = (current, transportMaximum, kind = null) => {
        if (!Number.isInteger(transportMaximum) || transportMaximum < 0) return current;
        let available = transportMaximum - (consumesSource && kind === "video" ? 1 : 0);
        if (kind === null && consumesSource) available -= 1;
        if (available < 0) { sourceOverflow = true; available = 0; }
        return Number.isInteger(current) && current >= 0 ? Math.min(current, available) : available;
    };
    if (Number.isInteger(topology?.transport_max)) {
        projected.max = intersectMaximum(topology.max, topology.transport_max);
    }
    if (Number.isInteger(topology?.transport_min) && topology.transport_min >= 0) {
        const available = Math.max(0, topology.transport_min - (consumesSource ? 1 : 0));
        projected.min = Math.max(Number.isInteger(topology.min) ? topology.min : 0, available);
    }
    for (const [kind, maximum] of Object.entries(topology?.transport_per_kind_max || {})) {
        projected.per_kind_max[kind] = intersectMaximum(projected.per_kind_max[kind], maximum, kind);
    }
    for (const [kind, minimum] of Object.entries(topology?.transport_per_kind_min || {})) {
        if (!Number.isInteger(minimum) || minimum < 0) continue;
        const available = Math.max(0, minimum - (consumesSource && kind === "video" ? 1 : 0));
        projected.per_kind_min[kind] = Math.max(projected.per_kind_min[kind] || 0, available);
    }
    const transportRequired = topology?.transport_required_kinds || [];
    projected.required_kinds = [...new Set([...projected.required_kinds,
        ...transportRequired.filter(kind => !(consumesSource && kind === "video"))])];
    for (const group of topology?.transport_mutually_exclusive || []) {
        if (consumesSource && group.includes("video")) {
            for (const kind of group.filter(item => item !== "video")) {
                projected.per_kind_max[kind] = Number.isInteger(projected.per_kind_max[kind])
                    ? Math.min(projected.per_kind_max[kind], 0) : 0;
            }
        } else projected.mutually_exclusive.push(group);
    }
    projected.transport_source_overflow = sourceOverflow;
    return projected;
}

function referenceShapeValid(topology, kinds) {
    if (!topology || !Array.isArray(kinds) || !Array.isArray(topology.kind_sets) ||
        topology.constraint_state === "UNKNOWN" || topology.constraint_state === "CONFLICT" ||
        topology.transport_source_overflow) return false;
    const counts = kinds.reduce((result, kind) => ({ ...result, [kind]: (result[kind] || 0) + 1 }), {});
    const maximum = Number.isInteger(topology.max) && topology.max >= 0 ? topology.max : null;
    if (kinds.length < (topology.min ?? 0) || (maximum !== null && kinds.length > maximum)) return false;
    if (!topology.kind_sets.some(set => kinds.every(kind => set.includes(kind)) && set.every(kind => counts[kind]))) return false;
    if (Object.entries(topology.per_kind_max || {}).some(([kind, max]) => counts[kind] > max)) return false;
    if (Object.entries(topology.per_kind_min || {}).some(([kind, min]) => (counts[kind] || 0) < min)) return false;
    if ((topology.required_kinds || []).some(kind => !counts[kind])) return false;
    if ((topology.mutually_exclusive || []).some(group => group.filter(kind => counts[kind]).length > 1)) return false;
    if (topology.execution_domain === "UNVERIFIED" && kinds.length) return false;
    if (topology.execution_domain === "VERIFIED_CONFIGURATIONS") {
        return (topology.verified_configurations || []).some(configuration =>
            Object.keys(configuration).every(kind => topology.reference_kinds.includes(kind)) &&
            topology.reference_kinds.every(kind => (counts[kind] || 0) === (configuration[kind] || 0)));
    }
    return true;
}

function referencePartialAllowed(topology, kinds) {
    if (!topology || topology.constraint_state === "UNKNOWN" || topology.constraint_state === "CONFLICT" ||
        topology.transport_source_overflow) return false;
    const counts = kinds.reduce((result, kind) => ({ ...result, [kind]: (result[kind] || 0) + 1 }), {});
    const maximum = Number.isInteger(topology.max) && topology.max >= 0 ? topology.max : null;
    if (maximum !== null && kinds.length > maximum) return false;
    if (Object.entries(topology.per_kind_max || {}).some(([kind, max]) => (counts[kind] || 0) > max)) return false;
    if ((topology.mutually_exclusive || []).some(group => group.filter(kind => counts[kind]).length > 1)) return false;
    if (topology.execution_domain === "UNVERIFIED") return referenceShapeValid(topology, kinds);
    if (topology.execution_domain === "VERIFIED_CONFIGURATIONS") {
        const configurations = topology.verified_configurations || [];
        const fitsConfiguration = configurations.some(configuration =>
            Object.keys(configuration).every(kind => topology.reference_kinds?.includes(kind)) &&
            topology.reference_kinds?.every(kind => (counts[kind] || 0) <= (configuration[kind] || 0)));
        if (!fitsConfiguration) return false;
    }
    if (referenceShapeValid(topology, kinds)) return true;
    if (maximum !== null && kinds.length >= maximum) return false;
    return (topology.kind_sets || []).some(set => {
        if (!kinds.every(kind => set.includes(kind))) return false;
        const needed = new Set([...set.filter(kind => !counts[kind]), ...(topology.required_kinds || []),
            ...Object.entries(topology.per_kind_min || {}).filter(([kind, min]) => (counts[kind] || 0) < min).map(([kind]) => kind)]);
        if ([...needed].some(kind => !set.includes(kind) ||
            (topology.per_kind_max?.[kind] ?? maximum) !== null &&
            (counts[kind] || 0) >= (topology.per_kind_max?.[kind] ?? maximum))) return false;
        const requiredAdditions = [...needed].reduce((sum, kind) => sum + Math.max(1,
            (topology.per_kind_min?.[kind] || 0) - (counts[kind] || 0)), 0);
        const minimumAdditions = Math.max(requiredAdditions, (topology.min ?? 0) - kinds.length, 0);
        return maximum === null || kinds.length + minimumAdditions <= maximum;
    });
}

function legacyReferenceKinds(input, savedOrigin = null, graph = mediaInputGraphs.get(input) || app.graph) {
    const link = savedOrigin || mediaLink(graph, input?.link);
    const origin = link ? graph?.getNodeById?.(link.origin_id) : null;
    if ((origin?.type || origin?.comfyClass) !== "OpenRouterVideoReferenceCollection") return null;
    const linked = (origin.inputs || []).filter(item => item.link != null && /(^|\.)reference_\d+$/.test(item.name));
    linked.sort((a, b) => referenceInputSuffix(a) - referenceInputSuffix(b));
    for (const item of linked) mediaInputGraphs.set(item, graph);
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
        max_reference_count: profile.topology?.max ?? null,
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

function providerOptionLeaves(spec, path = [], values = [], counts = {}) {
    if (spec?.type === "array") {
        const count = counts[JSON.stringify(path)] ?? Math.max(0, ...values.filter(v =>
            path.every((key,index) => v.path?.[index] === key) && Number.isInteger(v.path?.[path.length]))
            .map(v => v.path[path.length] + 1));
        return Array.from({length:Math.min(count,spec.max_items)}, (_,index) =>
            providerOptionLeaves(spec.items,[...path,index],values,counts)).flat();
    }
    if (spec?.type !== "object") return [{path, spec}];
    const variants = spec.variants;
    const selected = variants && values.find(v => JSON.stringify(v.path || []) === JSON.stringify([...path, variants.discriminator_field]))?.value;
    const variant = variants?.cases?.[selected];
    return Object.entries(spec.fields || {}).flatMap(([key, child]) => {
        if (variants && key !== variants.discriminator_field &&
            (!variant || variant.forbidden_fields?.includes(key) ||
             (variant.allowed_fields && !variant.allowed_fields.includes(key)))) return [];
        const narrowed = {...child, required:Boolean(child.required || spec.required_fields?.includes(key) || variant?.required_fields?.includes(key)),
            ...(variant?.field_values?.[key] ? {values:variant.field_values[key]} : {})};
        return providerOptionLeaves(narrowed, [...path, key], values, counts);
    });
}

function providerOptionLeaf(spec, path = []) {
    if (!Array.isArray(path)) return null;
    for (const key of path) {
        if (spec?.type === "array" && Number.isInteger(key) && key >= 0 && key < spec.max_items) {
            spec = spec.items;
            continue;
        }
        if (spec?.type !== "object" || !Object.hasOwn(spec.fields || {}, key)) return null;
        spec = spec.fields[key];
    }
    return !["object","array"].includes(spec?.type) ? spec : null;
}

function providerObjectIssue(spec, values, path = []) {
    const descendants = values.filter(v => path.every((key, index) => v.path?.[index] === key));
    if (spec.type === "array") {
        if (!descendants.length) return "";
        const count = Math.max(...descendants.map(v=>v.path[path.length]))+1;
        if (count < spec.min_items || count > spec.max_items) return "Provider array count is outside the supported range.";
        for (let index=0;index<count;index++) {
            const child=descendants.filter(v=>v.path[path.length]===index);
            if (!child.length) return "Complete each provider array item before Generate.";
            const issue=providerObjectIssue(spec.items,child,[...path,index]);
            if (issue) return issue;
        }
        return "";
    }
    if (spec.type !== "object") return spec.required && !descendants.some(v =>
        JSON.stringify(v.path || []) === JSON.stringify(path) && (typeof v.value !== "string" || v.value.trim()))
        ? `Required provider control: ${path.join(" · ") || "value"}.` : "";
    if (!descendants.length) return "";
    const present = key => descendants.some(v => v.path?.[path.length] === key &&
        (typeof v.value !== "string" || v.value.trim()));
    const discriminator = spec.variants?.discriminator_field;
    const selected = discriminator && descendants.find(v => JSON.stringify(v.path) === JSON.stringify([...path,discriminator]))?.value;
    const variant = spec.variants?.cases?.[selected];
    for (const key of [...(spec.required_fields || []), ...(variant?.required_fields || [])])
        if (!present(key)) return `Required provider control: ${[...path,key].join(" · ")}.`;
    for (const group of [...(spec.one_of_required || []), ...(variant?.one_of_required || [])])
        if (group.filter(present).length !== 1) return `Choose exactly one provider control: ${group.join(" / ")}.`;
    for (const [key, child] of Object.entries(spec.fields || {})) {
        const issue = providerObjectIssue(child, descendants, [...path,key]);
        if (issue) return issue;
    }
    return "";
}

function configureOperationControls(node, profile) {
    node.__orvProviderProfile = profile;
    const controls = profile.controls || {};
    for (const name of ["previous_job_id", "upscale_factor", "creativity"]) {
        let item = widget(node, name);
        const control = controls[name];
        if (!item) continue;
        const supported = control?.state === "SUPPORTED";
        if (supported && name === "upscale_factor" && item.type !== "number") {
            const index = node.widgets.indexOf(item), previous = item;
            item = node.addWidget("number", name, Number(previous.value) || control.number_range?.min,
                previous.callback, { ...previous.options, precision: 2, step: 0.1 });
            node.widgets.splice(node.widgets.indexOf(item), 1);
            node.widgets[index] = item;
            item.serializeValue = () => String(item.value ?? "");
        }
        if (supported && name === "upscale_factor") {
            Object.assign(item.options ||= {}, { min: control.number_range.min, max: control.number_range.max });
        }
        if (supported && name === "creativity") {
            item.type = "combo";
            (item.options ||= {}).values = [...control.values];
            if (!control.values.includes(item.value)) item.value = control.values[0];
        }
        item.label = {previous_job_id:"Previous Job ID", upscale_factor:"Upscale Factor", creativity:"Creativity"}[name];
        setVisible(item, supported);
    }
    const storage = widget(node, "provider_options");
    setVisible(storage, false);
    if (!storage || !node.addWidget) return;
    for (const item of node.widgets || []) if (item.__orvProviderOption) setVisible(item, false);
    let saved;
    try { saved = storage.value ? JSON.parse(storage.value) : []; }
    catch { saved = null; }
    if (!Array.isArray(saved) || saved.some(v => !v || typeof v !== "object")) return "Invalid saved provider controls; repair before Generate.";
    const providers = controls.provider_options?.state === "SUPPORTED" ? controls.provider_options.providers || {} : {};
    const activeLeaf = v => providerOptionLeaves(providers[v.provider]?.[v.key], [], saved.filter(other =>
        other.provider === v.provider && other.key === v.key && (other.container || null) === (v.container || null)))
        .find(leaf => JSON.stringify(leaf.path) === JSON.stringify(v.path || []))?.spec;
    let issue = saved.some(v => !providerOptionLeaf(providers[v.provider]?.[v.key], v.path || []) ||
        !activeLeaf(v) || (activeLeaf(v).values && !activeLeaf(v).values.includes(v.value)) ||
        (providers[v.provider][v.key].container || null) !== (v.container || null))
        ? "Saved provider controls are no longer supported; choose an explicit replacement." : "";
    for (const [provider, options] of Object.entries(providers)) for (const [key, spec] of Object.entries(options)) {
        const problem = providerObjectIssue(spec, saved.filter(v => v.provider === provider && v.key === key));
        if (!issue && problem) issue = `${key}: ${problem}`;
        if(saved.some(v=>v.provider===provider&&v.key===key)) for(const [dependency,domain] of Object.entries(spec.requires || {})) {
            const selected=saved.find(v=>v.provider===provider&&v.key===dependency)?.value ?? options[dependency]?.omitted_default;
            if(!domain.includes(selected)&&!issue)issue=`${key}: requires compatible ${dependency}.`;
        }
    }
    for (const [provider, options] of Object.entries(providers)) for (const [key, root] of Object.entries(options)) {
        const values=saved.filter(v=>v.provider===provider&&v.key===key), counts={};
        if (root.type === "array") {
            const name=`provider_option:${provider}:${root.container || ""}:${key}:count`;
            let count=widget(node,name);
            const storedCount=Math.max(0,...values.map(v=>Number(v.path?.[0])+1));
            if (!count) {
                count=node.addWidget("combo",name,storedCount,value=>{
                    count.value=Number(value);
                    let entries;try {entries=storage.value?JSON.parse(storage.value):[];}catch{return;}
                    storage.value=JSON.stringify(entries.filter(v=>v.provider!==provider||v.key!==key||v.path?.[0]<count.value));
                    const problem=configureOperationControls(node,node.__orvProviderProfile);
                    if(node.__orvCapabilityStatus)node.__orvCapabilityStatus.value=problem || "";
                    setVisible(node.__orvCapabilityStatus,Boolean(problem));
                    publishSemanticProjection(node);node.setDirtyCanvas?.(true,true);
                },{values:Array.from({length:root.max_items+1},(_,i)=>i)});
                count.__orvProviderOption=true;count.serialize=false;
            }
            count.label=`${key} · count`;
            count.value=Math.max(Number(count.value)||0,storedCount);
            if(count.value>storedCount&&!issue)issue=`${key}: Complete each provider array item before Generate.`;
            counts['[]']=count.value;setVisible(count,true);
        }
        for (const leaf of providerOptionLeaves(root, [], values, counts)) {
        const path = leaf.path, spec = {...leaf.spec, container:root.container};
        if (spec.values?.length === 1 && (spec.default !== undefined || spec.omitted_default === spec.values[0])) continue;
        const defaultLabel = "AUTO / PROVIDER DEFAULT";
        const boolean = spec.type === "boolean";
        const enabled=Object.entries(root.requires || {}).every(([dependency,domain])=>domain.includes(
            saved.find(v=>v.provider===provider&&v.key===dependency)?.value ?? options[dependency]?.omitted_default));
        const choices = !enabled ? [defaultLabel] : boolean ? [defaultLabel, "true", "false"]
            : spec.values ? [defaultLabel, ...spec.values] : undefined;
        const numeric = !choices && ["integer", "number"].includes(spec.type);
        const name = `provider_option:${provider}:${spec.container || ""}:${key}${path.length ? ":" + path.join(":") : ""}`;
        const matches = v => v.provider === provider && v.key === key &&
            (v.container || null) === (spec.container || null) && JSON.stringify(v.path || []) === JSON.stringify(path);
        const old = saved.find(matches);
        let item = widget(node, name);
        if (!item) {
            const type = choices ? "combo" : ["integer", "number"].includes(spec.type) ? "number" : "text";
            item = node.addWidget(type, name, old?.value ?? "", value => {
                if (numeric && value !== defaultLabel && widget(node, name + ":override")?.value !== "SET") return;
                let values;
                try { values = storage.value ? JSON.parse(storage.value) : []; } catch { return; }
                if (!Array.isArray(values)) return;
                const remaining = values.filter(v => !matches(v));
                if (value !== "" && value !== defaultLabel) remaining.push({provider, key,
                    value: boolean ? value === "true" : value, ...(spec.container ? {container:spec.container} : {}),
                    ...(path.length ? {path} : {})});
                storage.value = JSON.stringify(remaining);
                const issue = configureOperationControls(node, node.__orvProviderProfile);
                if (node.__orvCapabilityStatus) node.__orvCapabilityStatus.value = issue || "";
                setVisible(node.__orvCapabilityStatus, Boolean(issue));
                publishSemanticProjection(node);
                node.setDirtyCanvas?.(true, true);
                void refreshEstimate(node);
            }, {values:choices, min:spec.min, max:spec.max, step:spec.type === "integer" ? 1 : undefined});
            item.__orvProviderOption = true;
            item.serialize = false;
        }
        item.label = [key, ...path].join(" · ") + (spec.required ? " (required)" : "");
        Object.assign(item.options ||= {}, {min:spec.min, max:spec.max});
        item.options.tooltip=[spec.max_length == null ? "" : `Maximum ${spec.max_length} characters`,
            ...Object.entries(root.requires || {}).map(([key,domain])=>`Requires ${key}: ${domain.join(" / ")}`)].filter(Boolean).join("; ");
        if (choices) (item.options ||= {}).values = choices;
        item.value = old ? boolean ? String(old.value) : old.value : choices ? defaultLabel : numeric ? spec.omitted_default ?? spec.min ?? 0 : "";
        let mode = widget(node, name + ":override");
        if (numeric && !mode) {
            mode = node.addWidget("combo", name + ":override", old ? "SET" : defaultLabel, value => {
                mode.value = value;
                item.callback(value === "SET" ? item.value : defaultLabel);
                setVisible(item, value === "SET");
                publishSemanticProjection(node);
                node.setDirtyCanvas?.(true, true);
            }, {values:[defaultLabel, "SET"]});
            mode.__orvProviderOption = true;
            mode.serialize = false;
        }
        if (mode) {
            mode.label = item.label;
            mode.value = old ? "SET" : defaultLabel;
            setVisible(mode, numeric);
        }
        setVisible(item, !numeric || Boolean(old));
        }
    }
    const geometry=new Set(),omitted=new Set();
    for(const [provider,options]of Object.entries(providers))for(const [key,spec]of Object.entries(options)){
        for(const name of spec.omits_controls || [])geometry.add(name);
        const selected=saved.find(v=>v.provider===provider&&v.key===key);
        if(selected&&(!spec.omit_when||spec.omit_when.includes(selected.value)))for(const name of spec.omits_controls || [])omitted.add(name);
    }
    for(const name of geometry)setVisible(widget(node,name),!omitted.has(name)&&controls[name]?.state==='SUPPORTED');
    return issue;
}

function reprojectNodeSemantics(node, capability, method, transition = {}) {
    const key = `${capability.model_id}|${method || ""}`;
    const intent = capabilityIntent(node);
    const fields = ["resolution", "aspect_ratio", "duration", "size", "seed", "generate_audio", "geometry_authority", "previous_job_id", "upscale_factor", "creativity", "provider_options"];
    if (node.__orvProjectedKey !== key) {
        if (node.__orvProjectedKey) intent.controls[node.__orvProjectedKey] = Object.fromEntries(fields.map(name => [name, widget(node, name)?.value]));
        const saved = intent.controls[key];
        if (saved) for (const name of fields) { if (widget(node, name)) widget(node, name).value = saved[name]; }
        else if (node.__orvProjectedKey) {
            for (const name of ["provider_options", "previous_job_id"]) if (widget(node, name)) widget(node, name).value = "";
        }
        node.__orvProjectedKey = key;
    }
    const scoped = scopedCapability(capability, method);
    node.__orvCapability = scoped;
    if (!scoped.supported_sizes.length && geometryAuthority(node) === "EXACT") setGeometryAuthority(node, "NORMALIZED");
    configureReferenceTopology(node, scoped, method, transition);
    configureGenerationConfiguration(node, scoped);
    for (const name of ["prompt", "duration", "resolution", "aspect_ratio", "size", "seed", "generate_audio"]) {
        setVisible(widget(node, name), scoped.__methodProfile.controls?.[name]?.state === "SUPPORTED");
    }
    const prompt = widget(node, "prompt"), promptSpec = scoped.__methodProfile.controls?.prompt;
    if (prompt) {
        prompt.label = promptSpec?.required === false ? "Prompt (optional)" : "Prompt";
        const bounds = [promptSpec?.min_length == null ? "" : `minimum ${promptSpec.min_length} characters`,
            promptSpec?.max_length == null ? "" : `maximum ${promptSpec.max_length} characters`].filter(Boolean);
        (prompt.options ||= {}).tooltip = bounds.join("; ");
        // Communicate reviewed constraints without truncating saved user text.
        if (prompt.element) prompt.element.title = bounds.join("; ");
    }
    if (scoped.supports_seed) {
        const seed = widget(node, "seed");
        const bounds = scoped.__methodProfile.controls.seed.integer_range;
        // These are JavaScript's safe integer limits for the number widget,
        // not bounds asserted by OpenRouter when integer_range is absent.
        Object.assign(seed.options, {
            min: bounds?.min ?? Number.MIN_SAFE_INTEGER,
            max: bounds?.max ?? Number.MAX_SAFE_INTEGER,
            step: 1,
        });
        const value = Number(seed.value);
        if (seed.value !== -1 && (!Number.isSafeInteger(value) ||
            (bounds && (value < bounds.min || value > bounds.max)))) {
            intent.inactive ||= {};
            intent.inactive[key] ||= {};
            intent.inactive[key].seed = seed.value;
            seed.value = -1;
        }
    }
    const conflicts=Object.entries(scoped.__methodProfile.controls || {}).filter(([,spec])=>spec.state==='CONFLICT').map(([name])=>name);
    const operationIssue = configureOperationControls(node, scoped.__methodProfile) ||
        (conflicts.length ? `Upstream contract conflict: ${conflicts.join(" / ")}. These controls are omitted.` : "");
    if (node.__orvCapabilityStatus && operationIssue) node.__orvCapabilityStatus.value = operationIssue;
    setVisible(node.__orvCapabilityStatus, Boolean(operationIssue));
    fitPresentationWidth(node);
    publishSemanticProjection(node);
    return scoped;
}

const mediaInputGraphs = new WeakMap();
const MEDIA_KINDS = ["image", "video", "audio"];
const FIXED_MEDIA_ROLES = ["first_frame", "last_frame", "source_video"];

function mediaGraph(node) { return node?.graph || app.graph; }
function mediaLink(graph, id) { return graph?.links?.get?.(id) || graph?.links?.[id]; }
function isMediaInput(input) {
    return isDirectReferenceInput(input) || FIXED_MEDIA_ROLES.includes(input.name) || input.name === "input_references";
}

function outputMediaKind(origin, slot) {
    const type = origin?.outputs?.[slot]?.type;
    if (["IMAGE", "VIDEO", "AUDIO"].includes(type)) return type.toLowerCase();
    if (type !== "OPENROUTER_VIDEO_INPUT_REFERENCE") return null;
    return { OpenRouterVideoImageReference: "image", OpenRouterVideoVideoReference: "video",
        OpenRouterVideoAudioReference: "audio" }[origin?.comfyClass || origin?.type] || null;
}

function mediaSourceToken(origin) {
    origin.properties ||= {};
    return origin.properties.orv_media_source_token ||= `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

// This is the existing intent store, extended to retain each occurrence while it
// is active as well as parked. Never deduplicate intentionally repeated sources.
function captureMediaIntent(node) {
    // Native configure restores target links before every source's properties.
    // Observing that intermediate state must never retire saved occurrences.
    if (app.configuringGraph || node.__orvConfiguringMedia) {
        const media = node.properties?.orv_capability_intent?.media;
        return Array.isArray(media) ? media : [];
    }
    const intent = capabilityIntent(node), graph = mediaGraph(node);
    for (const input of node.inputs || []) mediaInputGraphs.set(input, graph);
    for (const input of directReferenceInputs(node)) if (input.link == null && input.orv_occurrence_id) {
        delete input.orv_occurrence_id;
        input.orv_pending_reference = true;
    }
    const inputs = (node.inputs || []).filter(input => isMediaInput(input) && input.link != null);
    const previous = Array.isArray(intent.media) ? intent.media : [];
    const ids = new Set(), names = new Set();
    node.__orvMediaIntentInvalid = !Array.isArray(intent.media) || previous.some(entry => {
        if (!entry || typeof entry !== "object" || !["string", "number"].includes(typeof entry.origin_id) ||
            !Number.isInteger(entry.origin_slot) || entry.origin_slot < 0) return true;
        if (entry.id != null && (typeof entry.id !== "string" || ids.has(entry.id))) return true;
        if (entry.reference_name != null && (!/^direct_references\.reference_\d+$/.test(entry.reference_name) ||
            (!entry.unresolved && names.has(entry.reference_name)))) return true;
        if (entry.roles != null && (!Array.isArray(entry.roles) || entry.roles.some(role => !FIXED_MEDIA_ROLES.includes(role)))) return true;
        ids.add(entry.id); if (!entry.unresolved) names.add(entry.reference_name);
        return false;
    });
    if (node.__orvMediaIntentInvalid) return [];
    let suffix = Math.max(-1, ...directReferenceInputs(node).map(referenceInputSuffix),
        ...previous.map(entry => referenceInputSuffix({ name: entry.reference_name || entry.name })));
    let ordinal = Math.max(-1, ...previous.map(entry => Number.isInteger(entry.order) ? entry.order : -1));
    const retained = [];
    for (const entry of previous) {
        if (entry.owner_id != null && entry.owner_id !== node.id) {
            retained.push({ ...entry, active_name: null, unresolved: true });
            continue;
        }
        const origin = graph?.getNodeById?.(entry.origin_id);
        if (!origin || (entry.origin_token && origin.properties?.orv_media_source_token !== entry.origin_token)) continue;
        if (entry.active_name != null) {
            const input = inputs.find(item => item.orv_occurrence_id === entry.id || item.name === entry.active_name);
            const link = mediaLink(graph, input?.link);
            // A user disconnect/replacement is authoritative, including after reload.
            if (!link || link.origin_id !== entry.origin_id || link.origin_slot !== entry.origin_slot) continue;
        }
        const migrated = { ...entry, owner_id: node.id, origin_token: mediaSourceToken(origin),
            active_name: entry.active_name ?? null, roles: entry.roles || (FIXED_MEDIA_ROLES.includes(entry.name) ? [entry.name] : []),
            legacy_parked: entry.active_name === undefined && entry.id === undefined,
            order: Number.isInteger(entry.order) ? entry.order : ++ordinal };
        migrated.id ||= `media_${migrated.order}`;
        migrated.reference_name ||= isDirectReferenceInput({ name: migrated.name }) ? migrated.name : `direct_references.reference_${++suffix}`;
        migrated.kind = outputMediaKind(origin, migrated.origin_slot);
        if (migrated.name === "input_references") migrated.collection = true;
        retained.push(migrated);
    }
    for (const input of inputs.sort((a, b) => isDirectReferenceInput(a) && isDirectReferenceInput(b)
        ? referenceInputSuffix(a) - referenceInputSuffix(b) : 0)) {
        const link = mediaLink(graph, input.link), origin = graph?.getNodeById?.(link?.origin_id);
        if (!link || !origin) continue;
        let entry = retained.find(item => item.id === input.orv_occurrence_id && item.active_name === input.name);
        entry ||= retained.find(item => item.active_name === input.name && item.origin_id === link.origin_id && item.origin_slot === link.origin_slot);
        if (!entry) {
            // Group placeholders have provisional names. Allocate their wire
            // position on connection; regrouping never changes it afterwards.
            if (input.orv_pending_reference) input.name = `direct_references.reference_${++suffix}`;
            const order = ++ordinal;
            entry = { id: `media_${order}`, order, owner_id: node.id, origin_id: link.origin_id,
                origin_slot: link.origin_slot, origin_token: mediaSourceToken(origin), kind: outputMediaKind(origin, link.origin_slot),
                reference_name: isDirectReferenceInput(input) ? input.name : `direct_references.reference_${++suffix}`,
                roles: FIXED_MEDIA_ROLES.includes(input.name) ? [input.name] : [], collection: input.name === "input_references" };
            retained.push(entry);
        }
        entry.active_name = input.name;
        entry.kind = outputMediaKind(origin, link.origin_slot);
        input.orv_occurrence_id = entry.id;
        delete input.orv_pending_reference;
    }
    intent.media = retained.sort((a, b) => a.order - b.order);
    return intent.media;
}

// Pure occurrence-to-role projection. Graph reconciliation is performed once by
// the caller, under a guard that suppresses reentrant connection callbacks.
function projectMediaIntent(entries, baseTopology, collectionKinds) {
    const assigned = new Map(), used = new Set();
    // Reserve every explicit role before selecting fallback materials, so an
    // earlier role cannot steal a retained Last Frame occurrence.
    for (const explicit of [true, false]) for (const role of baseTopology.fixed || []) {
        if ([...assigned.values()].includes(role)) continue;
        const kind = role === "source_video" ? "video" : "image";
        const entry = entries.find(item => !item.unresolved && !used.has(item.id) && !item.collection && item.kind === kind &&
            (!explicit || item.roles.includes(role)));
        if (entry) { assigned.set(entry.id, role); used.add(entry.id); }
    }
    const topology = applyTransportInputConstraints(baseTopology, [...assigned.values()].includes("source_video"));
    const collection = entries.find(entry => !entry.unresolved && entry.collection && referenceShapeValid(topology, collectionKinds(entry)));
    if (collection) assigned.set(collection.id, "input_references");
    else {
        const kinds = [];
        for (const entry of entries) {
            if (entry.unresolved || used.has(entry.id) || entry.collection || !topology.reference_kinds?.includes(entry.kind)) continue;
            if (!referencePartialAllowed(topology, [...kinds, entry.kind])) continue;
            assigned.set(entry.id, entry.reference_name); kinds.push(entry.kind);
        }
    }
    return assigned;
}

function parkIncompatibleMedia(node, topology, transition = {}) {
    const graph = mediaGraph(node), entries = captureMediaIntent(node);
    if (node.__orvMediaIntentInvalid || topology.constraint_state === "UNKNOWN" ||
        topology.constraint_state === "CONFLICT" || topology.execution_domain === "UNVERIFIED") return;
    let assigned;
    if (transition.cause !== "explicit") {
        // Accepted older workflows only stored parked entries. Migrate their
        // exact saved roles where already compatible; never reassign active
        // intent or use passive refresh as permission to shrink the graph.
        if (!entries.some(entry => entry.legacy_parked)) return;
        assigned = new Map(entries.filter(entry => entry.active_name != null).map(entry => [entry.id, entry.active_name]));
        const effective = applyTransportInputConstraints(topology, [...assigned.values()].includes("source_video"));
        const kinds = entries.filter(entry => isDirectReferenceInput({ name: assigned.get(entry.id) })).map(entry => entry.kind);
        for (const entry of entries.filter(item => item.legacy_parked && !item.unresolved)) {
            const name = entry.name;
            if ([...assigned.values()].includes(name)) continue;
            const allowed = FIXED_MEDIA_ROLES.includes(name) ? topology.fixed?.includes(name) && entry.kind === (name === "source_video" ? "video" : "image")
                : entry.collection ? kinds.length === 0 && referenceShapeValid(effective, legacyReferenceKinds(null, entry, graph))
                : isDirectReferenceInput({ name }) && ![...assigned.values()].includes("input_references") &&
                    effective.reference_kinds?.includes(entry.kind) && referencePartialAllowed(effective, [...kinds, entry.kind]);
            if (allowed) { assigned.set(entry.id, name); if (isDirectReferenceInput({ name })) kinds.push(entry.kind); }
        }
    } else assigned = projectMediaIntent(entries, topology, entry => legacyReferenceKinds(null, entry, graph));
    for (let index = (node.inputs?.length || 0) - 1; index >= 0; index -= 1) {
        const input = node.inputs[index];
        if (!isMediaInput(input) || input.link == null) continue;
        const entry = entries.find(item => item.id === input.orv_occurrence_id);
        if (!entry || assigned.get(entry.id) !== input.name) node.removeInput?.(index);
    }
    for (const entry of entries) {
        const name = assigned.get(entry.id);
        delete entry.legacy_parked;
        entry.active_name = null;
        if (!name) continue;
        if (!inputByName(node, name)) node.addInput?.(name, entry.collection ? "OPENROUTER_VIDEO_INPUT_REFERENCE_COLLECTION"
            : `${entry.kind.toUpperCase()},OPENROUTER_VIDEO_INPUT_REFERENCE`);
        const input = inputByName(node, name);
        mediaInputGraphs.set(input, graph);
        input.orv_occurrence_id = entry.id;
        if (input.link == null) graph?.getNodeById?.(entry.origin_id)?.connect?.(entry.origin_slot, node, node.inputs.indexOf(input));
        if (input.link != null) {
            entry.active_name = name;
            if (FIXED_MEDIA_ROLES.includes(name) && !entry.roles.includes(name)) entry.roles.push(name);
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
        return referencePartialAllowed(topology, next);
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
    const graph = mediaInputGraphs.get(input) || app.graph;
    const link = mediaLink(graph, input.link);
    return outputMediaKind(graph?.getNodeById?.(link?.origin_id), link?.origin_slot);
}

function fixedRolesForMethod(method) {
    if (method === "I2V") return ["first_frame"];
    if (method === "FLF2V") return ["first_frame", "last_frame"];
    if (method === "V2V_EDIT" || method === "V2V_EXTEND" || method === "V2V_UPSCALE") return ["source_video"];
    return [];
}

function methodUsesReferences(method) {
    return ["IR2V", "MI2V", "VR2V", "AR2V", "MMR2V", "V2V_EDIT", "V2V_EXTEND", "AVATAR_AUDIO"].includes(method);
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
        const link = linkId == null ? null : mediaLink(mediaGraph(node), linkId);
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

function addTrailingReferenceInput(node, kind) {
    const stored = capabilityIntent(node).media;
    const suffix = Math.max(-1, ...directReferenceInputs(node).map(referenceInputSuffix),
        ...(Array.isArray(stored) ? stored : []).filter(Boolean).map(entry => referenceInputSuffix({ name: entry.reference_name || entry.name }))) + 1;
    const name = `direct_references.reference_${suffix}`;
    node.addInput?.(name, `${kind.toUpperCase()},OPENROUTER_VIDEO_INPUT_REFERENCE`);
    const input = inputByName(node, name);
    if (input) { input.orv_reference_kind = kind; input.orv_pending_reference = true; mediaInputGraphs.set(input, mediaGraph(node)); }
}

function configureReferenceTopology(node, capability, method, transition = {}) {
    if (app.configuringGraph || node.__orvConfiguringMedia || node.__orvReconcilingMedia) return;
    node.__orvReconcilingMedia = true;
    try {
        reconcileReferenceTopology(node, capability, method, transition);
    } finally { node.__orvReconcilingMedia = false; }
    publishSemanticProjection(node);
}

function reconcileReferenceTopology(node, capability, method, transition) {
    const baseTopology = capability.__methodProfile?.topology || { fixed: [], reference_kinds: [], kind_sets: [[]], min: 0, max: 0 };
    parkIncompatibleMedia(node, baseTopology, transition);
    const sourcePresent = inputByName(node, "source_video")?.link != null;
    const topology = applyTransportInputConstraints(
        baseTopology, sourcePresent);
    const topologyUncertain = topology.constraint_state === "UNKNOWN" || topology.constraint_state === "CONFLICT";
    const executionUnverified = topology.execution_domain === "UNVERIFIED";
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
    const linked = inputs.filter((item) => item.link != null);
    const unlinked = inputs.filter((item) => item.link == null);
    const effectiveLimit = Number.isInteger(topology.max) && topology.max >= 0 ? topology.max : null;
    // Reviewed topology.max counts optional references; the fixed source is
    // already reserved when deriving that method profile. Legacy global
    // budgets still include it. Do not reserve the same source twice.
    const sourceCount = capability.__methodProfile ? 0 : inputByName(node, "source_video")?.link != null ? 1 : 0;
    const reservedSourceCount = capability.__methodProfile ? 0 : keepFixed.has("source_video") ? 1 : 0;
    const referencesConfirmed = topology.constraint_state !== "UNKNOWN" && topology.constraint_state !== "CONFLICT";
    const usesReferences = Boolean(topology.reference_kinds?.length) && referencesConfirmed && !executionUnverified;
    const possibleKinds = topology.reference_kinds || [];
    const linkedKinds = [...linked.map(connectedReferenceKind),
        ...(legacy?.link != null ? legacyReferenceKinds(legacy) || [] : [])];
    const verifiedSubset = topology.execution_domain === "VERIFIED_CONFIGURATIONS";
    const extensible = usesReferences && legacy?.link == null &&
        (effectiveLimit === null || linked.length + reservedSourceCount < effectiveLimit)
        ? MEDIA_KINDS.filter(kind => possibleKinds.includes(kind) && referencePartialAllowed(topology, [...linkedKinds, kind])) : [];
    const freeKinds = new Set();
    for (const input of unlinked) {
        const kind = input.orv_reference_kind;
        if (!extensible.includes(kind) || freeKinds.has(kind)) node.removeInput?.(node.inputs.indexOf(input));
        else freeKinds.add(kind);
    }
    for (const kind of extensible) if (!freeKinds.has(kind)) addTrailingReferenceInput(node, kind);
    const finalInputs = directReferenceInputs(node).sort((left, right) => {
        const leftKind = connectedReferenceKind(left) || left.orv_reference_kind;
        const rightKind = connectedReferenceKind(right) || right.orv_reference_kind;
        return MEDIA_KINDS.indexOf(leftKind) - MEDIA_KINDS.indexOf(rightKind) ||
            Number(left.link == null) - Number(right.link == null) || referenceInputSuffix(left) - referenceInputSuffix(right);
    });
    const visibleCounts = {};
    for (const input of finalInputs) {
        const kind = connectedReferenceKind(input) || (input.link == null ? input.orv_reference_kind : null);
        // Unknown/invalid saved source types remain visibly unresolved and blocked.
        input.type = kind ? `${kind.toUpperCase()},OPENROUTER_VIDEO_INPUT_REFERENCE` : "OPENROUTER_VIDEO_INPUT_REFERENCE";
        const prefix = kind || "unknown";
        visibleCounts[prefix] = (visibleCounts[prefix] || 0) + 1;
        input.label = `${prefix}_${visibleCounts[prefix]}`;
        mediaInputGraphs.set(input, mediaGraph(node));
    }
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
    const currentCount = finalInputs.filter((item) => item.link != null).length +
        (legacy?.link != null ? legacyReferenceKinds(legacy)?.length || 0 : 0);
    const allAtCaps = !possibleKinds.some(kind => referencePartialAllowed(topology, [...linkedKinds, kind]));
    const perKindCounts = Object.fromEntries([...new Set(linkedKinds)].map(kind =>
        [kind, linkedKinds.filter(value => value === kind).length]));
    const perKindSummary = Object.entries(perKindCounts).map(([kind, count]) => `${kind} ${count}`).join(" · ");
    const remainingByKind = extensible.map(kind => {
        const kindMax = topology.per_kind_max?.[kind];
        const totalRemaining = effectiveLimit === null ? null : effectiveLimit - currentCount - sourceCount;
        const remaining = Number.isInteger(kindMax) ? Math.min(kindMax - (perKindCounts[kind] || 0), totalRemaining ?? Infinity) : totalRemaining;
        return `${kind.toUpperCase()} ${remaining === null || verifiedSubset ? "capacity unverified" : `${remaining} available`}`;
    }).join(" · ");
    const unverifiedShape = executionUnverified && !referenceShapeValid(topology, linkedKinds);
    node.__orvReferenceSummary = usesReferences
        ? `${currentCount + sourceCount} connected${perKindSummary ? ` · ${perKindSummary}` : ""} · ${
            effectiveLimit !== null
            ? (allAtCaps ? (verifiedSubset ? "verified subset boundary · upper bound unverified" : "maximum reached") : `${effectiveLimit - currentCount - sourceCount} remaining`)
                : (allAtCaps ? (verifiedSubset ? "verified subset boundary · upper bound unverified" : "maximum reached") : (topology.execution_domain === "DOCUMENTED_CONTRACT" ? "limit not published" : "limit unverified"))
        }${remainingByKind ? ` · ${remainingByKind}` : ""}`
        : executionUnverified
            ? unverifiedShape
                ? "METHOD DOCUMENTED · input configurations require verification · existing links preserved; Generate blocked"
                : "Additional reference configurations require verification · existing links preserved"
            : topology.constraint_state === "UNKNOWN" || topology.constraint_state === "CONFLICT"
            ? "Reference limit unverified · existing links preserved" : "";
    const storedMedia = capabilityIntent(node).media;
    const parkedCount = Array.isArray(storedMedia) ? storedMedia.filter(entry => entry?.active_name === null).length : 0;
    if (parkedCount) node.__orvReferenceSummary = `${node.__orvReferenceSummary || `${currentCount} connected`} · ${parkedCount} parked`;
    if (node.__orvSummary) {
        node.__orvSummary.value = node.__orvReferenceSummary;
        (node.__orvSummary.options ||= {}).tooltip = node.__orvReferenceSummary;
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
    const orphanedFixed = ["first_frame", "last_frame", "source_video"].some(name =>
        inputByName(node, name)?.link != null && !keepFixed.has(name));
    const incompatibleReferences = !referencePartialAllowed(topology, linkedKinds) ||
        (legacy?.link != null && legacyReferenceKinds(legacy) === null);
    node.__orvReferenceInvalid = node.__orvMediaIntentInvalid || topologyUncertain || unverifiedShape || topology.transport_source_overflow || wrongReferenceKind || wrongFixedKind ||
        orphanedFixed || incompatibleReferences || (effectiveLimit !== null && currentCount + sourceCount > effectiveLimit);
    if ((wrongReferenceKind || wrongFixedKind) && !node.__orvMethodBlocked) {
        node.__orvCapabilityStatus.value = "INCOMPATIBLE · media kind · links preserved";
        setVisible(node.__orvCapabilityStatus, true);
    }
    if (node.__orvReferenceInvalid) {
        disclose(node, node.__orvMediaIntentInvalid ? "UNRESOLVED MEDIA INTENT; saved state preserved; Generate blocked" : unverifiedShape
            ? "METHOD DOCUMENTED · INPUT CONFIGURATIONS REQUIRE VERIFICATION; existing links preserved; Generate blocked"
            : topologyUncertain
            ? "REFERENCES · limit unverified; existing links preserved; Generate blocked"
            : topology.transport_source_overflow
                ? "SOURCE VIDEO EXCEEDS TRANSPORT INPUT LIMIT; Generate blocked"
                : `REFERENCES ${currentCount + sourceCount}/${effectiveLimit}: preserve links; reduce explicitly before Generate`);
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
        if (!node.__orvModelCapability?.supported_inference_methods?.includes(next)) return;
        previous?.apply(this, args);
        // Invalidate older asynchronous projections and their estimates.
        node.__orvProjectionVersion = (node.__orvProjectionVersion || 0) + 1;
        node.__orvEstimateRevision = (node.__orvEstimateRevision || 0) + 1;
        node.__orvConfigureVersion = (node.__orvConfigureVersion || 0) + 1;
        node.__orvConfiguringMedia = false;
        delete node.__orvPendingMediaSelection;
        clearTimeout(node.__orvEstimateTimer);
        node.__orvMethodExplicit = true;
        node.__orvLastMethod = next;
        if (node.__orvModelCapability) reprojectNodeSemantics(node, node.__orvModelCapability, next, { cause: "explicit" });
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
    const revision=node.__orvEstimateRevision=(node.__orvEstimateRevision || 0)+1;
    let providerControls;
    try { providerControls=JSON.parse(widget(node,"provider_options")?.value || "[]"); }
    catch { providerControls=null; }
    const providerSchema=node.__orvCapability?.__methodProfile?.controls?.provider_options?.providers || {};
    if(!Array.isArray(providerControls)||providerControls.length||Object.values(providerSchema).some(options=>Object.values(options).some(spec=>spec.required))){
        node.__orvEstimate.value="ESTIMATE UNAVAILABLE";
        node.setDirtyCanvas?.(true,true);
        return;
    }
    if (node.__orvReferenceInvalid || geometryAuthority(node) === "AMBIGUOUS") {
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
    const topology = applyTransportInputConstraints(profile?.topology,
        inputByName(node, "source_video")?.link != null);
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
        if(revision!==node.__orvEstimateRevision)return;
        node.__orvEstimate.value =
            result.availability === "AVAILABLE"
                ? `≈ $${result.estimated_cost_usd} EST.`
                : "ESTIMATE UNAVAILABLE";
    } catch {
        if(revision!==node.__orvEstimateRevision)return;
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
                node.__orvConfigureVersion = (node.__orvConfigureVersion || 0) + 1;
                node.__orvConfiguringMedia = false;
                node.__orvEstimateRevision = (node.__orvEstimateRevision || 0) + 1;
                node.__orvPendingMediaSelection = { model: canonicalModel(node), method: widget(node, "inference_method")?.value,
                    revision: (node.__orvMediaSelectionRevision || 0) + 1 };
                node.__orvMediaSelectionRevision = node.__orvPendingMediaSelection.revision;
                projectSelectedModel(node);
                return;
            }
            if (item.name === "duration" && Number(item.value) !== 0) {
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

async function projectSelectedModel(node, force = false, snapshot = null) {
    if (app.configuringGraph || node.__orvConfiguringMedia) return;
    const version = (node.__orvProjectionVersion || 0) + 1;
    node.__orvProjectionVersion = version;
    orderPresentationWidgets(node);
    node.__orvCapabilityStatus.value = "";
    setVisible(node.__orvCapabilityStatus, false);
    try {
        const connection = await loadConnection(force);
        if (node.__orvProjectionVersion !== version) return;
        if (connection.state !== "CONNECTED") {
            setVisible(node.__orvConnectionCta, true);
            node.__orvCapabilityStatus.value = "OpenRouter connection required";
            setVisible(node.__orvCapabilityStatus, true);
            fitPresentationWidth(node);
            return;
        }
        setVisible(node.__orvConnectionCta, false);
        const projection = snapshot || await loadCapabilities(force);
        if (node.__orvProjectionVersion !== version) return;
        if (projection.source_state === "STALE_FALLBACK") {
            node.__orvCatalogueFailed = true;
            node.__orvSelectionBlocked = true;
            node.__orvCapabilityStatus.value = "CATALOGUE STALE — refresh failed; saved settings and links preserved";
            setVisible(node.__orvCapabilityStatus, true);
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
            return;
        }
        node.__orvCatalogueFailed = false;
        if (projection.ui_contract_version !== UI_CONTRACT_VERSION) {
            node.__orvCapabilityStatus.value =
                `FRONTEND/BACKEND CONTRACT MISMATCH: UI ${UI_CONTRACT_VERSION} / BACKEND ${projection.ui_contract_version ?? "UNKNOWN"}`;
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
            return;
        }
        const missingSavedModel = configureModelPicker(node, projection);
        if ((projection.models || []).length === 0) {
            node.__orvSelectionBlocked = true;
            node.__orvCapabilityStatus.value = "No supported video models currently available — saved settings preserved";
            setVisible(node.__orvCapabilityStatus, true);
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
            return;
        }
        if (missingSavedModel) {
            node.__orvSelectionBlocked = true;
            node.__orvCapabilityStatus.value =
                `SAVED MODEL UNAVAILABLE: ${missingSavedModel} — no confirmed method; select a replacement`;
            setVisible(node.__orvCapabilityStatus, true);
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
        const savedMethod = widget(node, "inference_method")?.value;
        if (snapshot && METHODS.includes(savedMethod) &&
            !capability.supported_inference_methods.includes(savedMethod)) {
            node.__orvSelectionBlocked = true;
            widget(node, "inference_method").options.values = [...capability.supported_inference_methods];
            node.__orvCapabilityStatus.value = `METHOD UNAVAILABLE: ${savedMethod} — saved settings and links preserved; select a replacement`;
            setVisible(node.__orvCapabilityStatus, true);
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
            node.__orvModelCapability = capability;
            node.__orvReferenceSummary = `${selectedReferenceKinds(node)?.length ?? 0} connected · limit unverified`;
            if (node.__orvSummary) {
                node.__orvSummary.value = node.__orvReferenceSummary;
                setVisible(node.__orvSummary, true);
            }
            return;
        }
        node.__orvSelectionBlocked = false;
        node.__orvCapabilityStatus.value = "";
        setVisible(node.__orvCapabilityStatus, false);
        setVisible(widget(node, "first_frame_url"), false);
        setVisible(widget(node, "last_frame_url"), false);
        node.__orvModelCapability = capability;
        const method = configureInferenceMethod(node, capability);
        const pendingSelection = node.__orvPendingMediaSelection;
        const explicitSelection = pendingSelection?.model === model && pendingSelection.method === savedMethod;
        if (explicitSelection) delete node.__orvPendingMediaSelection;
        reprojectNodeSemantics(node, capability, method, { cause: explicitSelection ? "explicit" : "catalogue" });
        await refreshEstimate(node);
    } catch {
        if (node.__orvProjectionVersion !== version) return;
        node.__orvCatalogueFailed = true;
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

function capabilitySettingRenderer() {
    const root = document.createElement("div");
    const summary = document.createElement("p");
    summary.textContent = "Loading capability accounting…";
    const models = document.createElement("select");
    models.setAttribute("aria-label", "Discovered model capabilities");
    const details = document.createElement("div");
    root.append(summary, models, details);
    loadCapabilities().then(projection => {
        const report = projection.capability_completeness;
        if (!report) { summary.textContent = "Capability accounting unavailable in this server version."; return; }
        summary.textContent = `${projection.source_state || "UNKNOWN"} · ${report.discovered_model_count} discovered models · ${report.executable_method_count} executable methods. Accounted capabilities are not proof of executable support.`;
        for (const model of report.models) {
            const option = document.createElement("option");
            option.value = model.model_id; option.textContent = model.model_id;
            models.append(option);
        }
        const paint = () => {
            details.replaceChildren();
            const model = report.models.find(item => item.model_id === models.value);
            for (const row of model?.rows || []) {
                const line = document.createElement("p");
                const sources = [...new Set((row.evidence || []).map(item => item.source))];
                line.textContent = `${row.path} — ${row.disposition}: ${row.reason}${sources.length ? ` · ${sources.join(", ")}` : ""}`;
                details.append(line);
            }
        };
        models.onchange = paint; paint();
    }).catch(() => { summary.textContent = "Catalogue unavailable. Saved workflow settings are preserved."; });
    return root;
}

app.registerExtension({
    name: EXTENSION,
    settings: [
        {
            id: "OpenRouter Video.Capabilities",
            name: "Capability accounting",
            category: ["OpenRouter Video", "Capabilities"],
            type: capabilitySettingRenderer,
            defaultValue: null,
            telemetry: { trackChanges: false },
        },
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
        startCatalogueLifecycle();
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
        const previousNodeConfigure = nodeType.prototype.configure;
        if (typeof previousNodeConfigure === "function") nodeType.prototype.configure = function (...args) {
            // LGraphNode.configure emits input callbacks before onConfigure.
            // Mark reconstruction at entry, including standalone undo/configure.
            this.__orvConfiguringMedia = true;
            this.__orvProjectionVersion = (this.__orvProjectionVersion || 0) + 1;
            try { return previousNodeConfigure.apply(this, args); }
            catch (error) { this.__orvConfiguringMedia = false; throw error; }
        };
        const previousConnectInput = nodeType.prototype.onConnectInput;
        nodeType.prototype.onConnectInput = function (slot, type, output, origin, originSlot, ...rest) {
            if (previousConnectInput?.call(this, slot, type, output, origin, originSlot, ...rest) === false) return false;
            if (app.configuringGraph || this.__orvConfiguringMedia || this.__orvReconcilingMedia) return true;
            const input = this.inputs?.[slot];
            if (!input || !isMediaInput(input) || !this.__orvCapability) return;
            const kind = outputMediaKind(origin, originSlot);
            const topology = applyTransportInputConstraints(this.__orvCapability.__methodProfile?.topology,
                inputByName(this, "source_video")?.link != null || input.name === "source_video");
            if (FIXED_MEDIA_ROLES.includes(input.name)) return topology.fixed?.includes(input.name) &&
                kind === (input.name === "source_video" ? "video" : "image") &&
                (input.name !== "source_video" || referencePartialAllowed(topology,
                    directReferenceInputs(this).filter(item => item.link != null).map(connectedReferenceKind)));
            if (isDirectReferenceInput(input)) {
                if (kind === null || (input.orv_reference_kind && input.orv_reference_kind !== kind) || inputByName(this, "input_references")?.link != null) return false;
                const others = directReferenceInputs(this).filter(item => item !== input && item.link != null).map(connectedReferenceKind);
                return referencePartialAllowed(topology, [...others, kind]);
            }
        };
        const previousConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (...args) {
            const result = previousConnectionsChange?.apply(this, args);
            if (app.configuringGraph || this.__orvReconcilingMedia || this.__orvConfiguringMedia) return result;
            // Establish occurrence order at the connection event, before a second
            // connection can arrive during the debounced catalogue projection.
            captureMediaIntent(this);
            this.__orvEstimateRevision = (this.__orvEstimateRevision || 0) + 1;
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
            delete this.__orvPendingMediaSelection;
            this.__orvConfiguringMedia = true;
            this.__orvProjectionVersion = (this.__orvProjectionVersion || 0) + 1;
            const configuringVersion = this.__orvConfigureVersion = (this.__orvConfigureVersion || 0) + 1;
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
                if (this.__orvConfigureVersion !== configuringVersion) return;
                this.__orvConfiguringMedia = false;
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
