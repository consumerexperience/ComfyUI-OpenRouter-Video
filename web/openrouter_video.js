import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";
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
    T2V: "T2V: Text → Video",
    I2V: "I2V: First Frame → Video",
    FLF2V: "FLF2V: First + Last Frame → Video",
    IR2V: "IR2V: Single Image Reference → Video",
    MI2V: "MI2V: Multiple Image References → Video",
    VR2V: "VR2V: Video Reference → Video",
    AR2V: "AR2V: Audio Reference → Video",
    MMR2V: "MMR2V: Mixed Multimodal References → Video",
    V2V_EDIT: "V2V_EDIT: Source Video → Edited Video",
    V2V_EXTEND: "V2V_EXTEND: Source Video → Extended Video",
    V2V_UPSCALE: "V2V_UPSCALE: Upscale Video",
    AVATAR_AUDIO: "AVATAR_AUDIO: Photo + Audio → Talking Avatar",
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
// Cost presentation only. Object identity never leaves this process or a workflow.
const costPresentationNodes = new Set();
const actualGraphEpochs = new WeakMap();
const actualDispatches = new Map();
const actualQueueTickets = new Map();
const actualQueueObservers = new Set();
const actualEarlyEvents = new Map();
const actualPreparedNodes = new WeakMap();
const costPreviewSelections = new WeakMap();
const ACTUAL_BINDING_TTL_MS = 60 * 60 * 1000;
const ACTUAL_EARLY_TTL_MS = 30000;
let actualGraphEpoch = 0;
let actualDispatchSequence = 0;
let actualPruneTimer;
let costLifecycleInstalled = false;

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
        if (!previous || previous.type === "combo" || previous.type === "slider" ||
            (name === "duration" && previous.__orvDurationAdapter)) continue;
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

function nodeTypography(node = null) {
    const native=node?.innerFontStyle;
    const size=typeof native==="string" ? Number(native.match(/([0-9.]+)px/)?.[1]) : 12;
    const family='Inter, Arial, Helvetica, "Noto Sans", "Noto Sans CJK SC", "Noto Sans CJK JP", "Noto Sans Arabic", "Noto Sans Devanagari", sans-serif';
    return {family,size:Number.isFinite(size)&&size>0?size:12,weight:400,line:20};
}

function installNodeTypography(node) {
    const token=nodeTypography(node);
    if(!node.__orvNativeFontsInstalled){
        node.__orvNativeFontsInstalled=true;
        for(const key of ["innerFontStyle","titleFontStyle"]){
            const original=node[key];
            if(typeof original!=="string")continue;
            const prefix=original.match(/^(.*?\b[0-9.]+px)(?:\/[^\s]+)?\s+/)?.[1];
            if(prefix)Object.defineProperty(node,key,{configurable:true,get:()=>`${prefix} ${token.family}`});
        }
    }
    for(const item of node.widgets || []){
        if(item.element?.style)Object.assign(item.element.style,{fontFamily:token.family,fontWeight:"400",lineHeight:"18px"});
        for(const method of ["draw","drawWidget"]){
            const marker=`__orvTypography_${method}`;
            if(typeof item[method]!=="function" || item[marker])continue;
            const draw=item[method];item[marker]=true;
            let numericContext, numericView;
            item[method]=function(ctx,...args){ctx.save();ctx.font=`${token.weight} ${token.size}px ${token.family}`;ctx.textBaseline="alphabetic";
                const numericSlider = method === "drawWidget" && this.__orvProviderOption
                    && this.type === "slider" && typeof this.value === "number";
                if (numericSlider && numericContext !== ctx) {
                    numericContext = ctx;
                    numericView = new Proxy(ctx, {
                    get(target,key) {
                        if (key === "fillText") return (_text,...position) =>
                            target.fillText(`${item.label}  ${providerDisplayValue(item)}`,...position);
                        const value = Reflect.get(target,key,target);
                        return typeof value === "function" ? value.bind(target) : value;
                    },
                    set(target,key,value) { return Reflect.set(target,key,value,target); },
                    });
                }
                try{return draw.call(this,numericSlider ? numericView : ctx,...args);}finally{ctx.restore();}};
        }
    }
}

function providerDisplayValue(item, includeAuto = true, editing = false) {
    if (item.__orvProviderOption && ["slider","number"].includes(item.type)) {
        const locale = costLocale();
        const auto = locale === "ru" ? "Авто" : "Auto";
        const raw = item.value;
        let cached = item.__orvNumericDisplay;
        if (!cached || cached.locale !== locale || cached.editing !== editing || !Object.is(cached.raw, raw)) {
            const text = typeof raw === "number" ? new Intl.NumberFormat(locale, {
                useGrouping: false, maximumFractionDigits: editing || !item.__orvProviderFractional ? 20 : 2,
            }).format(raw) : "";
            cached = item.__orvNumericDisplay = {locale, raw, editing, text};
        }
        if (includeAuto && item.__orvProviderAuto) return item.__orvProviderKnownDefault ? `${cached.text} ${auto}` : auto;
        return cached.text;
    }
    return String(item._displayValue ?? item.value ?? "");
}

function installClassicProviderSlider(item) {
    if (item.__orvClassicProviderSlider || typeof item.onClick !== "function") return;
    item.__orvClassicProviderSlider = true;
    const nativeClick = item.onClick;
    const nativeSet = item.setValue;
    item.onClick = function (event) {
        if (this.computedDisabled || this.options.read_only) return;
        const width = this.width || event.node.size[0];
        const x = event.e.canvasX - event.node.pos[0];
        if (Math.abs(x-width/2) <= 27 && event.canvas?.prompt) {
            event.canvas.prompt(this.label, providerDisplayValue(this, false, true), draft => {
                const separator = new Intl.NumberFormat(costLocale()).formatToParts(1.1)
                    .find(part => part.type === "decimal")?.value || ".";
                const text = String(draft).trim().replace(separator, ".");
                if (!text || !Number.isFinite(Number(text))) return;
                const value = Math.min(this.options.max, Math.max(this.options.min, Number(text)));
                if (value !== this.value || this.__orvProviderAuto) this.callback?.(value);
            }, event.e);
            return;
        }
        return nativeClick.call(this,event);
    };
    if (typeof nativeSet === "function") item.setValue = function (value, event) {
        const {min,max,step2} = this.options;
        const next = value <= min ? min : value >= max ? max :
            Number((min + Math.round((value-min)/step2)*step2).toPrecision(15));
        if (this.__orvProviderAuto && Object.is(next,this.value)) this.callback?.(next);
        else return nativeSet.call(this,next,event);
    };
}

function syncProviderGroupHeading(node,row) {
    const input=row.querySelector('input');
    const item=(node.widgets || []).find(w=>w.__orvProviderHeading && input?.getAttribute?.('aria-label')===w.name);
    if(!item)return;
    let title=row.querySelector('.orv-provider-heading');
    if(!title){title=document.createElement('span');title.className='orv-provider-heading';Object.assign(title.style,{gridColumn:'1 / -1',font:`600 11px/20px ${nodeTypography(node).family}`,color:'#999',padding:'0 15px'});row.append(title);}
    if(title.textContent!==item.label)title.textContent=item.label;input.style.display='none';
    const label=row.querySelector('[data-testid="widget-layout-field-label"]');if(label?.style)label.style.display='none';
}

function syncProviderNumericState(node, row) {
    const label=row.querySelector('[data-testid="widget-layout-field-label"]');
    const input=row.querySelector('input');
    const item=(node.widgets || []).find(item=>item.__orvProviderOption && !item.hidden &&
        ["number","slider"].includes(item.type) && (input?.getAttribute?.("aria-label")===item.name || label?.textContent?.trim()===(item.displayName || item.label)));
    if(!item)return;
    const unknownAuto=item.__orvProviderAuto && !item.__orvProviderKnownDefault;
    if (input && !unknownAuto && item.__orvProviderFractional && input.style) {
        if (!input.__orvCompactNumberOnBlur) {
            input.__orvCompactNumberOnBlur = true;
            input.addEventListener("focus", () => {
                const current = input.__orvNumericItem;
                if (current && !current.computedDisabled) input.value = providerDisplayValue(current, false, true);
            }, true);
            input.addEventListener("blur", () => {
                // The host reapplies its fixed-precision string on blur.
                // Reformat the settled value without touching the editor draft.
                requestAnimationFrame(() => {
                    if (row.isConnected) syncProviderNumericState(node, row);
                });
            });
        }
        input.__orvNumericItem = item;
        const decimal = providerDisplayValue(item, false);
        if (input.ownerDocument?.activeElement !== input && input.value !== decimal) input.value = decimal;
        const style = typeof getComputedStyle === "function" ? getComputedStyle(input) : null;
        const padding = (parseFloat(style?.paddingLeft) || 0) + (parseFloat(style?.paddingRight) || 0);
        const width = `calc(${Math.max(4, decimal.length + 1)}ch + ${padding}px)`;
        if (input.style.width !== width) input.style.width = width;
        if (input.style.minWidth !== width) input.style.minWidth = width;
        input.style.textOverflow = "clip";
        // PrimeVue's fixed-width wrapper also contains the Auto/Reset control.
        const wrapper = input.parentElement;
        if (wrapper?.classList?.contains("p-inputnumber")) {
            wrapper.style.width = "max-content";
            wrapper.style.flexShrink = "0";
        }
    }
    if(input && unknownAuto){
        input.placeholder=providerAutoLabel({});
        // Native numeric presentation coerces null to zero. Omission is not zero;
        // leave focused drafts to the native editor and never change widget intent.
        if(input.ownerDocument?.activeElement!==input && input.value!=="")input.value="";
    }
    const absolute=input && typeof getComputedStyle==="function" && getComputedStyle(input).position==="absolute";
    const host=absolute ? input.parentElement?.parentElement : input?.parentElement;
    syncNumericAutoButton(host, item, unknownAuto);
}

function syncNumericAutoButton(host, item, hidden) {
    if (!host?.append) return;
    let state=host.querySelector?.('.orv-provider-state');
    if(!state){state=document.createElement('button');state.type='button';state.className='orv-provider-state';
        Object.assign(state.style,{font:'inherit',fontSize:'11px',flex:'0 0 auto',padding:'0 4px',border:'0',background:'transparent',color:'inherit'});
        state.addEventListener('click',event=>{event.stopPropagation();state.__orvReset?.();});host.append(state);}
    state.hidden=Boolean(hidden);
    state.__orvReset=item.__orvResetProvider || item.__orvResetDuration;
    const automatic=item.__orvDurationAdapter ? Number(item.value) === -1 : item.__orvProviderAuto;
    const text=automatic?providerAutoLabel({}):'↺';if(state.textContent!==text)state.textContent=text;
    state.title=costLocale()==='ru'?'Сбросить в Авто':'Reset to Auto';
    state.setAttribute('aria-label',`${item.label}: ${state.title}`);
}

function syncDurationSliderState(node, row) {
    const input = row.querySelector('input[aria-label="duration"]');
    const handle = row.querySelector('[role="slider"]');
    const item = widget(node, "duration");
    if (!input || !handle || !item?.__orvDurationAdapter) return;
    const mixed = Boolean(item.__orvResetDuration);
    const automatic = mixed && Number(item.value) === -1;
    const host = input.parentElement?.parentElement;
    if (mixed) syncNumericAutoButton(host,item,false);
    else host?.querySelector('.orv-provider-state')?.remove();
    // The native slider clamps out-of-range values to the first position.
    // While Auto owns the semantic value, conceal that numeric position.
    const numeric = input.parentElement;
    numeric.style.display = automatic ? "none" : "";
    handle.style.opacity = automatic ? "0" : "";
    if (automatic) handle.setAttribute('aria-valuetext',providerAutoLabel({}));
    else handle.removeAttribute('aria-valuetext');
}

function presentationSize(node) { return node.__orvLiveSize || node.size || [400,0]; }

function classicContentBounds(item, width) {
    // The pinned native BaseWidget exposes these inherited geometry tokens.
    // Insets apply to all text and preserve native arrows/hit targets unchanged.
    const base=item.constructor || {}, margin=Number(base.margin) || COMPACT_LAYOUT.inset;
    const arrows=["combo","number"].includes(item.type);
    const reserved=arrows ? (Number(base.arrowMargin) || 6)+(Number(base.arrowWidth) || 10) : 0;
    const left=margin+reserved+COMPACT_LAYOUT.gap, right=width-left;
    const labelWidth=Math.max(0,Math.min(160,Math.max(112,128+(width-400)/3),right-left-80));
    return {left,right,labelWidth,valueLeft:left+labelWidth+COMPACT_LAYOUT.gap*2};
}

function fitWidgetText(ctx, text, width) {
    if (!(width>0)) return "";
    if (!ctx.measureText || ctx.measureText(text).width<=width) return text;
    const points=Array.from(text), tail="…";let low=0,high=points.length;
    while(low<high){const mid=Math.ceil((low+high)/2);if(ctx.measureText(points.slice(0,mid).join("")+tail).width<=width)low=mid;else high=mid-1;}
    return ctx.measureText(tail).width>width ? "" : points.slice(0,low).join("")+tail;
}

function scheduleResizeLayout(node) {
    if (node.__orvResizeFrame != null) return;
    const run=()=>{node.__orvResizeFrame=null;if(node.__orvRemoved)return;syncBetaPresentation(node);node.setDirtyCanvas?.(true,true);};
    node.__orvResizeFrame=typeof requestAnimationFrame==="function" ? requestAnimationFrame(run) : (queueMicrotask(run),0);
}

function suppressPackageBadge(node, root = null) {
    // Clone the native badge projection, never mutate its cached identity/data.
    for(let i=0;i<(node.badges || []).length;i++){
        const source=node.badges[i];if(typeof source!=="function" || source.__orvPackFiltered)continue;
        const wrapped=function(...args){const badge=source.apply(this,args);if(typeof badge?.text!=="string" || !badge.text.includes("OpenRouter-Video"))return badge;
            return Object.assign(Object.create(Object.getPrototypeOf(badge)),badge,{text:badge.text.replaceAll("OpenRouter-Video","").trim()});};
        wrapped.__orvPackFiltered=true;node.badges[i]=wrapped;
    }
    if (!root?.querySelectorAll) return;
    for(const leaf of root.querySelectorAll("span,div")){
        if(leaf.childElementCount || leaf.textContent?.trim()!=="OpenRouter-Video" || leaf.closest?.('[data-testid="node-widgets"], .lg-node-header'))continue;
        let badge=leaf;
        while(badge.parentElement && badge.parentElement!==root && badge.parentElement.textContent?.trim()==="OpenRouter-Video" && !badge.parentElement.querySelector?.("button,input,textarea"))badge=badge.parentElement;
        if(badge.style)badge.style.display="none";
    }
}

function installParameterColumns(node) {
    for (const item of node.widgets || []) {
        if (["prompt","REFERENCES","STATE","Advanced"].includes(item.name) || item.__orvColumnsInstalled) continue;
        if (!["text","combo","number","toggle","slider"].includes(item.type)) continue;
        if (typeof item.drawTruncatingText !== "function" && typeof item.drawLabel !== "function") continue;
        item.__orvColumnsInstalled = true;
        const bounds = width => classicContentBounds(item,width);
        const label = (ctx,width) => {
            const b=bounds(width), y=item.y || 0;
            ctx.save();ctx.font=`400 ${nodeTypography(node).size}px ${nodeTypography(node).family}`;ctx.textBaseline="alphabetic";ctx.beginPath();ctx.rect(b.left,y,b.labelWidth,item.height || COMPACT_LAYOUT.row);ctx.clip();
            ctx.textAlign="left";ctx.fillStyle=item.secondary_text_color || "#C4C4C4";
            ctx.fillText(fitWidgetText(ctx,String(item.displayName ?? item.label ?? item.name),b.labelWidth),b.left,item.labelBaseline ?? y+15);ctx.restore();
            return b;
        };
        if (typeof item.drawLabel === "function") item.drawLabel=function(ctx) { label(ctx,this.width || presentationSize(node)[0]); };
        if (typeof item.drawTruncatingText === "function") item.drawTruncatingText=function({ctx,width}) {
            const b=label(ctx,width), y=this.y || 0;
            ctx.save();ctx.font=`400 ${nodeTypography(node).size}px ${nodeTypography(node).family}`;ctx.textBaseline="alphabetic";ctx.beginPath();ctx.rect(b.valueLeft,y,Math.max(0,b.right-b.valueLeft),this.height || COMPACT_LAYOUT.row);ctx.clip();
            ctx.textAlign="right";ctx.fillStyle=this.text_color || "#F9F9F9";
            const value = providerDisplayValue(this);
            const widthAvailable = Math.max(0,b.right-b.valueLeft);
            if (this.__orvProviderFractional && widthAvailable > 0) ctx.fillText(value,b.right,this.labelBaseline ?? y+15,widthAvailable);
            else ctx.fillText(fitWidgetText(ctx,value,widthAvailable),b.right,this.labelBaseline ?? y+15);
            ctx.restore();
        };
    }
}

function sizePrimaryControls(node) {
    installParameterColumns(node);
    for (const item of node.widgets || []) {
        if (["model", "inference_method", "resolution", "aspect_ratio", "duration", "seed", "generate_audio", "size", "randomize"].includes(item.name)) {
            item.__orvComputeSize = () => [0, COMPACT_LAYOUT.row];
            setVisible(item, !item.hidden);
        }
    }
    for (const prompt of creativeTextWidgets(node, true)) {
        prompt.__orvComputeSize = () => {
            const region = textRegionGeometry(node);
            const margin = Number(prompt.margin) || 0;
            // LiteGraph includes its ordinary gap in the allocation and its
            // DOM overlay removes two margins. A following native row has no
            // leading DOM margin, so reserve it here, outside the text area.
            const height = node.__orvMeasuringMinimum
                ? COMPACT_LAYOUT.prompt + COMPACT_LAYOUT.domInset : region.field;
            if (!margin) return [0,height];
            const following = node.widgets.slice(node.widgets.indexOf(prompt)+1).find(item => !item.hidden);
            const trailing = following && !(Number(following.margin) > 0) ? margin : 0;
            if (prompt.element?.style) {
                const cssHeight = trailing ? `calc(100% - ${trailing}px)` : "100%";
                if (prompt.element.style.height !== cssHeight) prompt.element.style.height = cssHeight;
            }
            return [0,height + 2*margin - COMPACT_LAYOUT.gap + trailing];
        };
        setVisible(prompt, !prompt.hidden);
    }
}

function creativeTextWidgets(node, includeHidden = false) {
    return (node.widgets || []).filter(item => (item.name === "prompt" || item.__orvTextSemantic)
        && (includeHidden || !item.hidden));
}

function textRegionGeometry(node, minimum = COMPACT_LAYOUT.prompt + COMPACT_LAYOUT.domInset) {
    const count = creativeTextWidgets(node).length;
    const gaps = Math.max(0, count - 1) * COMPACT_LAYOUT.gap;
    const stored=node.properties?.orv_prompt_geometry;
    const preferred=node.__orvLivePromptHeight ?? node.__orvMasterPromptHeight ?? (stored?.version===2 ? stored.height : undefined);
    const field=count ? Math.max(minimum,Number.isFinite(preferred) ? preferred : minimum) : 0;
    return {count,min:count*minimum+gaps,budget:count*field+gaps,field};
}

function persistMasterPromptHeight(node, height) {
    if(!Number.isFinite(height))return;
    node.__orvMasterPromptHeight=Math.max(0,height);
    node.properties ||= {};
    node.properties.orv_prompt_geometry={version:2,height:node.__orvMasterPromptHeight};
}

function masterHeightFromRegion(node, budget) {
    const count=creativeTextWidgets(node).length;
    return count ? Math.max(0,(budget-Math.max(0,count-1)*COMPACT_LAYOUT.gap)/count) : node.__orvMasterPromptHeight;
}

function nativeFlowHeight(element, scale) {
    // Measure normal-flow children instead of counting native flex slack as content.
    // The returned number is applied through node.setSize, never independent CSS bounds.
    if (typeof getComputedStyle !== "function" || !element?.getBoundingClientRect) return null;
    const style = getComputedStyle(element);
    if (style.display === "none") return 0;
    if (style.display !== "flex" || style.flexDirection !== "column") return element.getBoundingClientRect().height / scale;
    const children = [...element.children].filter(child => {
        const css = getComputedStyle(child);
        return css.display !== "none" && !["absolute", "fixed"].includes(css.position);
    });
    const pixels = key => parseFloat(style[key]) || 0;
    return children.reduce((sum,child) => {
        const css = getComputedStyle(child);
        return sum + nativeFlowHeight(child,scale) + (parseFloat(css.marginTop)||0) + (parseFloat(css.marginBottom)||0);
    }, 0)
        + Math.max(0,children.length-1)*pixels("rowGap")
        + pixels("paddingTop")+pixels("paddingBottom")+pixels("borderTopWidth")+pixels("borderBottomWidth");
}

function stylePrompt(node) {
    for (const item of creativeTextWidgets(node, true)) {
    item.label = creativeTextLabel(item);
    const element = item.element;
    if (!element?.style) continue;
    element.placeholder = item.label;
    element.style.background = "#20272a";
    element.style.border = "1px solid #354540";
    element.style.borderRadius = "4px";
    element.style.color = "#e4ece9";
    element.style.fontSize = "12px";
    const margin = typeof item.margin === "number" ? COMPACT_LAYOUT.gap : 0;
    // Native DOMWidget owns the vertical offset. Its horizontal margin is part
    // of the same inset used by the other full-width Classic rows.
    (item.options ||= {}).margin = margin;
    element.style.padding = "4px 6px";
    element.style.margin = "0";
    element.style.boxSizing = "border-box";
    element.style.width = `calc(100% - ${(COMPACT_LAYOUT.inset-margin)*2}px)`;
    element.style.marginInline = `${COMPACT_LAYOUT.inset-margin}px`;
    element.style.textIndent = "0";
    element.style.lineHeight = "18px";
    element.style.fontFamily=nodeTypography(node).family;
    element.style.fontWeight="400";
    }
}

function orderPresentationWidgets(node) {
    // LiteGraph paints widgets in array order. Keep the summary directly below
    // sockets and place advanced-only controls below their disclosure. Saved
    // positional values from the prior order are restored by name on configure.
    const control = (node.widgets || []).find((item) =>
        (item.name === "randomize" || /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`)),
    );
    const leading = [
        node.__orvSummary,
        widget(node, "model"), widget(node, "inference_method"), ...creativeTextWidgets(node, true),
        widget(node, "resolution"), widget(node, "aspect_ratio"),
        widget(node, "duration"), widget(node, "seed"),
        widget(node, "generate_audio"), node.__orvAdvanced,
        widget(node, "size"), control,
    ].filter(Boolean);
    const used = new Set(leading);
    // Keep persisted fixed-control tails ahead of nonserialized provider rows.
    const fixed=(node.widgets || []).filter(item=>!used.has(item) && !item.__orvProviderOption);
    const grouped=["voice","appearance","advanced"].flatMap(group=>[
        widget(node,`provider_group:${group}`),
        ...(node.widgets || []).filter(w=>w.__orvProviderOption && !w.__orvProviderHeading && !w.__orvTextSemantic && w.__orvProviderGroup===group)
    ]).filter(item=>item && !used.has(item));
    for(const item of [...fixed,...grouped])used.add(item);
    const ordered = [...leading,...fixed,...grouped, ...(node.widgets || []).filter((item) => !used.has(item))];
    if (ordered.some((item, index) => item !== node.widgets[index])) {
        // Keep the array identity: Comfy's widget layer may retain the
        // original array while the node definition is being configured.
        node.widgets.splice(0, node.widgets.length, ...ordered);
        return true;
    }
    return false;
}

function installSemanticSerialization(node) {
    if(node.__orvNamedSerializationInstalled)return;
    node.__orvNamedSerializationInstalled=true;
    const previous=node.onSerialize;
    node.onSerialize=function(data,...args){
        const result=previous?.call(this,data,...args);
        if(!data || typeof data!=="object")return result;
        const names=["model","inference_method","prompt","resolution","aspect_ratio","duration","size","seed","generate_audio","first_frame_url","last_frame_url","geometry_authority","previous_job_id","upscale_factor","creativity","provider_options"];
        const named={...(data.widgets_values_named || {})};
        for(const name of names){const item=widget(this,name);if(item)named[name]=item.value;}
        const control=(this.widgets || []).find(item=>(item.name === "randomize" || /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`)));
        if(control) {
            const modes=["fixed","increment","decrement","randomize"];
            if (control.value==null && modes.includes(this.__orvRestoredSeedMode)) {
                // Native copy serializes a temporary, not-yet-attached clone.
                // A transient empty binding must not erase explicit saved intent.
                control.value=this.__orvRestoredSeedMode;
                if(Array.isArray(data.widgets_values))data.widgets_values[this.widgets.indexOf(control)]=control.value;
            }
            if(modes.includes(control.value))this.__orvRestoredSeedMode=control.value;
            named[control.name]=control.value;
        }
        data.widgets_values_named=named;
        return result;
    };
}

function applyPresentation(node) {
    installSemanticSerialization(node);
    suppressPackageBadge(node);
    installNodeTypography(node);
    if(node.__orvSummary && node.__orvCapability?.__methodProfile)setVisible(node.__orvSummary,referenceCapacity(node).visible);
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
        suppressPackageBadge(this);
        if(this.__orvProviderProfile && this.__orvProviderLocale!==costLocale())configureOperationControls(this,this.__orvProviderProfile);
        const reordered = orderPresentationWidgets(this);
        const advancedChanged = syncAdvancedControls(this);
        const returningToClassic = Number.isFinite(this.__orvNativeFixedHeight)
            && app.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") === false;
        if (reordered || advancedChanged || returningToClassic) {
            fitPresentationWidth(this);
        }
        previousDraw?.call(this, ctx, ...args);
        if (this.flags?.collapsed) {
            drawCollapsedCostBadge(this, ctx);
            return;
        }
        const width = this.size?.[0] || 460;
        checkNativeCostMetadata(this);
        expireCostPresentation(this);
        const badge = costBadgeLabel(this, width * 0.5 - 24);
        const colors = costBadgeColors(this, badge);
        ctx.save();
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(0.75, -29, width - 1.5, (this.size?.[1] || 0) + 28, 10);
        else ctx.rect(0.75, -29, width - 1.5, (this.size?.[1] || 0) + 28);
        ctx.strokeStyle = "#328761";
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.font = `600 11px ${nodeTypography(node).family}`;
        const badgeWidth = Math.min(width * 0.5, ctx.measureText(badge).width + 24);
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(width - badgeWidth - 10, -27, badgeWidth, 21, 6);
        else ctx.rect(width - badgeWidth - 10, -27, badgeWidth, 21);
        ctx.fillStyle = colors.background || "#27302f";
        ctx.strokeStyle = colors.accent || "#60706c";
        ctx.fill();
        ctx.stroke();
        ctx.textAlign = "right";
        ctx.fillStyle = colors.accent || "#aeb8b6";
        drawCostBadgeLabel(this, ctx, badge, width - 22, -12, badgeWidth - 18);
        ctx.restore();
        syncClassicCostBadge(this, ctx, { x: width - badgeWidth - 10, y: -27, width: badgeWidth, height: 21 });
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
        if ((item.name === "randomize" || /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`))) {
            item.options ||= {};
            Object.assign(item.options, { advanced: false });
            item.options.getOptionLabel ||= value => ({
                fixed:"Fixed", increment:"Increment", decrement:"Decrement", randomize:"Randomize",
            })[value] ?? String(value ?? "");
            const label = costLocale() === "ru" ? "Управление после генерации" : "Control After Generate";
            if (item.label !== label) item.label = label;
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
        try {
            const measured = previousCompute?.apply(this, args);
            if (measured) measured[0] = 320; // Shared floor for native control/slot columns; labels never set node width.
            return measured;
        }
        finally { this.__orvMeasuringMinimum = false; }
    };
    const previousResize = node.onResize;
    // Only a trusted pointer sample calls this writer. onResize is a notification,
    // including when a programmatic callback interleaves with a user gesture.
    node.__orvCommitResizeIntent = (width,height,textBudget) => {
        if (!Number.isFinite(width) || !Number.isFinite(height) || node.__orvAutomaticLayout || node.__orvConfiguringMedia) return;
        delete node.__orvRestoreGeometry;
        node.__orvPreferredWidth = Math.max(320,width);
        const minimum = node.computeSize?.()?.[1];
        if (Number.isFinite(minimum)) persistMasterPromptHeight(node,masterHeightFromRegion(node,Number.isFinite(textBudget) ? textBudget : textRegionGeometry(node).min+height-minimum));
    };
    node.onResize = function (size, ...args) {
        if(this.__orvApplyingLiveResize){previousResize?.call(this,size,...args);return;}
        const dispatch=this.__orvResizeDispatch;
        if (dispatch && !dispatch.used && app.canvas?.pointer?.eMove===dispatch.event && !this.__orvAutomaticLayout) {
            dispatch.used=true;
            this.__orvCommitResizeIntent(size[0],size[1],Math.abs(size[1]-dispatch.height)<0.01 ? dispatch.budget : undefined);
            this.__orvLiveSize=Array.from(size);
            this.__orvLivePromptHeight=this.__orvMasterPromptHeight;
            scheduleResizeLayout(this);
        }
        if (this.__orvRestoreGeometry) {
            previousResize?.call(this,size,...args);
            return;
        }
        const minimum = this.computeSize?.()?.[1];
        if (Number.isFinite(minimum)) size[1] = Math.max(size[1], minimum);
        if (!this.__orvConfiguringMedia && Number.isFinite(this.__orvPreferredWidth) && Number.isFinite(minimum)) {
            size[0] = this.__orvPreferredWidth;
            size[1] = Number.isFinite(this.__orvNativeFixedHeight)
                ? this.__orvNativeFixedHeight + textRegionGeometry(this,this.__orvNativeTextMinimum).budget
                : minimum + textRegionGeometry(this).budget - textRegionGeometry(this).min;
        }
        size[0] = Math.max(320,size[0]);
        previousResize?.call(this, size, ...args);
    };
    const canvas=app.canvas?.canvas;
    if (canvas?.addEventListener) {
        let origin=null, nativeDrag=null, ownedDrag=null;
        const start=event=>{
            if (!event.isTrusted || event.button!==0 || app.canvas?.read_only || node.flags?.pinned || node.resizable===false || app.canvas?.graph?.getNodeById?.(node.id)!==node) return;
            const point=Number.isFinite(event.canvasX) && Number.isFinite(event.canvasY) ? [event.canvasX,event.canvasY] : app.canvas.convertEventToCanvasOffset?.(event);
            if(!point)return;
            const corner=node.findResizeDirection?.(point[0],point[1]);
            if (!["SE","SW","NE","NW"].includes(corner) ) return;
            origin={x:point[0],y:point[1],width:node.size[0],height:node.size[1],corner,id:event.pointerId,budget:textRegionGeometry(node).budget};
            const pointer=app.canvas?.pointer;
            if (typeof pointer?.onDrag!=="function") { origin=null; return; }
            nativeDrag=pointer.onDrag;
            ownedDrag=function(event){
                if (!origin || !event.isTrusted || event.pointerId!==origin.id) return nativeDrag?.call(this,event);
                // Authority exists only on the synchronous native drag stack.
                // A capture-listener microtask is too early: it runs before the
                // native target listener. Deferred callbacks must stay excluded.
                const dispatch={event,used:false,height:origin.height,budget:origin.budget};
                node.__orvResizeDispatch=dispatch;
                try { return nativeDrag.call(this,event); }
                finally { if(node.__orvResizeDispatch===dispatch)delete node.__orvResizeDispatch; }
            };
            pointer.onDrag=ownedDrag;
            node.__orvUserResizeActive=true;
        };
        const move=()=>{};
        const end=()=>{
            if(app.canvas?.pointer?.onDrag===ownedDrag)app.canvas.pointer.onDrag=nativeDrag;
            origin=null;nativeDrag=null;ownedDrag=null;
            delete node.__orvResizeDispatch;delete node.__orvLiveSize;delete node.__orvLivePromptHeight;node.__orvUserResizeActive=false;
        };
        canvas.addEventListener("pointerdown",start,true);canvas.addEventListener("pointermove",move,true);
        // Observe completion before native target handlers can stop propagation.
        // Otherwise a finished Classic drag can leave Vue in live-flex mode.
        canvas.addEventListener("pointerup",end,true);canvas.addEventListener("pointercancel",end,true);
        const removed=node.onRemoved;
        node.onRemoved=function(...args){
            end();this.__orvRemoved=true;if(typeof cancelAnimationFrame==="function")cancelAnimationFrame(this.__orvResizeFrame);canvas.removeEventListener("pointerdown",start,true);canvas.removeEventListener("pointermove",move,true);
            canvas.removeEventListener("pointerup",end,true);canvas.removeEventListener("pointercancel",end,true);
            return removed?.apply(this,args);
        };
    }
}

function fitPresentationWidth(node) {
    if (node.__orvUserResizeActive) return;
    if (app.ui?.settings?.getSettingValue && !app.ui.settings.getSettingValue("Comfy.VueNodes.Enabled")) {
        delete node.__orvNativeFixedHeight;
        delete node.__orvNativeTextMinimum;
    }
    const measured = node.computeSize?.();
    if (!measured) return;
    if (node.__orvConfiguringMedia) return;
    if (node.__orvRestoreGeometry) {
        if (!node.__orvCapability?.__methodProfile) return; // Decode saved total height only against hydrated controls.
        if (app.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled") && !Number.isFinite(node.__orvNativeFixedHeight)) return;
        node.__orvPreferredWidth = Math.max(320,node.__orvRestoreGeometry[0]);
        if(!Number.isFinite(node.__orvMasterPromptHeight)) {
            const saved=node.properties?.orv_prompt_geometry;
            persistMasterPromptHeight(node,saved?.version===2 && Number.isFinite(saved.height) ? saved.height : masterHeightFromRegion(node,
                Number.isFinite(node.__orvNativeFixedHeight) ? node.__orvRestoreGeometry[1]-node.__orvNativeFixedHeight
                : textRegionGeometry(node).min+node.__orvRestoreGeometry[1]-measured[1]));
        }
        delete node.__orvRestoreGeometry;
    }
    let width = node.__orvPreferredWidth ?? (Number.isFinite(node.size?.[0]) && node.size[0] > 0 ? node.size[0] : COMPACT_LAYOUT.width);
    if (!node.__orvPresentationWidthInitialized) {
        if (node.__orvIsNewNode) width = Math.max(COMPACT_LAYOUT.width, width);
        node.__orvPresentationWidthInitialized = true;
    }
    width = Math.fround(Math.max(320,width));
    node.__orvPreferredWidth = width;
    if (!Number.isFinite(node.__orvMasterPromptHeight)) {
        const stored=node.properties?.orv_prompt_geometry;
        persistMasterPromptHeight(node,stored?.version===2 && Number.isFinite(stored.height) ? stored.height : masterHeightFromRegion(node,textRegionGeometry(node).min+(node.size?.[1] || 0)-measured[1]));
    }
    const region = textRegionGeometry(node, node.__orvNativeTextMinimum);
    const height = Math.fround(Number.isFinite(node.__orvNativeFixedHeight)
        ? node.__orvNativeFixedHeight+region.budget : measured[1]+region.budget-region.min);
    if (node.size?.[0] !== width || node.size?.[1] !== height) {
        node.__orvAutomaticLayout = true;
        try { node.setSize?.([width, height]); }
        finally { node.__orvAutomaticLayout = false; }
    }
}

function createEstimateState() {
    let value = costText("invalidBadge");
    const state = { result: { state: "INVALID", reason_codes: ["select_model"] } };
    return Object.defineProperty(state, "value", {
        get: () => value,
        set: (next) => {
            if (String(next).startsWith("ESTIMATE UNAVAILABLE")) {
                value = costText("unknownBadge");
                state.result = { state: "UNKNOWN", reason_codes: ["current_configuration_unresolved"] };
            } else value = next;
            scheduleBetaPresentation();
        },
    });
}

function scheduleBetaPresentation(nodes = installBetaPresentation.nodes) {
    if (!nodes) return;
    const dirty = installBetaPresentation.dirty ||= new Set();
    for (const node of nodes) dirty.add(node);
    if (!dirty.size || installBetaPresentation.pending) return;
    installBetaPresentation.pending = true;
    const flush = () => {
        installBetaPresentation.pending = false;
        const batch = [...dirty];
        dirty.clear();
        for (const node of batch) {
            if (installBetaPresentation.nodes.has(node)) syncBetaPresentation(node);
        }
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(flush);
    else queueMicrotask(flush);
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
            .orv-nodes2 { font-family:${nodeTypography().family}; }
            .orv-nodes2 [data-testid="node-widget"] :is(label,input,button,[role="combobox"]) { font-family:${nodeTypography().family}; font-size:12px; font-weight:400; line-height:20px; }
            .orv-nodes2 .orv-estimate { flex:0 1 auto; max-width:50%; overflow:hidden;
                text-overflow:ellipsis; white-space:nowrap; border:1px solid var(--border-color, #666);
                border-radius:6px; padding:1px 7px; color:var(--input-text, #ddd); font:600 11px/16px ${nodeTypography().family};
                cursor:pointer; font-variant-numeric:tabular-nums; }
            .orv-nodes2 .orv-estimate:focus-visible { outline:2px solid var(--input-text, #ddd); }
            .orv-nodes2 .orv-prompt-row { min-height:42px; }
            .orv-nodes2 .orv-prompt-row textarea { min-height:42px; height:100%;
                padding:4px 6px; margin:0; box-sizing:border-box; font:400 12px/18px ${nodeTypography().family}; overflow:auto; }
        `;
        document.head.append(style);
        installBetaPresentation.observer = new MutationObserver(records => {
            const selector = ".lg-node[data-node-id]";
            const dirty = new Set();
            const graph = app.canvas?.graph || app.graph;
            for (const record of records) {
                const root = record.target.closest?.(selector);
                if (root) {
                    const changed = graph?.getNodeById?.(root.dataset.nodeId);
                    if (installBetaPresentation.nodes.has(changed)) dirty.add(changed);
                    continue;
                }
                // Renderer or graph replacement can mount/unmount several nodes
                // together. Ordinary menus, tooltips and sidebars cannot.
                const changedRoots = [...record.addedNodes, ...record.removedNodes].some(
                    element => element.matches?.(selector) || element.querySelector?.(selector),
                );
                if (changedRoots) {
                    scheduleBetaPresentation();
                    return;
                }
            }
            scheduleBetaPresentation(dirty);
        });
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
    scheduleBetaPresentation([node]);
}

function referenceCapacity(node) {
    // Read the same authoritative active projection as topology and ACI. Never
    // derive capacities by parsing prose or summing independent kind maxima.
    const raw=node.__orvCapability?.__methodProfile?.topology;
    const kinds=selectedReferenceKinds(node);
    const topology=raw ? applyTransportInputConstraints(raw,inputByName(node,"source_video")?.link!=null) : null;
    const verified=topology && !["UNKNOWN","CONFLICT"].includes(topology.constraint_state) && topology.execution_domain!=="UNVERIFIED";
    const limit=verified && Number.isSafeInteger(topology.max) && topology.max>=0 ? topology.max : null;
    const modalities=(topology?.reference_kinds || []).filter(kind=>["image","video","audio"].includes(kind)).map(kind=>({
        kind,active:Array.isArray(kinds) ? kinds.filter(k=>k===kind).length : null,
        limit:verified && Number.isSafeInteger(topology.per_kind_max?.[kind]) ? topology.per_kind_max[kind] : null
    }));
    const stored=node.properties?.orv_capability_intent?.media || [];
    const parked=stored.filter(item=>item?.active_name===null).length;
    const active=Array.isArray(kinds) ? kinds.length : null;
    return {active,limit,modalities,parked,visible:modalities.length>0 || parked>0,
        utilization:limit>0 && active!=null ? Math.max(0,Math.min(1,active/limit)) : null};
}

function capacityMeterHeight(node) {
    const data=referenceCapacity(node);
    return COMPACT_LAYOUT.row*2+COMPACT_LAYOUT.gap*2+3+(data.parked?COMPACT_LAYOUT.row:0);
}

function drawCapacityMeter(ctx,node,width,y) {
    const data=referenceCapacity(node),left=COMPACT_LAYOUT.inset,right=width-left;
    ctx.save();ctx.font=`400 ${nodeTypography(node).size}px ${nodeTypography(node).family}`;ctx.fillStyle="#C4C4C4";ctx.textAlign="left";
    ctx.fillText(costLocale()==="ru"?"Референсы":"References",left,y+15);
    ctx.textAlign="right";ctx.fillText(`${data.active??"?"} / ${data.limit??"?"}`,right,y+15);
    const track=y+COMPACT_LAYOUT.row+COMPACT_LAYOUT.gap;
    ctx.fillStyle="#44494b";ctx.fillRect(left,track,Math.max(0,right-left),3);
    if(data.utilization!=null){ctx.fillStyle="#B6BBBD";ctx.fillRect(left,track,Math.max(0,right-left)*data.utilization,3);}
    const top=track+3+COMPACT_LAYOUT.gap+14;
    data.modalities.forEach((item,index)=>{
        ctx.fillStyle="#B6BBBD";ctx.textAlign=index===0?"left":index===data.modalities.length-1?"right":"center";
        const x=data.modalities.length===1?left:left+(right-left)*index/(data.modalities.length-1);
        ctx.fillText(`${item.kind.toUpperCase()} ${item.active??"?"}/${item.limit??"?"}`,x,top);
    });
    if(data.parked){ctx.textAlign="right";ctx.fillStyle="#FFBB00";ctx.fillText(`${data.parked} ${costLocale()==="ru"?"вне режима":"parked"}`,right,top+COMPACT_LAYOUT.row);}
    ctx.restore();
}

function syncCapacityMeter(node,row,input) {
    let meter=row.querySelector(".orv-capacity-summary");
    if(!meter){
        meter=document.createElement("div");meter.className="orv-capacity-summary";
        // Share the native full-width widget columns, including their gutter.
        Object.assign(meter.style,{gridColumn:"2 / -1",minWidth:"0",font:`400 12px/20px ${nodeTypography(node).family}`,color:"#C4C4C4"});
        const title=document.createElement("div"),name=document.createElement("span"),count=document.createElement("span");
        Object.assign(title.style,{display:"flex",justifyContent:"space-between",gap:"8px"});title.append(name,count);
        const track=document.createElement("div"),fill=document.createElement("div");Object.assign(track.style,{height:"3px",margin:"4px 0",background:"#44494b"});Object.assign(fill.style,{height:"3px",background:"#B6BBBD"});track.append(fill);
        const kinds=document.createElement("div");Object.assign(kinds.style,{display:"flex",justifyContent:"space-between",gap:"8px",flexWrap:"wrap"});
        const parked=document.createElement("div");Object.assign(parked.style,{textAlign:"right",color:"#FFBB00"});
        meter.append(title,track,kinds,parked);meter.__orvParts={name,count,track,fill,kinds,parked};row.append(meter);
    }
    input.style.display="none";
    const data=referenceCapacity(node),parts=meter.__orvParts;
    if(!parts)return;
    const name=costLocale()==="ru"?"Референсы":"References";if(parts.name.textContent!==name)parts.name.textContent=name;
    const count=`${data.active??"?"} / ${data.limit??"?"}`;if(parts.count.textContent!==count)parts.count.textContent=count;
    parts.track.setAttribute("role",data.utilization==null?"status":"meter");
    if(data.utilization!=null){parts.track.setAttribute("aria-valuenow",String(data.active));parts.track.setAttribute("aria-valuemax",String(data.limit));}
    else {parts.track.removeAttribute?.("aria-valuenow");parts.track.removeAttribute?.("aria-valuemax");}
    parts.fill.style.width=data.utilization==null?"0%":`${data.utilization*100}%`;
    const signature=JSON.stringify(data.modalities);
    if(meter.__orvKinds!==signature){
        parts.kinds.replaceChildren?.();
        for(const item of data.modalities){const text=document.createElement("span");text.textContent=`${item.kind.toUpperCase()} ${item.active??"?"}/${item.limit??"?"}`;parts.kinds.append(text);}
        meter.__orvKinds=signature;
    }
    const parked=data.parked?`${data.parked} ${costLocale()==="ru"?"вне режима":"parked"}`:"";if(parts.parked.textContent!==parked)parts.parked.textContent=parked;
    parts.parked.style.display=data.parked?"":"none";
}

function capacitySummaryText(node) {
    const data=referenceCapacity(node);
    return `${costLocale()==="ru"?"Референсы":"References"} ${data.active??"?"} / ${data.limit??"?"}`+
        (data.modalities.length?" · "+data.modalities.map(item=>`${item.kind.toUpperCase()} ${item.active??"?"}/${item.limit??"?"}`).join(" · "):"")+
        (data.parked?` · ${data.parked} ${costLocale()==="ru"?"вне режима":"parked"}`:"");
}

function capacitySummaryLines(node, width) {
    // Conservative screen-space text budget shared by measurement and Classic drawing.
    const budget = Math.max(8, Math.floor((Math.max(80,width || 400) - 24) / 8));
    const lines = []; let line = "";
    for (const word of capacitySummaryText(node).split(/\s+/)) {
        if (line && line.length + word.length + 1 > budget) { lines.push(line); line = ""; }
        line = line ? `${line} ${word}` : word;
    }
    if (line) lines.push(line);
    return lines;
}

function syncBetaPresentation(node) {
    const activeGraph = app.canvas?.graph || app.graph;
    if (node.graph && activeGraph?.getNodeById?.(node.id) !== node) {
        if (node.__orvClassicCostBadge) node.__orvClassicCostBadge.hidden = true;
        node.__orvCostPopover?.remove();
        node.__orvCostPopover = null;
        return;
    }
    const root = [...document.querySelectorAll(".lg-node[data-node-id]")].find(
        (element) => element.dataset.nodeId === String(node.id),
    );
    if (!root) return; // Classic has no Vue node DOM; never touch its canvas.
    if (node.__orvClassicCostBadge) {
        node.__orvClassicCostBadge.hidden = true;
        if (node.__orvCostPopoverOwner === node.__orvClassicCostBadge) {
            node.__orvCostPopover?.remove();
            node.__orvCostPopover = null;
            node.__orvCostPopoverOwner = null;
        }
    }
    if(!node.__orvResumeActualInstalled && node.__orvProviderProfile && node.__orvProviderLocale!==costLocale())configureOperationControls(node,node.__orvProviderProfile);
    root.classList.add("orv-nodes2");
    suppressPackageBadge(node,root);
    const header = root.querySelector(".lg-node-header > div");
    if (header && (!node.graph || (app.canvas?.graph || app.graph)?.getNodeById?.(node.id) === node)) {
        checkNativeCostMetadata(node);
        let badge = header.querySelector(".orv-estimate");
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "orv-estimate";
            header.append(badge);
            bindCostBadge(node, badge);
        }
        expireCostPresentation(node);
        const text = costBadgeLabel(node, (node.size?.[0] || 400) * 0.5 - 20);
        setCostBadgeLabel(node, badge, text);
        const colors = costBadgeColors(node, text);
        badge.style.color = colors.accent;
        badge.style.borderColor = colors.accent;
        badge.style.backgroundColor = colors.background;
        badge.removeAttribute?.("title");
        badge.setAttribute("aria-label", costDetailsText(node));
    }
    if (node.__orvResumeActualInstalled) {
        root.__orvGeometryCleanup?.();
        delete root.__orvGeometryOwner;
        delete root.__orvGeometryCleanup;
        return;
    } // Resume adds cost disclosure only, no Generate geometry treatment.
    if (root.__orvGeometryOwner !== node && root.addEventListener) {
        root.__orvGeometryCleanup?.();
        const previousMinWidth=root.style?.minWidth || "";
        const nativeGrid=root.querySelector('[data-testid="node-widgets"]');
        const previousGrid=nativeGrid?.style ? [nativeGrid.style.gridTemplateColumns || "",nativeGrid.style.gridTemplateRows || "",nativeGrid.style.flex || ""] : null;
        const touched=new Map();
        root.__orvRememberGeometry=(element,keys,title=false)=>{
            for (const prior of touched.keys()) if (prior.isConnected===false) touched.delete(prior);
            if (!element?.style || touched.has(element)) return;
            touched.set(element,{styles:Object.fromEntries(keys.map(key=>[key,element.style[key] || ""])),title,originalTitle:element.title || ""});
        };
        root.style && (root.style.minWidth = "320px");
        root.__orvGeometryOwner = node;
        let origin=null, moveTarget=null;
        const start = event => {
            if (event.isTrusted && event.button === 0 && event.target?.closest?.('[data-corner]')) {
                const corner=event.target.closest('[data-corner]').dataset?.corner;
                const rect=root.getBoundingClientRect?.();
                const scale=rect?.width/node.size?.[0];
                if (!["SE","SW","NE","NW"].includes(corner) || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY) || !(scale>0)) return;
                const fields=[...(root.querySelectorAll?.(".orv-prompt-row") || [])];
                const regionHeight=fields.length ? fields.reduce((sum,row)=>sum+row.getBoundingClientRect().height/scale,0)+Math.max(0,fields.length-1)*COMPACT_LAYOUT.gap : textRegionGeometry(node,node.__orvNativeTextMinimum).budget;
                origin={height:node.size[1],totalHeight:rect.height/scale,regionHeight,budget:textRegionGeometry(node).budget,id:event.pointerId};
                node.__orvUserResizeActive = true;
                // Native startResize must measure the unchanged start rectangle.
                // Switching the grid to flex here would move its drag origin.
            }
        };
        const move = event => {
            if (!origin || !event.isTrusted || event.pointerId!==origin.id || root.__orvGeometryOwner!==node) return;
            const intent=origin;
            // useNodeResize writes on window bubble. Sample synchronously after
            // that native listener, before unrelated deferred notifications.
            const width=parseFloat(root.style?.getPropertyValue?.("--node-width"));
            const height=parseFloat(root.style?.getPropertyValue?.("--node-height"));
            queueMicrotask(()=>{
                if (origin!==intent || root.__orvGeometryOwner!==node) return;
                // Native pointer handler writes these CSS dimensions in this
                // trusted dispatch (including its snapping/minimum rules).
                // onResize notifications and mutable node.size are not evidence.
                if (Number.isFinite(width) && Number.isFinite(height)) {
                    const delta=height-intent.totalHeight;
                    node.__orvCommitResizeIntent?.(width,intent.height+delta,Math.abs(delta)<0.01 ? intent.budget : intent.regionHeight+delta);
                    node.__orvLiveSize=[width,height];
                    node.__orvLivePromptHeight=masterHeightFromRegion(node,Math.max(0,intent.regionHeight+delta));
                    const apply=()=>{
                        if(origin!==intent || root.__orvGeometryOwner!==node)return;
                        node.__orvAutomaticLayout=true;node.__orvApplyingLiveResize=true;
                        try { if(node.size?.[0]!==Math.fround(width) || node.size?.[1]!==Math.fround(height)) node.setSize?.([Math.fround(width),Math.fround(height)]); }
                        finally { node.__orvAutomaticLayout=false;node.__orvApplyingLiveResize=false; }
                        syncBetaPresentation(node);node.setDirtyCanvas?.(true,true);
                    };
                    node.__orvPendingLiveLayout=apply;
                    if(node.__orvLiveFrame==null)node.__orvLiveFrame=requestAnimationFrame(()=>{node.__orvLiveFrame=null;node.__orvPendingLiveLayout?.();});
                }
            });
        };
        const captured = event => {
            if (!origin || !event.isTrusted || event.pointerId!==origin.id) return;
            // Capture is delivered after the native pointerdown has registered
            // its window drag handler. Observe that same native dispatch last.
            moveTarget?.removeEventListener?.("pointermove",move);
            moveTarget=root.ownerDocument?.defaultView || root;
            moveTarget.addEventListener("pointermove",move);
            syncBetaPresentation(node);
        };
        const finish = () => {
            moveTarget?.removeEventListener?.("pointermove",move);moveTarget=null;
            if (!node.__orvUserResizeActive) return;
            node.__orvPendingLiveLayout?.();
            if(node.__orvLiveFrame!=null && typeof cancelAnimationFrame==="function")cancelAnimationFrame(node.__orvLiveFrame);
            node.__orvLiveFrame=null;node.__orvPendingLiveLayout=null;
            origin=null;node.__orvUserResizeActive=false;
            delete node.__orvLiveSize;delete node.__orvLivePromptHeight;
            syncBetaPresentation(node);
        };
        root.addEventListener("pointerdown",start,true);
        root.addEventListener("gotpointercapture",captured,true);
        root.addEventListener("lostpointercapture",finish,true);
        root.addEventListener("pointercancel",finish,true);
        root.__orvGeometryCleanup = () => {
            node.__orvUserResizeActive = false;
            moveTarget?.removeEventListener?.("pointermove",move);moveTarget=null;
            origin=null;
            if(typeof cancelAnimationFrame==="function")cancelAnimationFrame(node.__orvLiveFrame);
            node.__orvPendingLiveLayout=null;node.__orvLiveFrame=null;
            delete node.__orvLiveSize;delete node.__orvLivePromptHeight;
            if (root.style) root.style.minWidth=previousMinWidth;
            if (previousGrid) [nativeGrid.style.gridTemplateColumns,nativeGrid.style.gridTemplateRows,nativeGrid.style.flex]=previousGrid;
            for (const [element,previous] of touched) {
                Object.assign(element.style,previous.styles);
                if (previous.title) element.title=previous.originalTitle;
            }
            root.querySelectorAll?.(".orv-duration-readonly").forEach(element=>element.remove());
            root.querySelectorAll?.(".orv-prompt-row").forEach(element=>element.classList.remove("orv-prompt-row"));
            delete node.__orvNativeFixedHeight;delete node.__orvNativeTextMinimum;
            touched.clear();delete root.__orvRememberGeometry;
            root.removeEventListener?.("pointerdown",start,true);
            root.removeEventListener?.("gotpointercapture",captured,true);
            root.removeEventListener?.("lostpointercapture",finish,true);
            root.removeEventListener?.("pointercancel",finish,true);
        };
    }
    if (!node.__orvUserResizeActive && !node.__orvRestoreGeometry) fitPresentationWidth(node);
    const duration = widget(node, "duration");
    if (duration?.__orvDurationAdapter && duration.options?.read_only) {
        const label = durationPresentationLabel(duration);
        if (duration.label !== label) duration.label = label;
    }
    const grid = root.querySelector('[data-testid="node-widgets"]');
    if (!grid) return;
    const rows = [...grid.querySelectorAll(':scope > [data-testid="node-widget"]')];
    const labelWidth = Math.max(112,Math.min(160,128+((presentationSize(node)[0] || 400)-400)/3));
    // Native subgrid owns controls and hit testing. Only its column budget changes.
    grid.style.gridTemplateColumns = `min-content ${labelWidth}px minmax(125px, 1fr)`;
    for (const row of rows) {
        if (row.style) {
            root.__orvRememberGeometry?.(row,["minWidth","gridColumn"]);
            row.style.minWidth = "0";
            row.style.gridColumn = "1 / -1";
        }
        const label = row.querySelector('[data-testid="widget-layout-field-label"]');
        if (label?.style) {
            root.__orvRememberGeometry?.(label,["maxWidth","overflow","textOverflow"],true);
            label.style.maxWidth = `${labelWidth}px`;
            label.style.overflow = "hidden";
            label.style.textOverflow = "ellipsis";
            label.title = label.textContent || "";
        }
    }
    for (const row of rows) {
        const input = row.querySelector('input[aria-label="REFERENCES"]');
        if (!input || !node.__orvSummary) continue;
        syncCapacityMeter(node,row,input);
    }
    const creative = creativeTextWidgets(node);
    const bindings = rows.map(row => {
        const textarea = row.querySelector("textarea");
        if (!textarea) return null;
        // Vue renders its own textarea, identified through its native associated
        // label. It is not the Classic widget.element and has no name/placeholder.
        const label = row.querySelector('label[for]') || row.querySelector('[data-testid="widget-layout-field-label"]');
        const text = label?.textContent?.trim();
        const item = creative.find(item => textarea === item.element || textarea.getAttribute?.("name") === item.name
            || text === (item.label || item.name));
        if (!item) { row.classList.remove?.("orv-prompt-row"); return null; }
        row.classList.add("orv-prompt-row");
        const display = creativeTextLabel(item);
        textarea.placeholder = display;
        textarea.setAttribute?.("aria-label",display);
        if (label) {
            root.__orvRememberGeometry?.(label,["display"]);
            label.style && (label.style.display = "none");
        }
        if (textarea.rows !== 2) textarea.rows = 2;
        return {row,textarea,item};
    });
    let minimum = COMPACT_LAYOUT.prompt;
    if (typeof getComputedStyle === "function") for (const binding of bindings.filter(Boolean)) {
        minimum = Math.max(minimum,parseFloat(getComputedStyle(binding.textarea).minHeight) || 0);
    }
    node.__orvNativeTextMinimum = minimum;
    const region = textRegionGeometry(node,minimum);
    const template = bindings.map(binding => !binding ? "max-content" : node.__orvUserResizeActive
        ? `minmax(${minimum}px, 1fr)` : `${region.field}px`).join(" ");
    if (grid.style.gridTemplateRows !== template) grid.style.gridTemplateRows = template;
    const flex = bindings.some(Boolean) ? (node.__orvUserResizeActive ? "1 1 auto" : "0 0 auto") : "";
    if (grid.style.flex !== flex) grid.style.flex = flex;
    for (const row of rows) {syncReadOnlyDurationRow(node,root,row);syncDurationSliderState(node,row);syncProviderNumericState(node,row);syncProviderGroupHeading(node,row);}
    const rect = root.getBoundingClientRect?.();
    const scale = rect?.width / presentationSize(node)[0];
    if (scale > 0 && bindings.filter(Boolean).length === region.count) {
        const intrinsic = nativeFlowHeight(root,scale);
        if (Number.isFinite(intrinsic) && intrinsic > 0 && !node.__orvUserResizeActive) {
            // Vue's measured perimeter includes the native title; Canvas size
            // excludes its bounding offset. Keep one authoritative node size.
            const titleOffset = Math.max(0,Number(node.boundingOffset?.[1]) || 0);
            node.__orvNativeFixedHeight = intrinsic-titleOffset-region.budget;
            const restoring = Boolean(node.__orvRestoreGeometry);
            fitPresentationWidth(node);
            if (restoring && !node.__orvRestoreGeometry) syncBetaPresentation(node);
        }
    }
}

function canonicalModel(node) {
    const item = widget(node, "model");
    const value = item?.value;
    return typeof value === "string" && value !== SELECT_MODEL ? value : null;
}

function modelDisplayLabel(value) { return String(value || "").replace(/\s+[—–]\s+/, ": "); }

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
        const name = String(modelDisplayLabel(model.display_name) || model.model_id);
        nameCounts.set(name, (nameCounts.get(name) || 0) + 1);
    }
    const entries = models.map((model) => {
        const name = String(modelDisplayLabel(model.display_name) || model.model_id);
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
        (item.name === "randomize" || /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`)),
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
        ["geometry_authority", 12], ["previous_job_id", 13],
        ["upscale_factor", 14], ["creativity", 15], ["provider_options", 16],
    ] : [
        ["model", 1], ["inference_method", 2], ["prompt", 3],
        ["resolution", 4], ["aspect_ratio", 5], ["duration", 6],
        ["seed", 7], ["generate_audio", 8], ["size", 10],
        ["first_frame_url", 12], ["last_frame_url", 13],
        ["geometry_authority", 14], ["previous_job_id", 15],
        ["upscale_factor", 16], ["creativity", 17], ["provider_options", 18],
    ];
    for (const [name, index] of fields) {
        const item = widget(node, name);
        if (item && index < serializedValues.length) item.value = serializedValues[index];
    }
    const control = (node.widgets || []).find((item) =>
        (item.name === "randomize" || /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`)),
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
        "last_frame_url", "geometry_authority", "previous_job_id",
        "upscale_factor", "creativity", "provider_options",
    ]) {
        if (Object.hasOwn(namedValues, name)) {
            const item = widget(node, name);
            if (item) item.value = namedValues[name];
        }
    }
    const control = (node.widgets || []).find((item) =>
        (item.name === "randomize" || /control[ _]?after[ _]?generate/i.test(`${item.name || ""} ${item.label || ""}`)),
    );
    if (control && Object.hasOwn(namedValues, control.name)) {
        control.value = namedValues[control.name];
        if (["fixed","increment","decrement","randomize"].includes(control.value)) node.__orvRestoredSeedMode=control.value;
        else delete node.__orvRestoredSeedMode;
    }
    if (typeof namedValues.model === "string" && namedValues.model !== SELECT_MODEL && METHODS.includes(namedValues.inference_method)) {
        // The serialized active values are newer than the parked method bank.
        // Native node recreation must not reapply that stale bank over them.
        const key=`${namedValues.model}|${namedValues.inference_method}`;
        const intent=capabilityIntent(node);
        intent.controls ||= {};
        const current={...(intent.controls[key] || {})};
        for (const name of ["resolution","aspect_ratio","duration","size","seed","generate_audio","geometry_authority","previous_job_id","upscale_factor","creativity","provider_options"]) {
            if (Object.hasOwn(namedValues,name)) current[name]=namedValues[name];
        }
        intent.controls[key]=current;
        node.__orvProjectedKey=key;
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
        if (connection.state !== "CONNECTED") {
            for (const node of connectionNodes()) if (node?.type === GENERATE_NODE)
                discardCurrentCost(node, "openrouter_connection_unavailable");
            return;
        }
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
        // Price-only cache refreshes need not change the capability projection.
        // Reuse this existing refresh event; never add an upstream call per widget.
        if (!changed) await Promise.all(nodes.filter(node => !node.__orvCatalogueFailed).map(node => {
            node.__orvCostAcceptedSignature = null;
            return refreshEstimate(node);
        }));
    })().catch(() => {
        for (const node of connectionNodes()) {
            if (node?.type === GENERATE_NODE) discardCurrentCost(node, "catalogue_refresh_unavailable");
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

function durationPresentationLabel(item) {
    return costText("durationLabel");
}

function readOnlyValueParts(item) {
    const duration = item.__orvDurationAdapter;
    const automatic = duration && item.__orvDurationPresentation === "AUTOMATIC";
    if (duration && !["FIXED","AUTOMATIC"].includes(item.__orvDurationPresentation)) {
        return {value:Number(item.value)>0 ? `${item.value}${costLocale()==="ru" ? " с" : " s"}` : "—",state:costText("unverifiedDuration")};
    }
    return {
        value: automatic ? (costLocale() === "ru" ? "Авто" : "Auto")
            : `${item.value}${duration ? (costLocale() === "ru" ? " с" : " s") : ""}`,
        state: automatic ? costText("automatic") : costText("fixedDuration"),
    };
}

function drawReadOnlyValue(node, item, ctx) {
    ctx.save?.();
    ctx.font=`400 ${nodeTypography(node).size}px ${nodeTypography(node).family}`;ctx.textBaseline="alphabetic";
    const width = item.width || node.size?.[0] || 400, y = item.y || 0;
    const left = 15+Math.max(112,Math.min(160,128+(width-400)/3))+8;
    const parts = readOnlyValueParts(item);
    ctx.fillStyle = item.background_color || "#303435";
    ctx.beginPath?.();ctx.roundRect?.(left,y,width-left-15,COMPACT_LAYOUT.row,6);ctx.fill?.();
    ctx.fillStyle = item.text_color || "#ddd";ctx.textAlign="left";
    ctx.fillText(item.__orvDurationAdapter ? durationPresentationLabel(item) : (item.label || item.name),15,y+14);
    ctx.fillText(parts.value,left+8,y+14);
    ctx.textAlign="right";ctx.fillStyle=item.secondary_text_color || "#aaa";
    ctx.fillText(parts.state,width-23,y+14);
    ctx.restore?.();
}

function syncReadOnlyDurationRow(node, root, row) {
    const input = row.querySelector('input');
    if (!input) return;
    const name = input.getAttribute?.("aria-label") || input.name;
    const item = widget(node,name);
    if (!item || !(item.__orvDurationAdapter || item.__orvFixedValue)) return;
    let display = row.querySelector(".orv-duration-readonly");
    const container = [...(row.children || [])].find(child => child.contains?.(input));
    // Native Vue widgets can group the label and input in one subgrid.
    // Hide only the input region so the native label keeps its own column.
    const nestedLabel = container?.querySelector('[data-testid="widget-layout-field-label"]');
    const cell = nestedLabel ? [...(container.children || [])].find(child => child.contains?.(input)) : container;
    if (!cell) return;
    if (!item.options?.read_only) {
        if (cell.__orvOriginalDisplay !== undefined) cell.style.display = cell.__orvOriginalDisplay;
        display?.remove();
        return;
    }
    if (cell.__orvOriginalDisplay === undefined) cell.__orvOriginalDisplay = cell.style.display || "";
    root.__orvRememberGeometry?.(cell,["display"]);
    cell.style.display = "none";
    if (!display) {
        display = document.createElement("div"); display.className = "orv-duration-readonly";
        display.setAttribute("role","status");
        Object.assign(display.style,{gridColumn:nestedLabel?"2 / -1":"3 / -1",display:"flex",alignItems:"center",justifyContent:"space-between",gap:"4px",minWidth:"0",minHeight:"28px",padding:"0 12px",borderRadius:"6px",background:"var(--component-node-widget-background, #303435)",color:"var(--component-node-foreground, #ddd)",font:"inherit"});
        const value = document.createElement("span"), state = document.createElement("span");
        Object.assign(state.style,{fontSize:"11px",padding:"1px 6px",borderRadius:"4px",background:"rgba(127,127,127,0.16)",whiteSpace:"nowrap"});
        display.append(value,state); (nestedLabel?container:row).append(display);
    }
    if (typeof getComputedStyle === "function") {
        const native = getComputedStyle(input);
        display.style.font = `400 ${nodeTypography(node).size}px/20px ${nodeTypography(node).family}`;
        display.style.borderRadius = native.borderRadius;
        if (parseFloat(native.height)>0) display.style.minHeight = native.height;
    }
    const parts = readOnlyValueParts(item);
    if (display.children[0].textContent !== parts.value) display.children[0].textContent = parts.value;
    if (display.children[1].textContent !== parts.state) display.children[1].textContent = parts.state;
}

function createDurationSlider(node, previous) {
    const index = node.widgets.indexOf(previous);
    const item = node.addWidget("slider", "duration", previous.value ?? 0, null, { min: 0, max: 1, step: 1, precision: 0 });
    item.__orvDurationAdapter = true;
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
    const numericDomain = () => item.__orvSliderDomain || item.__orvDomain || {kind:"UNKNOWN"};
    const nativeOptions = () => numericDomain().allowed_values ?
        { ...item.options, min: 0, max: Math.max(1, numericDomain().allowed_values.length - 1), step: 1 } : item.options;
    const trackWidth = width => item.__orvResetDuration ? width - 48 : width;
    const nativeDraw = item.drawWidget;
    const nativeClick = item.onClick;
    const nativeDrag = item.onDrag;
    const view = Object.create(item);
    Object.defineProperty(view, "value", { get() {
        const domain = numericDomain();
        return domain.allowed_values ? domain.allowed_values.indexOf(Number(item.value)) : Number(item.value);
    } });
    Object.defineProperty(view, "height", { value: COMPACT_LAYOUT.row });
    view.setValue = position => {
        if (item.options.read_only) return;
        const next = durationAtPosition(numericDomain(), position);
        if (next == null) return;
        item.value = next;
        item.callback?.(next);
        node.setDirtyCanvas?.(true, true);
    };
    // Delegate geometry, fill and pointer interaction to the public native slider.
    // Only its display coordinate differs from the product's semantic seconds.
    if (nativeDraw) item.drawWidget = function (ctx, options) {
        if (item.options.read_only) {
            drawReadOnlyValue(node,item,ctx);
            return;
        }
        view.y = item.y;
        view.options = nativeOptions();
        const width = options.width || item.width || node.size?.[0] || 400;
        const track = trackWidth(width);
        view.width = track;
        view.label = durationPresentationLabel(item);
        const auto = Number(item.value) === -1;
        const text = auto ? view.label : Number(item.value) > 0 ? `${view.label} ${item.value}${costLocale()==="ru"?" с":"s"}` : `${view.label} —`;
        const drawContext = new Proxy(ctx, { get(target, key) {
            if (key === "fillText") return (_nativeText, ...args) => target.fillText(text, ...args);
            const value = Reflect.get(target, key, target);
            return typeof value === "function" ? value.bind(target) : value;
        }, set(target, key, value) { target[key] = value; return true; } });
        nativeDraw.call(view, drawContext, {...options,width:track});
        if (item.__orvResetDuration && options.showText !== false) {
            ctx.save();
            ctx.fillStyle = item.text_color || "#ddd";
            ctx.textAlign = "center";
            ctx.fillText(auto ? providerAutoLabel({}) : "↺",width-36,view.y+COMPACT_LAYOUT.row*0.7);
            ctx.restore();
        }
    };
    if (nativeClick) item.onClick = event => {
        if (item.options.read_only) return;
        const width = item.width || node.size?.[0] || 400;
        if (item.__orvResetDuration && event.e && event.e.canvasX - node.pos[0] >= width-56) {
            return item.__orvResetDuration();
        }
        view.options = nativeOptions(); view.width = trackWidth(width);
        nativeClick.call(view,event);
    };
    if (nativeDrag) item.onDrag = event => {
        if (item.options.read_only) return false;
        view.options = nativeOptions(); view.width = trackWidth(item.width || node.size?.[0] || 400);
        return nativeDrag.call(view,event);
    };
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
    const domain = durationDomain(supported);
    const values = domain.allowed_values || [];
    const mixedAuto = values.length > 1 && values.includes(-1);
    const numericValues = mixedAuto ? values.filter(value => value > 0) : values;
    item.__orvSliderDomain = mixedAuto ? durationDomain(numericValues) : undefined;
    item.__orvResetDuration = mixedAuto ? () => {
        if (Number(item.value) === -1) return;
        item.value = -1;
        item.callback?.(-1);
        node.setDirtyCanvas?.(true,true);
    } : undefined;
    item.options ||= {};
    item.__orvDomain = domain;
    setVisible(item, !Array.isArray(supported) || supported.length > 0);
    const current = Number(item.value || 0);
    const valid = durationValueAllowed(domain, current);
    const linked = inputByName(node, "duration")?.link != null;
    if (!valid && domain.kind !== "UNKNOWN" && !linked) item.value = productDefault("duration", values.filter(value => value > 0)) ?? domain.min;
    const singleton = domain.kind !== "UNKNOWN" && domain.min === domain.max;
    const presentation = domain.kind === "UNKNOWN" ? "UNKNOWN" : singleton ?
        domain.min === -1 ? "AUTOMATIC" : "FIXED" : "VARIABLE";
    item.__orvDurationPresentation = presentation;
    const readOnly = presentation !== "VARIABLE";
    item.type = readOnly ? "text" : "slider";
    item.label = durationPresentationLabel(item);
    item.options.values = values;
    item.options.min = mixedAuto ? numericValues[0] : domain.min ?? 0;
    item.options.max = domain.max ?? 1;
    item.options.step = numericValues.length ? arithmeticStep(numericValues) ?? 1 : 10 ** -(domain.precision ?? 0);
    item.options.step2 = item.options.step;
    item.options.read_only = item.options.readOnly = item.options.disabled = readOnly;
    if (linked && !valid) disclose(node, "DURATION: linked value is outside the projected domain; correct the upstream value");
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

// ComfyUI 1.49.6 installs its own instance-level Autogrow callback for
// this schema. The backend schema stays intact; only the competing UI writer
// is removed from this node's registry. Never disable other groups or nodes.
function claimDirectReferenceTopology(node) {
    const groups = node.comfyDynamic?.autogrow;
    if (!groups || !Object.hasOwn(groups, "direct_references")) return true;
    const group = groups.direct_references;
    if (group?.prefix !== "reference_" || group.max !== 100 || group.min !== 0 ||
        group.inputSpecs?.length !== 1) {
        node.__orvReferenceInvalid = true;
        if (node.__orvCapabilityStatus) disclose(node, "UNSUPPORTED NATIVE REFERENCE TOPOLOGY; saved links preserved; Generate blocked");
        return false;
    }
    delete groups.direct_references;
    return true;
}

function normalizeImportedReferenceInputs(node) {
    const inputs = node.inputs || [];
    const aliases = inputs.filter(input => /^reference_\d+$/.test(input.name))
        .map(input => ({ input, name: `direct_references.${input.name}` }));
    const names = new Set(inputs.map(input => input.name)), targets = new Set(), aliasesSeen = new Set();
    node.__orvReferenceAliasConflict = false;
    for (const alias of aliases) {
        if (aliasesSeen.has(alias.input.name)) {
            node.__orvReferenceAliasConflict = true;
            node.__orvReferenceInvalid = true;
            return;
        }
        aliasesSeen.add(alias.input.name);
        // A native socket and an imported alias may coexist. Keep both
        // occurrences: choose a free wire name rather than merge their links.
        if (names.has(alias.name) || targets.has(alias.name)) {
            let index = Math.max(-1, ...inputs.filter(isDirectReferenceInput).map(referenceInputSuffix),
                ...aliases.map(item => referenceInputSuffix({ name: item.name }))) + 1;
            while (names.has(`direct_references.reference_${index}`) ||
                targets.has(`direct_references.reference_${index}`)) index++;
            alias.name = `direct_references.reference_${index}`;
        }
        targets.add(alias.name);
    }
    // Native inputs are hydrated at onConfigure. Rename only after validating
    // every alias, without replacing sockets or touching their slots/links.
    for (const { input, name } of aliases) input.name = name;
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
        scheduleTopologyRefresh(node, () => projectSelectedModel(node));
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

function providerObjectIssue(spec, values, path = [], rootKey = "") {
    const descendants = values.filter(v => path.every((key, index) => v.path?.[index] === key));
    if (spec.type === "array") {
        if (!descendants.length) return "";
        const count = Math.max(...descendants.map(v=>v.path[path.length]))+1;
        if (count < spec.min_items || count > spec.max_items) return "Provider array count is outside the supported range.";
        for (let index=0;index<count;index++) {
            const child=descendants.filter(v=>v.path[path.length]===index);
            if (!child.length) return "Complete each provider array item before Generate.";
            const issue=providerObjectIssue(spec.items,child,[...path,index],rootKey);
            if (issue) return issue;
        }
        return "";
    }
    if (spec.type !== "object") return spec.required && !descendants.some(v =>
        JSON.stringify(v.path || []) === JSON.stringify(path) && (typeof v.value !== "string" || v.value.trim()))
        ? (costLocale()==="ru" ? `Заполните ${providerControlLabel(spec,rootKey,path)} перед генерацией.` : `Enter ${providerControlLabel(spec,rootKey,path)} before generation.`) : "";
    if (!descendants.length) return "";
    const present = key => descendants.some(v => v.path?.[path.length] === key &&
        (typeof v.value !== "string" || v.value.trim()));
    const discriminator = spec.variants?.discriminator_field;
    const selected = discriminator && descendants.find(v => JSON.stringify(v.path) === JSON.stringify([...path,discriminator]))?.value;
    const variant = spec.variants?.cases?.[selected];
    for (const key of [...(spec.required_fields || []), ...(variant?.required_fields || [])])
        if (!present(key)) return costLocale()==="ru" ? `Заполните ${providerControlLabel(spec.fields[key],rootKey,[...path,key])} перед генерацией.` : `Enter ${providerControlLabel(spec.fields[key],rootKey,[...path,key])} before generation.`;
    for (const group of [...(spec.one_of_required || []), ...(variant?.one_of_required || [])])
        if (group.filter(present).length !== 1) return (costLocale()==="ru" ? "Укажите один источник: " : "Choose exactly one source: ")+group.map(key=>providerControlLabel(spec.fields[key],rootKey,[...path,key])).join(" / ")+".";
    for (const [key, child] of Object.entries(spec.fields || {})) {
        const issue = providerObjectIssue(child, descendants, [...path,key],rootKey);
        if (issue) return issue;
    }
    return "";
}

function providerControlLabel(spec, key, path = []) {
    const label=spec?.presentation?.label;
    if(label)return label[costLocale()] || label.en;
    return [key,...path].map(part=>String(part).replace(/([a-z])([A-Z])/g,"$1 $2").replaceAll("_"," "))
        .join(" ").replace(/\b(id|url|tts|api)\b/gi,word=>word.toUpperCase()).replace(/(^|\s)\S/g,word=>word.toUpperCase());
}

function providerAutoLabel(spec) {
    const word=costLocale()==="ru"?"Авто":"Auto";
    return spec.values?.includes(word) ? `${word} (${costLocale()==="ru"?"не передавать":"omit"})` : word;
}

function creativeTextLabel(item) {
    return item.name==="prompt" ? "prompt" : item.__orvCreativeLabel || (item.__orvTextSemantic==="negative_prompt" ? "negative prompt" : "prompt");
}

function updateProviderIntent(node, root, identity, entries, value, omit) {
    const {provider,key,container,path}=identity;
    const matches=v=>v.provider===provider && v.key===key && (v.container || null)===(container || null);
    const prefix=(entry,base)=>matches(entry) && base.every((p,i)=>entry.path?.[i]===p);
    const branchKey=(base,selected)=>JSON.stringify([node.__orvProjectedKey || canonicalModel(node),provider,container || null,key,base,selected]);
    const intent=capabilityIntent(node);intent.provider_variants ||= {};
    let spec=root,base=[];
    const ancestors=[];
    for(const part of path){ancestors.push({spec,base});spec=spec?.type==="array"?spec.items:spec?.fields?.[part];base=[...base,part];}
    const parent=ancestors.at(-1);
    if(parent?.spec?.variants && parent.spec.variants.discriminator_field===path.at(-1)){
        const base=parent.base,old=entries.find(v=>prefix(v,path) && v.path?.length===path.length)?.value;
        if(old!==undefined)intent.provider_variants[branchKey(base,old)]=entries.filter(v=>prefix(v,base) && JSON.stringify(v.path)!==JSON.stringify(path)).map(v=>({...v,path:[...v.path]}));
        entries=entries.filter(v=>!prefix(v,base));
        if(!omit){entries.push({provider,key,value,...(container?{container}:{}),...(path.length?{path}: {})});
            const restored=intent.provider_variants[branchKey(base,value)] || [];
            const leaves=providerOptionLeaves(root,[],[...entries,...restored]);
            for(const entry of restored){const active=leaves.find(leaf=>JSON.stringify(leaf.path)===JSON.stringify(entry.path));
                if(active && (!active.spec.values || active.spec.values.includes(entry.value)))entries.push(entry);}
        }
        return entries;
    }
    const discriminator=parent?.spec?.variants?.discriminator_field;
    const selected=discriminator && entries.find(entry=>matches(entry) && JSON.stringify(entry.path)===JSON.stringify([...parent.base,discriminator]))?.value;
    const exclusive=[...(parent?.spec?.one_of_required || []),...(parent?.spec?.variants?.cases?.[selected]?.one_of_required || [])];
    if(!omit) for(const group of exclusive){
        if(!group.includes(path.at(-1)))continue;
        entries=entries.filter(entry=>{
            if(prefix(entry,parent.base) && group.includes(entry.path?.[parent.base.length]) && entry.path?.[parent.base.length]!==path.at(-1)){
                intent.provider_variants[branchKey(entry.path,"exclusive")]=[{...entry,path:[...entry.path]}];return false;
            }return true;
        });
    }
    entries=entries.filter(v=>!(matches(v) && JSON.stringify(v.path || [])===JSON.stringify(path)));
    if(!omit)entries.push({provider,key,value,...(container?{container}:{}),...(path.length?{path}: {})});
    return entries;
}

function installProviderResetMenu(node) {
    if(node.__orvProviderMenuInstalled)return;
    node.__orvProviderMenuInstalled=true;
    const previous=node.getExtraMenuOptions;
    node.getExtraMenuOptions=function(canvas,options,...args){
        const result=previous?.call(this,canvas,options,...args);
        const items=(this.widgets || []).filter(item=>!item.hidden && item.__orvResetProvider).map(item=>({
            content:`${item.label}: ${costLocale()==="ru"?"сбросить в Авто":"reset to Auto"}`,callback:()=>item.__orvResetProvider()
        }));
        const target=Array.isArray(result)?result:options;
        if(items.length)target.push({content:costLocale()==="ru"?"Параметры провайдера":"Provider controls",submenu:{options:items}});
        return result;
    };
}

function providerControlGroups(node) {
    const groups=["voice","appearance","advanced"];
    for(const name of groups){
        const items=(node.widgets || []).filter(w=>w.__orvProviderOption && !w.hidden && w.__orvProviderGroup===name && !w.__orvTextSemantic);
        const labels={voice:["Voice","Голос"],appearance:["Appearance","Внешний вид"],advanced:["Other Controls","Другие параметры"]};
        let heading=widget(node,`provider_group:${name}`);
        if(items.length>=3 && !heading){heading=addReadOnlyWidget(node,`provider_group:${name}`,"");heading.__orvProviderOption=true;heading.__orvProviderGroup=name;heading.__orvProviderHeading=true;
            heading.draw=(ctx,n,width,y)=>{ctx.save();ctx.font=`600 11px ${nodeTypography(n).family}`;ctx.fillStyle="#999";ctx.textAlign="left";ctx.fillText(heading.label,15,y+14);ctx.restore();};}
        if(heading){heading.label=labels[name][costLocale()==="ru"?1:0];setVisible(heading,items.length>=3);}
    }
}

function configureOperationControls(node, profile) {
    node.__orvProviderProfile = profile;
    node.__orvProviderLocale=costLocale();
    installProviderResetMenu(node);
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
    const inactive = new Set((node.widgets || []).filter(item =>
        item.__orvProviderOption || item.name?.startsWith("provider_option:")));
    const hideInactive = () => {
        for (const item of inactive) {
            item.__orvProviderOption = true;
            setVisible(item, false);
        }
    };
    let saved;
    try { saved = storage.value ? JSON.parse(storage.value) : []; }
    catch { saved = null; }
    if (!Array.isArray(saved) || saved.some(v => !v || typeof v !== "object")) {
        hideInactive();
        return "Invalid saved provider controls; repair before Generate.";
    }
    const providers = controls.provider_options?.state === "SUPPORTED" ? controls.provider_options.providers || {} : {};
    const activeLeaf = v => providerOptionLeaves(providers[v.provider]?.[v.key], [], saved.filter(other =>
        other.provider === v.provider && other.key === v.key && (other.container || null) === (v.container || null)))
        .find(leaf => JSON.stringify(leaf.path) === JSON.stringify(v.path || []))?.spec;
    let issue = saved.some(v => !providerOptionLeaf(providers[v.provider]?.[v.key], v.path || []) ||
        !activeLeaf(v) || (activeLeaf(v).values && !activeLeaf(v).values.includes(v.value)) ||
        (providers[v.provider][v.key].container || null) !== (v.container || null))
        ? "Saved provider controls are no longer supported; choose an explicit replacement." : "";
    node.__orvLinkedCreativeIssue = false;
    for (const input of node.inputs || []) {
        if (input.link == null || !input.name?.startsWith("provider_option:")) continue;
        const [,provider,container,key] = input.name.split(":");
        const spec = providers[provider]?.[key];
        if (!spec || (spec.container || "") !== container || !spec.text_semantic) {
            node.__orvLinkedCreativeIssue = true;
            if (!issue) issue = "Linked creative text is not supported by this configuration; the connection is preserved.";
        }
    }
    for (const [provider, options] of Object.entries(providers)) for (const [key, spec] of Object.entries(options)) {
        const problem = providerObjectIssue(spec, saved.filter(v => v.provider === provider && v.key === key),[],key);
        if (!issue && problem) issue = problem;
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
                count.__orvProviderOption=true;count.__orvProviderGroup=root.presentation?.group || "advanced";count.serialize=false;
            }
            count.label=`${providerControlLabel(root,key)} ${costLocale()==="ru"?"— количество":"Count"}`;
            count.value=Math.max(Number(count.value)||0,storedCount);
            if(count.value>storedCount&&!issue)issue=`${key}: Complete each provider array item before Generate.`;
            counts['[]']=count.value;inactive.delete(count);setVisible(count,true);
        }
        for (const leaf of providerOptionLeaves(root, [], values, counts)) {
        const path = leaf.path, spec = {...leaf.spec, container:root.container};
        const defaultLabel = providerAutoLabel(spec);
        const boolean = spec.type === "boolean";
        const enabled=Object.entries(root.requires || {}).every(([dependency,domain])=>domain.includes(
            saved.find(v=>v.provider===provider&&v.key===dependency)?.value ?? options[dependency]?.omitted_default));
        const on=costLocale()==="ru"?"Вкл.":"On",off=costLocale()==="ru"?"Выкл.":"Off";
        const choices = boolean ? [defaultLabel,on,off] : !enabled ? [defaultLabel]
            : spec.values ? [defaultLabel, ...spec.values] : undefined;
        const numeric = !choices && ["integer", "number"].includes(spec.type);
        const name = `provider_option:${provider}:${spec.container || ""}:${key}${path.length ? ":" + path.join(":") : ""}`;
        const matches = v => v.provider === provider && v.key === key &&
            (v.container || null) === (spec.container || null) && JSON.stringify(v.path || []) === JSON.stringify(path);
        const old = saved.find(matches);
        let item = widget(node, name);
        const updateValue = value => {
                if (item.__orvProjectingProviderValue || node.__orvProviderProfile!==profile) return;
                let values;
                try { values = storage.value ? JSON.parse(storage.value) : []; } catch { return; }
                if (!Array.isArray(values)) return;
                const omit=value===defaultLabel || value==="" || value==null;
                const actual=boolean && !omit ? value===true || value===on || value==="true" : value;
                const remaining=updateProviderIntent(node,root,{provider,key,container:spec.container,path},values,actual,omit);
                storage.value = JSON.stringify(remaining);
                const issue = configureOperationControls(node, node.__orvProviderProfile);
                if (node.__orvCapabilityStatus) node.__orvCapabilityStatus.value = issue || "";
                setVisible(node.__orvCapabilityStatus, Boolean(issue));
                fitPresentationWidth(node);
                publishSemanticProjection(node);
                node.setDirtyCanvas?.(true, true);
                void refreshEstimate(node);
            };
        const creative = ["negative_prompt","creative_prompt"].includes(spec.text_semantic);
        const knownDefault=spec.omitted_default ?? spec.default;
        const bounded = numeric && Number.isFinite(spec.min) && Number.isFinite(spec.max) && spec.max>spec.min;
        // An unknown automatic value has no honest slider position. A native
        // nullable numeric input accepts the first explicit value directly.
        const type = creative ? "customtext" : choices ? "combo" : bounded && (old || Number.isFinite(knownDefault)) ? "slider" : numeric ? "number" : "text";
        const previous = item && item.type !== type ? item : null;
        const position = previous ? node.widgets.indexOf(previous) : -1;
        if (previous) item = null;
        if (!item) {
            if (creative) item = ComfyWidgets.STRING(node,name,["STRING",{default:old?.value ?? "",multiline:true}],app).widget;
            else {
                item = node.addWidget(type,name,old?.value ?? (numeric ? knownDefault ?? null : defaultLabel),updateValue,
                    {values:choices,min:spec.min,max:spec.max,step:spec.type === "integer" ? 1 : undefined});
            }
        }
        if (previous) {
            node.widgets.splice(node.widgets.indexOf(item),1);
            node.widgets.splice(position,1,item);
            inactive.delete(previous);
            previous.onRemove?.();
        }
        inactive.delete(item);
        item.callback = updateValue;
        item.__orvProviderOption = true;
        item.__orvTextSemantic = creative ? spec.text_semantic : undefined;
        item.__orvCreativeLabel = creative && spec.presentation ? providerControlLabel(spec,key,path) : undefined;
        item.__orvProviderGroup=spec.presentation?.group || root.presentation?.group || "advanced";
        item.__orvProviderAuto=!old;
        item.__orvProviderKnownDefault=knownDefault!==undefined;
        item.__orvResetProvider=()=>updateValue(defaultLabel);
        item.__orvFixedValue = numeric && spec.min === spec.max && Number.isFinite(spec.min);
        item.serialize = false;
        item.label = providerControlLabel(spec,key,path) + (spec.required ? " *" : "");
        Object.assign(item.options ||= {}, {min:spec.min, max:spec.max});
        if (numeric) {
            // The native slider defaults to a whole unit without an explicit
            // step. This is an interaction increment, not a provider constraint.
            const step = spec.type === "integer" ? 1 : 0.01;
            item.options.step = step;
            item.options.step2 = step;
            // Fractional fields have no provider-imposed decimal scale.
            // Avoid the native input's default three-decimal quantization.
            item.options.precision = spec.type === "integer" ? 0 : 15;
            item.__orvProviderFractional = bounded && spec.type !== "integer";
            if (type === "slider") installClassicProviderSlider(item);
        }
        item.options.placeholder=spec.required ? (costLocale()==="ru"?"Обязательное поле":"Required") : defaultLabel;
        item.options.tooltip=[numeric ? (costLocale()==="ru"?"Измените значение для ручной настройки. Сброс в Авто — в меню ноды.":"Edit to override. Reset to Auto from the node menu.") : "",spec.max_length == null ? "" : `Maximum ${spec.max_length} characters`,
            ...Object.entries(root.requires || {}).map(([key,domain])=>`Requires ${key}: ${domain.join(" / ")}`)].filter(Boolean).join("; ");
        if (choices) {
            item.options.values = choices;
            // Format reviewed ordinary enum values; leave literal values and
            // provider identifiers outside this display mapping untouched.
            item.options.getOptionLabel = value => ({
                high:"High", medium:"Medium", low:"Low", fixed:"Fixed", contain:"Contain",
                cover:"Cover", color:"Color", image:"Image", elevenlabs:"ElevenLabs",
                fish:"Fish", starfish:"Starfish", orca:"Orca", heygen_voice:"HeyGen Voice",
            })[value] ?? String(value ?? "");
        }
        item.__orvProjectingProviderValue = true;
        try { item.value = old ? (boolean ? old.value ? on : off : old.value) : choices ? defaultLabel : numeric ? knownDefault ?? null : ""; }
        finally { item.__orvProjectingProviderValue = false; }
        if (item.__orvFixedValue) {
            item.options.read_only = item.options.readOnly = item.options.disabled = true;
            if (!item.__orvFixedDrawInstalled) {
                const nativeDraw = item.drawWidget, nativeClick = item.onClick, nativeDrag = item.onDrag;
                item.drawWidget = function(ctx,options) { return this.__orvFixedValue ? drawReadOnlyValue(node,this,ctx) : nativeDraw?.call(this,ctx,options); };
                item.onClick = function(event) { if (!this.__orvFixedValue) return nativeClick?.call(this,event); };
                item.onDrag = function(event) { if (!this.__orvFixedValue) return nativeDrag?.call(this,event); };
                item.__orvFixedDrawInstalled = true;
            }
        }
        const legacyMode=widget(node,name+":override");if(legacyMode)setVisible(legacyMode,false);
        setVisible(item,enabled);
        }
    }
    const geometry=new Set(),omitted=new Set();
    for(const [provider,options]of Object.entries(providers))for(const [key,spec]of Object.entries(options)){
        for(const name of spec.omits_controls || [])geometry.add(name);
        const selected=saved.find(v=>v.provider===provider&&v.key===key);
        if(selected&&(!spec.omit_when||spec.omit_when.includes(selected.value)))for(const name of spec.omits_controls || [])omitted.add(name);
    }
    for(const name of geometry)setVisible(widget(node,name),!omitted.has(name)&&controls[name]?.state==='SUPPORTED');
    // Determine the new projection before retiring controls from the old one.
    // Retained native widgets never make a hidden-to-visible round trip.
    for (const item of inactive) if (item.__orvProviderHeading) inactive.delete(item);
    hideInactive();
    providerControlGroups(node); orderPresentationWidgets(node); sizePrimaryControls(node); stylePrompt(node); installNodeTypography(node);
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
        prompt.label = "prompt";
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
// Backend Autogrow TemplatePrefix max=100, independent of model limits.
const REFERENCE_WIRE_LIMIT = 100;

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
    normalizeImportedReferenceInputs(node);
    if (node.__orvReferenceAliasConflict) {
        node.__orvMediaIntentInvalid = true;
        return [];
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
    if (suffix >= REFERENCE_WIRE_LIMIT - 4) intent.compact_reference_wires = true;
    const compactWires = intent.compact_reference_wires === true;
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
            if (input.orv_pending_reference && !compactWires) input.name = `direct_references.reference_${++suffix}`;
            const order = ++ordinal;
            entry = { id: `media_${order}`, order, owner_id: node.id, origin_id: link.origin_id,
                origin_slot: link.origin_slot, origin_token: mediaSourceToken(origin), kind: outputMediaKind(origin, link.origin_slot),
                reference_name: isDirectReferenceInput(input) && !compactWires ? input.name : `direct_references.reference_${++suffix}`,
                roles: FIXED_MEDIA_ROLES.includes(input.name) ? [input.name] : [], collection: input.name === "input_references" };
            retained.push(entry);
        }
        entry.active_name = input.name;
        entry.kind = outputMediaKind(origin, link.origin_slot);
        input.orv_occurrence_id = entry.id;
        delete input.orv_pending_reference;
    }
    intent.media = retained.sort((a, b) => a.order - b.order);
    if (suffix >= REFERENCE_WIRE_LIMIT - 4) intent.compact_reference_wires = true;
    if (intent.compact_reference_wires && !compactActiveReferenceWires(node, intent.media)) {
        node.__orvMediaIntentInvalid = true;
    }
    return intent.media;
}

// Keep durable occurrence identity/order independent of the finite native wire
// namespace. Enter compact mode only when the old monotonic allocator reaches
// its host boundary. Do not delete/reconnect a linked input to rename its wire.
function compactActiveReferenceWires(node, entries) {
    const refs = directReferenceInputs(node);
    const linked = refs.filter(input => input.link != null);
    const active = entries.filter(entry => isDirectReferenceInput({ name: entry.active_name }));
    const ordered = active.map(entry => ({ entry, input: linked.find(input =>
        input.orv_occurrence_id === entry.id && input.name === entry.active_name) }));
    const free = refs.filter(input => input.link == null);
    if (ordered.length !== linked.length || ordered.some(item => !item.input) ||
        new Set(ordered.map(item => item.input)).size !== linked.length ||
        linked.length + free.length > REFERENCE_WIRE_LIMIT) return false;
    ordered.forEach(({ entry, input }, index) => {
        input.name = `direct_references.reference_${index}`;
        entry.active_name = input.name;
    });
    free.forEach((input, index) => { input.name = `direct_references.reference_${linked.length + index}`; });
    return true;
}

function boundedReferenceAssignment(entries, assigned) {
    const result = new Map(assigned);
    let index = 0;
    for (const entry of entries) if (isDirectReferenceInput({ name: assigned.get(entry.id) })) {
        if (index >= REFERENCE_WIRE_LIMIT) return null;
        result.set(entry.id, `direct_references.reference_${index++}`);
    }
    return result;
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
    const compactWires = capabilityIntent(node).compact_reference_wires === true;
    if (compactWires) {
        assigned = boundedReferenceAssignment(entries, assigned);
        if (!assigned) { node.__orvMediaIntentInvalid = true; return; }
        // Free slots are recreated from capabilities below. Retained linked
        // reference occurrences keep the original input object and graph link.
        for (let index = (node.inputs?.length || 0) - 1; index >= 0; index--) {
            const input = node.inputs[index];
            if (isDirectReferenceInput(input) && input.link == null) node.removeInput?.(index);
        }
    }
    for (let index = (node.inputs?.length || 0) - 1; index >= 0; index -= 1) {
        const input = node.inputs[index];
        if (!isMediaInput(input) || input.link == null) continue;
        const entry = entries.find(item => item.id === input.orv_occurrence_id);
        const name = entry && assigned.get(entry.id);
        if (compactWires && isDirectReferenceInput(input) && isDirectReferenceInput({ name })) {
            input.name = name;
        } else if (!entry || name !== input.name) node.removeInput?.(index);
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
    const intent = capabilityIntent(node), stored = intent.media;
    const suffix = Math.max(-1, ...directReferenceInputs(node).map(referenceInputSuffix),
        ...(intent.compact_reference_wires ? [] : (Array.isArray(stored) ? stored : [])
            .filter(Boolean).map(entry => referenceInputSuffix({ name: entry.reference_name || entry.name })))) + 1;
    if (suffix >= REFERENCE_WIRE_LIMIT) { node.__orvMediaIntentInvalid = true; return; }
    const name = `direct_references.reference_${suffix}`;
    node.addInput?.(name, `${kind.toUpperCase()},OPENROUTER_VIDEO_INPUT_REFERENCE`);
    const input = inputByName(node, name);
    if (input) { input.orv_reference_kind = kind; input.orv_pending_reference = true; mediaInputGraphs.set(input, mediaGraph(node)); }
}

function configureReferenceTopology(node, capability, method, transition = {}) {
    if (app.configuringGraph || node.__orvConfiguringMedia || node.__orvReconcilingMedia) return;
    if (!claimDirectReferenceTopology(node)) return;
    node.__orvReconcilingMedia = true;
    try {
        reconcileReferenceTopology(node, capability, method, transition);
    } finally { node.__orvReconcilingMedia = false; }
    publishSemanticProjection(node);
}

function reconcileReferenceTopology(node, capability, method, transition) {
    if (node.__orvReferenceAliasConflict) {
        node.__orvReferenceInvalid = true;
        disclose(node, "CONFLICTING REFERENCE INPUT NAMES; saved state preserved; Generate blocked");
        return;
    }
    const baseTopology = capability.__methodProfile?.topology || { fixed: [], reference_kinds: [], kind_sets: [[]], min: 0, max: 0 };
    parkIncompatibleMedia(node, baseTopology, transition);
    if (node.__orvReferenceAliasConflict) {
        node.__orvReferenceInvalid = true;
        return;
    }
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
        input.localized_name = input.label;
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

function projectionMatchesSelection(node) {
    return !node.__orvProjectedKey || node.__orvProjectedKey ===
        `${canonicalModel(node)}|${widget(node, "inference_method")?.value || ""}`;
}

function bindInferenceMethod(node) {
    const item = widget(node, "inference_method");
    if (!item) return;
    const previous = item.callback;
    item.callback = function (...args) {
        const next = item.value;
        if (canonicalModel(node) !== node.__orvModelCapability?.model_id) {
            if (!METHODS.includes(next)) return;
            // A method event during an asynchronous model switch must never
            // apply the previous model's topology to the newly selected model.
            cancelTopologyRefresh(node);
            node.__orvMethodExplicit = true;
            node.__orvConfigureVersion = (node.__orvConfigureVersion || 0) + 1;
            node.__orvConfiguringMedia = false;
            node.__orvMediaSelectionRevision = (node.__orvMediaSelectionRevision || 0) + 1;
            node.__orvPendingMediaSelection = { model: canonicalModel(node), method: next,
                revision: node.__orvMediaSelectionRevision };
            projectSelectedModel(node);
            return;
        }
        if (!node.__orvModelCapability?.supported_inference_methods?.includes(next)) return;
        previous?.apply(this, args);
        // Invalidate older asynchronous projections and their estimates.
        node.__orvProjectionVersion = (node.__orvProjectionVersion || 0) + 1;
        node.__orvEstimateRevision = (node.__orvEstimateRevision || 0) + 1;
        node.__orvConfigureVersion = (node.__orvConfigureVersion || 0) + 1;
        node.__orvConfiguringMedia = false;
        delete node.__orvPendingMediaSelection;
        cancelTopologyRefresh(node);
        node.__orvMethodExplicit = true;
        node.__orvLastMethod = next;
        if (node.__orvModelCapability) reprojectNodeSemantics(node, node.__orvModelCapability, next, { cause: "explicit" });
        scheduleCostRefresh(node);
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
    const connected = directReferenceInputs(node).filter((item) => item.link != null)
        .sort((a, b) => referenceInputSuffix(a) - referenceInputSuffix(b));
    const kinds = connected.map(connectedReferenceKind);
    return kinds.some((kind) => kind === null) ? null : kinds;
}

function costMoney(value) {
    // Money strings from Core are exact decimals; do not round via binary float.
    if (typeof value !== "string" || !/^\d{1,32}(\.\d{1,60})?$/.test(value)) return null;
    const [whole, fraction = ""] = value.split(".");
    const digits = (fraction + "000").slice(0, 3);
    let cents = BigInt(whole) * 100n + BigInt(digits.slice(0, 2));
    if (digits[2] >= "5") cents += 1n;
    // A positive sub-cent estimate must not look like a free generation.
    if (cents === 0n && /[1-9]/.test(value)) return "<0.01";
    return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}

function costDecimalShift(value, places) {
    if (typeof value !== "string" || !/^\d{1,32}(\.\d{1,60})?$/.test(value) || !Number.isSafeInteger(places) || places < 0 || places > 6) return null;
    const [whole, fraction = ""] = value.split(".");
    const digits = whole + fraction.padEnd(places, "0"), point = whole.length + places;
    return `${digits.slice(0, point).replace(/^0+/, "") || "0"}${digits.length > point ? `.${digits.slice(point)}` : ""}`;
}

function costCompactDecimal(value) {
    const text = String(value ?? "");
    if (!/^\d{1,32}(\.\d{1,60})?$/.test(text)) return "?";
    const [whole, fraction = ""] = text.split(".");
    const digits = (fraction + "00000").slice(0, 5);
    let units = BigInt(whole) * 10000n + BigInt(digits.slice(0, 4));
    if (digits[4] >= "5") units += 1n;
    if (units === 0n && /[1-9]/.test(text)) return "<0.0001";
    const tail = String(units % 10000n).padStart(4, "0").replace(/0+$/, "");
    return `${units / 10000n}${tail ? `.${tail}` : ""}`;
}

function costPrecompletionAdvisory(result) {
    const advisory = result?.precompletion_advisory, scenario = advisory?.scenario;
    if (advisory?.version === "ACI-PRECOMPLETION-2") {
        const roleKind={first_frame:"image",last_frame:"image",source_video:"video",audio:"audio"};
        const missing=list=>Array.isArray(list) && list.every(item=>item && ["image","video","audio"].includes(item.kind) &&
            (item.role==="reference" || roleKind[item.role]===item.kind) && Number.isSafeInteger(item.count) && item.count>0 && item.count<=64);
        const scenarios=advisory.scenarios,rates=advisory.rates;
        if(result?.state!=="INVALID" || result.availability!=="UNAVAILABLE" || result.reason!=="required_inputs_missing" ||
            [result.amount_usd,result.estimated_cost_usd,result.lower_usd,result.upper_usd].some(v=>v!=null) ||
            !Number.isSafeInteger(result.context_revision) || result.context_revision<0 || !(result.valid_for_ms>0) || !Number.isFinite(result.valid_for_ms) ||
            advisory.currency!=="USD" || !["COMPARISON","COMPONENT"].includes(advisory.scope) ||
            !["REFERENCE","SCENARIOS","RATE_ONLY","UNKNOWN"].includes(advisory.display) ||
            !Array.isArray(advisory.actual_reference_kinds) || advisory.actual_reference_kinds.length>64 || !advisory.actual_reference_kinds.every(k=>["image","video","audio"].includes(k)) ||
            !missing(advisory.missing_inputs) || !Array.isArray(advisory.alternatives) || !advisory.alternatives.length || !advisory.alternatives.every(a=>missing(a)&&a.length>0) ||
            !Array.isArray(advisory.completion_assumptions) || !advisory.completion_assumptions.length || !advisory.completion_assumptions.every(a=>typeof a==="string"&&a.trim()) ||
            !Array.isArray(scenarios) || !scenarios.every(row=>row && ["COMPARISON","COMPONENT"].includes(row.scope) && costMoney(row.amount_usd)!==null && typeof row.assumption==="string" && row.assumption.trim() && missing(row.missing_inputs || advisory.missing_inputs)) ||
            !Array.isArray(rates) || !rates.every(row=>row && costRateLabel(row) && typeof row.assumption==="string" && row.assumption.trim()) ||
            (advisory.display!=="UNKNOWN" && !/^[a-f0-9]{64}$/.test(result.rates_hash || "")))return null;
        if(advisory.display==="REFERENCE" && (scenarios.length!==1 || advisory.scenario?.amount_usd!==advisory.amount_usd || advisory.amount_usd!==scenarios[0].amount_usd || advisory.scope!==advisory.scenario?.scope))return null;
        if(advisory.display==="SCENARIOS" && (scenarios.length<2 || !costRangeUsd(advisory.lower_usd,advisory.upper_usd)))return null;
        if(advisory.display==="RATE_ONLY" && (!rates.length || scenarios.length || advisory.amount_usd!=null))return null;
        if(advisory.display==="UNKNOWN" && (rates.length || scenarios.length || advisory.amount_usd!=null))return null;
        return advisory;
    }
    if (result?.state !== "INVALID" || result.availability !== "UNAVAILABLE" ||
        result.reason !== "required_inputs_missing" ||
        [result.amount_usd, result.estimated_cost_usd, result.lower_usd, result.upper_usd].some(value => value != null) ||
        !Number.isSafeInteger(result.context_revision) || result.context_revision < 0 ||
        !Number.isFinite(result.valid_for_ms) || !(result.valid_for_ms > 0) ||
        !/^[a-f0-9]{64}$/.test(result.rates_hash || "") ||
        advisory?.version !== "ACI-PRECOMPLETION-1" || advisory.currency !== "USD" ||
        !["COMPARISON", "COMPONENT"].includes(advisory.scope) || scenario?.scope !== advisory.scope ||
        costMoney(advisory.amount_usd) === null || scenario.amount_usd !== advisory.amount_usd ||
        !Array.isArray(advisory.actual_reference_kinds) || advisory.actual_reference_kinds.length > 64 ||
        !advisory.actual_reference_kinds.every(kind => ["image", "video", "audio"].includes(kind)) ||
        !Array.isArray(advisory.missing_inputs) || !advisory.missing_inputs.length ||
        !advisory.missing_inputs.every(item => item?.kind === "image" && item.role === "reference" &&
            Number.isInteger(item.count) && item.count > 0 && item.count <= 64) ||
        !Array.isArray(advisory.completion_assumptions) || !advisory.completion_assumptions.length ||
        !advisory.completion_assumptions.every(item => typeof item === "string" && item.trim().length > 0) ||
        typeof scenario.assumption !== "string" || !scenario.assumption.trim()) return null;
    return advisory;
}

function costAdvisoryComparison(result) {
    const precompletion = costPrecompletionAdvisory(result);
    if (precompletion) return precompletion.scenario || null;
    if (result?.state === "PARTIAL" && result.availability === "UNAVAILABLE" && result.planning == null &&
        [result.amount_usd,result.estimated_cost_usd,result.lower_usd,result.upper_usd].every(value=>value==null) &&
        Number.isSafeInteger(result.context_revision) && result.context_revision>=0 &&
        Number.isFinite(result.valid_for_ms) && result.valid_for_ms>0 && /^[a-f0-9]{64}$/.test(result.rates_hash || "")) {
        const components=(Array.isArray(result.breakdown) ? result.breakdown : []).filter(row=>row && costMoney(row.amount_usd)!==null);
        if(components.length===1 && components[0].unit==="USD" && components[0].applicability==="APPLICABLE" &&
            ["base","additive"].includes(components[0].relation)) {
            // Present one Core-provided component verbatim, never sum fees or
            // promote an incomplete bill to an executable/modelled total.
            return {...components[0],scope:"COMPONENT",source:"APPLICABLE_BREAKDOWN"};
        }
    }
    if (!["UNKNOWN", "RATE_ONLY", "PARTIAL"].includes(result?.state) ||
        result.planning?.version !== "ACI-PLANNING-1" || result.planning.display !== "DETAIL_ONLY") return null;
    if (result.state === "RATE_ONLY" && costMoney(result.rate_usd) !== null) return null;
    const rows = (result.planning.scenarios || []).filter(row =>
        ["COMPARISON", "COMPONENT"].includes(row.scope) && costMoney(row.amount_usd) !== null);
    const known = (result.breakdown || []).filter(row => costMoney(row.amount_usd) !== null);
    // A reference is not a modelled total. Never choose arbitrarily between
    // alternatives, aggregate components, or replace an available primary rate.
    return rows.length === 1 && result.planning.scenarios.length === 1 && known.length <= 1 ? rows[0] : null;
}

function costLocale() {
    const value = app.ui?.settings?.getSettingValue?.("Comfy.Locale");
    return typeof value === "string" && /^ru(?:-|$)/i.test(value) ? "ru" : "en";
}

function costText(key) {
    const messages = costText.messages ||= {
        en: { formula:"Estimated cost", range:"Estimated range", model:"Modelled cost", scenarios:"Modelled scenarios",
            reference:"Reference cost", component:"Known cost component", details:"Cost details", rate:"Published rate",
            partial:"Partial cost", unknown:"Price unknown", invalid:"Check inputs", stale:"Price stale", calculating:"Calculating cost",
            partialBadge:"COST PARTIAL", unknownBadge:"PRICE UNKNOWN", invalidBadge:"CHECK INPUTS", staleBadge:"PRICE STALE", calculatingBadge:"CALCULATING…", detailsBadge:"COST DETAILS",
            formulaNote:"Based on documented pricing. Final provider charge may differ.", rangeNote:"Documented price bounds; not a spending cap.",
            modelNote:"Based on a billing assumption. Not a quote or spending limit.", scenariosNote:"Scenario values, not a guaranteed range or spending cap.",
            referenceNote:"Reference only; not a total. Input charges may differ.", silentNote:"Silent-output pricing is not disclosed. Input charges may differ. Reference only; not a total.",
            componentNote:"Other charges are not established. Not a total or lower bound.", detailsNote:"Separate known values; no combined total is established.",
            rateNote:"Billable quantity is needed to calculate a total.", partialNote:"A total cannot be calculated from the available data.",
            unknownNote:"Pricing for this configuration is not established.", invalidNote:"Check the required inputs and selected settings.",
            staleNote:"Refresh pricing before relying on an estimate.", calculatingNote:"No current estimate yet.",
            output:"Output video", withAudioOutput:"With audio · Output only", knownComponent:"Known component only",
            conditional:"Conditional total", alternative:"Alternative conditional totals", referenceScope:"Reference scenario", billableQuantity:"Scenario billing quantity",
            selected:"Selected configuration", audio:"Generate audio", on:"On", off:"Off", inputCharges:"Input charges", notEstablished:"Not established",
            lastJob:"Last completed job", actual:"Actual cost", job:"Job", modelLabel:"Model", actualUnavailable:"Unavailable",
            referenceRow:"Reference", componentRow:"Component", seconds:"s", automatic:"Automatic", perSecond:"s", millionTokens:"M tok", modelUnavailable:"Model not selected",
            completionNote:"Reference for a completed input configuration, not a quote. Add the missing inputs before generation.",
            routeComparisonNote:"Comparison assumes no additional reference fees. OpenRouter billing equivalence and audio/reference charges are unconfirmed; not a total.",
            inputComponentNote:"Input VIDEO charges and tariff precedence are unconfirmed. Known components only; not a total or lower bound.",
            missingInputs:"Missing inputs", imageReferences:"IMAGE references", videoReferences:"VIDEO references", audioReferences:"AUDIO references", completionOptions:"Example valid completions", unknownInputQuantities:"Missing media duration, geometry and input charges are not assumed to be zero. Reference scenarios are not a spending cap.",
            durationLabel:"Duration", fixedDuration:"Fixed", unverifiedDuration:"Not verified",
            validationTitle:"Inputs to check", correction:"To correct", preview:"Preview", notKnown:"Not known",
            validation_configuration:"Configuration", validation_inference_method:"Method", validation_model:"Model",
            validation_first_frame:"First frame", validation_last_frame:"Last frame", validation_source_video:"Source video",
            validation_reference_shape:"Reference types", validation_reference_count:"References", validation_distinct_media_types:"Distinct media types",
            validation_duration:"Duration", validation_combined_duration:"Combined input duration", validation_input_output_duration:"Input + output duration",
            validation_resolution:"Resolution", validation_aspect_ratio:"Aspect ratio", validation_size:"Exact size", validation_width:"Width", validation_height:"Height", validation_pixels:"Pixels",
            validation_provider_controls:"Provider controls", validation_geometry:"Geometry", validation_catalogue:"Prices", validation_media_metadata:"Media metadata",
            choose_allowed:"Choose a compatible value from the allowed options.", choose_model:"Select an available model.",
            connect_input:"Connect the required input.", add_references:"Connect at least {limit} matching references.", remove_references:"Keep at most {limit} active references.",
            connect_distinct_types:"Connect at least {limit} different supported media types.",
            shorten_media:"Shorten this input to {limit} s or less.", lengthen_media:"Use an input of at least {limit} s.",
            shorten_group:"Reduce combined input duration to {limit} s or less.", shorten_input_or_output:"Shorten input or output so their sum is at most {limit} s.",
            adjust_media:"Adjust media to the displayed bound.", correct_provider_controls:"Correct saved provider controls; values are preserved.", review_provider_controls:"Review the selected provider controls.",
            choose_geometry:"Choose Resolution/Aspect or Exact Size explicitly.", check_metadata:"Load the media and wait for its metadata; unknown is not zero.", refresh_price:"Refresh catalogue pricing.", check_inputs:"Check the required inputs and selected settings." },
        ru: { formula:"Расчётная стоимость", range:"Расчётный диапазон", model:"Модельная оценка", scenarios:"Сценарии стоимости",
            reference:"Справочная стоимость", component:"Компонент стоимости", details:"Сведения о стоимости", rate:"Опубликованный тариф",
            partial:"Частичная стоимость", unknown:"Цена неизвестна", invalid:"Проверьте входы", stale:"Цена устарела", calculating:"Расчёт стоимости",
            partialBadge:"НЕПОЛНАЯ ЦЕНА", unknownBadge:"ЦЕНА НЕИЗВЕСТНА", invalidBadge:"ПРОВЕРЬТЕ ВХОДЫ", staleBadge:"ЦЕНА УСТАРЕЛА", calculatingBadge:"РАСЧЁТ…", detailsBadge:"СВЕДЕНИЯ О ЦЕНЕ",
            formulaNote:"По опубликованным тарифам. Итоговое списание может отличаться.", rangeNote:"Границы по опубликованным правилам; не лимит расходов.",
            modelNote:"Расчёт по допущению о тарификации. Не оферта и не лимит расходов.", scenariosNote:"Сценарные значения, не гарантированный диапазон и не лимит расходов.",
            referenceNote:"Это ориентир, не итоговая стоимость. Начисления за вход могут отличаться.", silentNote:"Тариф без звука не раскрыт. Начисления за вход могут отличаться. Это ориентир, не итоговая стоимость.",
            componentNote:"Другие начисления неизвестны. Не итог и не нижняя граница.", detailsNote:"Отдельные известные суммы; общий итог не установлен.",
            rateNote:"Для расчёта суммы нужен оплачиваемый объём.", partialNote:"Доступных данных недостаточно для расчёта итога.",
            unknownNote:"Тарификация этой конфигурации не установлена.", invalidNote:"Проверьте обязательные входы и выбранные настройки.",
            staleNote:"Обновите тарифы перед использованием оценки.", calculatingNote:"Актуальной оценки пока нет.",
            output:"Выходное видео", withAudioOutput:"Со звуком · Только выход", knownComponent:"Только известный компонент",
            conditional:"Условная сумма", alternative:"Условные суммы по сценариям", referenceScope:"Справочный сценарий", billableQuantity:"Оплачиваемый объём сценария",
            selected:"Выбранная конфигурация", audio:"Генерация звука", on:"Вкл.", off:"Выкл.", inputCharges:"Стоимость входа", notEstablished:"Не установлена",
            lastJob:"Последняя завершённая операция", actual:"Фактическая стоимость", job:"Задание", modelLabel:"Модель", actualUnavailable:"Недоступна",
            referenceRow:"Ориентир", componentRow:"Компонент", seconds:" с", automatic:"Автоматически", perSecond:"с", millionTokens:"млн ток.", modelUnavailable:"Модель не выбрана",
            completionNote:"Ориентир для дополненной конфигурации, не итоговая стоимость. Перед генерацией подключите недостающие входы.",
            routeComparisonNote:"Сравнение предполагает отсутствие дополнительных сборов за референсы. Эквивалентность тарификации OpenRouter и начисления за аудио/референсы не подтверждены; это не итог.",
            inputComponentNote:"Тарификация входного VIDEO и приоритет тарифов не подтверждены. Только известные компоненты; не итог и не нижняя граница.",
            missingInputs:"Не хватает входов", imageReferences:"IMAGE-референсы", videoReferences:"VIDEO-референсы", audioReferences:"AUDIO-референсы", completionOptions:"Примеры допустимого дополнения", unknownInputQuantities:"Неизвестные параметры и начисления за вход не считаются нулевыми. Справочные сценарии — не лимит расходов.",
            durationLabel:"Длительность", fixedDuration:"Фиксировано", unverifiedDuration:"Не подтверждено",
            validationTitle:"Проверьте входы", correction:"Как исправить", preview:"Предпросмотр", notKnown:"Неизвестно",
            validation_configuration:"Конфигурация", validation_inference_method:"Метод", validation_model:"Модель",
            validation_first_frame:"Первый кадр", validation_last_frame:"Последний кадр", validation_source_video:"Исходное видео",
            validation_reference_shape:"Типы референсов", validation_reference_count:"Референсы", validation_distinct_media_types:"Различные типы медиа",
            validation_duration:"Длительность", validation_combined_duration:"Суммарная длительность входа", validation_input_output_duration:"Длительность входа + выхода",
            validation_resolution:"Разрешение", validation_aspect_ratio:"Пропорции", validation_size:"Точный размер", validation_width:"Ширина", validation_height:"Высота", validation_pixels:"Пиксели",
            validation_provider_controls:"Параметры провайдера", validation_geometry:"Геометрия", validation_catalogue:"Тарифы", validation_media_metadata:"Метаданные медиа",
            choose_allowed:"Выберите совместимое значение из допустимых вариантов.", choose_model:"Выберите доступную модель.",
            connect_input:"Подключите обязательный вход.", add_references:"Подключите не менее {limit} подходящих референсов.", remove_references:"Оставьте не более {limit} активных референсов.",
            connect_distinct_types:"Подключите не менее {limit} разных поддерживаемых типов медиа.",
            shorten_media:"Сократите этот вход до {limit} с или менее.", lengthen_media:"Используйте вход длительностью не менее {limit} с.",
            shorten_group:"Сократите суммарную длительность входов до {limit} с или менее.", shorten_input_or_output:"Сократите вход или выход, чтобы сумма не превышала {limit} с.",
            adjust_media:"Приведите медиа к указанному ограничению.", correct_provider_controls:"Исправьте сохранённые параметры провайдера; значения сохранены.", review_provider_controls:"Проверьте выбранные параметры провайдера.",
            choose_geometry:"Явно выберите Разрешение/Пропорции или Точный размер.", check_metadata:"Загрузите медиа и дождитесь метаданных; неизвестное не равно нулю.", refresh_price:"Обновите тарифы каталога.", check_inputs:"Проверьте обязательные входы и выбранные настройки." }
    };
    return messages[costLocale()][key] || messages.en[key] || "";
}

function costUsd(value) {
    const formatted = costMoney(value);
    if (formatted === null) return null;
    const number = costLocale() === "ru" ? formatted.replace(".", ",") : formatted;
    return number.startsWith("<") ? `<$${number.slice(1)}` : `$${number}`;
}

function costRangeUsd(lower, upper) {
    if (costMoney(lower) === null || costMoney(upper) === null) return null;
    let lo = costMoney(lower), hi = costMoney(upper);
    if (lo === hi && lower !== upper) {
        const cents = (value, up) => {
            const [whole, fraction = ""] = value.split(".");
            let n = BigInt(whole) * 100n + BigInt((fraction + "00").slice(0, 2));
            if (up && /[1-9]/.test(fraction.slice(2))) n++;
            return `${n / 100n}.${String(n % 100n).padStart(2, "0")}`;
        };
        lo = cents(lower, false); hi = cents(upper, true);
    }
    const local = value => costLocale() === "ru" ? value.replace(".", ",") : value;
    if (lo.startsWith("<") || hi.startsWith("<")) return `${costUsd(lower)}–${costUsd(upper)}`;
    return `$${local(lo)}–${local(hi)}`;
}

function costReferenceRows(result) {
    const precompletion=costPrecompletionAdvisory(result);
    if(precompletion?.version==="ACI-PRECOMPLETION-2")return precompletion.scenarios;
    if (!["UNKNOWN", "PARTIAL", "RATE_ONLY"].includes(result?.state) ||
        result.planning?.version !== "ACI-PLANNING-1" || result.planning.display !== "DETAIL_ONLY") return [];
    return (result.planning.scenarios || []).filter(row => ["COMPARISON", "COMPONENT"].includes(row.scope) && costMoney(row.amount_usd) !== null);
}

function costRateLabel(result) {
    const rate = costDecimalShift(result?.rate_usd, 0);
    if (rate === null) return null;
    if (["token", "tokens", "OUTPUT_TOKEN"].includes(result.rate_unit)) return `${costUsd(costDecimalShift(rate, 6))}/${costText("millionTokens")}`;
    const decimal = costCompactDecimal(rate);
    const number = costLocale() === "ru" ? decimal.replace(".", ",") : decimal;
    const money = number.startsWith("<") ? `<$${number.slice(1)}` : `$${number}`;
    const unit = ["s", "output_seconds", "source_seconds", "OUTPUT_SECOND"].includes(result.rate_unit) ? costText("perSecond") : result.rate_unit || "unit";
    return `${money}/${unit}`;
}

function localCostValidationDetails(node, code, topology = null, kinds = null) {
    const fallback = (field, correction_key) => [{ code, scope:"selection", field, correction_key }];
    if (/provider_control|provider_configuration/.test(code)) return fallback("provider_controls",
        code === "provider_control_invalid" ? "correct_provider_controls" : "review_provider_controls");
    if (code === "select_model") return fallback("model", "choose_model");
    if (code === "pricing_evidence_stale" || code === "pricing_request_unavailable") return fallback("catalogue", "refresh_price");
    if (geometryAuthority(node) === "AMBIGUOUS") return fallback("geometry", "choose_geometry");
    topology ||= applyTransportInputConstraints(node.__orvCapability?.__methodProfile?.topology,
        inputByName(node,"source_video")?.link != null);
    kinds ||= selectedReferenceKinds(node);
    if (!topology || !Array.isArray(kinds)) return fallback("media_metadata", "check_metadata");
    // Diagnostic quantities only: the existing shape predicates remain the gate.
    const details = [], add = (field, observed, bound, operator, correction_key, kind = "") =>
        details.push({code,scope:"reference_group",field,observed,bound,operator,correction_key,kind});
    for (const [kind,max] of Object.entries(topology.per_kind_max || {})) if (kinds.filter(k=>k===kind).length > max)
        add("reference_count",kinds.filter(k=>k===kind).length,max,"max","remove_references",kind);
    if (kinds.length < topology.min) add("reference_count",kinds.length,topology.min,"min","add_references",topology.reference_kinds?.length===1?topology.reference_kinds[0]:"");
    if (topology.max != null && kinds.length > topology.max) add("reference_count",kinds.length,topology.max,"max","remove_references");
    const minimumTypes = Math.min(...(topology.kind_sets || []).map(set=>new Set(set).size));
    if (Number.isFinite(minimumTypes) && minimumTypes > 1 && new Set(kinds).size < minimumTypes)
        add("distinct_media_types",new Set(kinds).size,minimumTypes,"min","connect_distinct_types");
    return details.length ? details : fallback("reference_shape", "check_inputs");
}

function costValidationSection(node, result) {
    let details = Array.isArray(result?.validation_details) ? result.validation_details : [];
    if (result?.state === "STALE") details = localCostValidationDetails(node,"pricing_evidence_stale");
    const knownFields = ["configuration","inference_method","model","source_video","first_frame","last_frame","reference_shape","reference_count","distinct_media_types","duration","duration_seconds","combined_duration","input_output_duration","resolution","aspect_ratio","size","width","height","pixels","provider_controls","geometry","catalogue","media_metadata"];
    details = details.filter(item=>item && typeof item === "object" && knownFields.includes(item.field));
    if (!details.length) return null;
    const quantity = (value,field) => {
        if (value == null) return costText("notKnown");
        if (!["string","number","boolean"].includes(typeof value)) return costText("notKnown");
        if (value === -1 || value === "-1") return costText("automatic");
        if (typeof value === "boolean") return costText(value?"on":"off");
        const text = String(value);
        if (/^\d{1,20}(\.\d{1,20})?$/.test(text)) return costCompactDecimal(text);
        if ((field === "resolution" && /^\d{1,4}(p|K)$/.test(text)) ||
            (field === "aspect_ratio" && /^\d{1,4}:\d{1,4}$/.test(text)) ||
            (field === "size" && /^\d{1,5}x\d{1,5}$/.test(text))) return text;
        return costText("notKnown");
    };
    const rows = [];
    for (const detail of details.slice(0,3)) {
        const kind = ["image","video","audio"].includes(detail.kind) ? detail.kind.toUpperCase() : "";
        const occurrence = Number.isSafeInteger(detail.kind_index) && detail.kind_index>0 ? ` ${detail.kind_index}` : "";
        const field = ["duration_seconds"].includes(detail.field)?"duration":detail.field;
        const name = `${kind}${occurrence}${kind?" · ":""}${costText(`validation_${field}`) || costText("validation_configuration")}${detail.metadata_status === "HINT" ? ` (${costText("preview")})` : detail.metadata_status === "UNKNOWN" ? ` (${costText("notKnown")})` : ""}`;
        const observed = `${detail.observed_is_lower_bound?"≥ ":""}${quantity(detail.observed,field)}`;
        const bound = detail.bound != null ? quantity(detail.bound,field) : null;
        const allowed = Array.isArray(detail.allowed) ? detail.allowed.slice(0,20).map(value=>quantity(value,field)).join(" / ") : null;
        const value = `${observed}${bound?` / ${bound}`:allowed?` → ${allowed}`:""}${detail.unit === "s" ? costText("seconds") : detail.unit === "px" ? " px" : ""}`;
        rows.push([name,value,false,detail.observed != null && (bound || allowed)?"violation":"neutral"]);
        const actions = ["choose_allowed","choose_model","connect_input","add_references","remove_references","connect_distinct_types","shorten_media","lengthen_media","shorten_group","shorten_input_or_output","adjust_media","correct_provider_controls","review_provider_controls","choose_geometry","check_metadata","refresh_price","check_inputs"];
        let actionKey = actions.includes(detail.correction_key) ? detail.correction_key : "check_inputs";
        if (detail.field === "duration_seconds") actionKey = detail.operator === "max"?"shorten_media":"lengthen_media";
        const action = costText(actionKey) || costText("check_inputs");
        rows.push([costText("correction"),action.replace("{limit}",bound || "")]);
    }
    return {title:`${costText("validationTitle")}${details.length>3?` (3/${details.length})`:""}`,rows};
}

function costTooltipView(node) {
    expireCostPresentation(node);
    const result = node.__orvEstimate?.result || { state: "UNKNOWN" };
    const precompletion = costPrecompletionAdvisory(result);
    const reference = costAdvisoryComparison(result), rows = costReferenceRows(result);
    const { kind, amount, accent } = costPriceView(result);
    const id = canonicalModel(node), model = widget(node, "model")?.__orvIdToLabel?.get(id) || node.__orvModelCapability?.display_name || costText("modelUnavailable");
    const chosenMethod = widget(node, "inference_method")?.value;
    const method = METHODS.includes(chosenMethod) ? chosenMethod : "";
    const selectedDuration = widget(node, "duration")?.value;
    const referenceSeconds = reference && !precompletion && reference.source!=="APPLICABLE_BREAKDOWN" && reference.quantity_unit==="s" ? reference.quantity : null;
    // A scenario quantity can include input VIDEO seconds. It is not evidence
    // that the selected output duration changed.
    const separateQuantity = referenceSeconds!=null && /^\d+(\.\d+)?$/.test(String(referenceSeconds)) &&
        (selectedDuration===-1 || Number.isFinite(Number(selectedDuration)) && Number(selectedDuration)>0) && Number(referenceSeconds)!==Number(selectedDuration);
    const duration = separateQuantity ? selectedDuration : reference && !precompletion && reference.source!=="APPLICABLE_BREAKDOWN" ? referenceSeconds : selectedDuration;
    const resolution = widget(node, "resolution")?.value;
    const referenceTier = reference && reference.sku?.endsWith(`_${resolution}`);
    const geometry = reference && !precompletion && reference.source!=="APPLICABLE_BREAKDOWN" && !separateQuantity ? (referenceTier ? resolution : null) :
        geometryAuthority(node) === "EXACT" ? widget(node, "size")?.value : [resolution, widget(node, "aspect_ratio")?.value].filter(Boolean).join(" · ");
    const context = [geometry, duration === -1 ? costText("automatic") : duration != null && /^\d+(\.\d+)?$/.test(String(duration)) ? `${String(duration).replace(".", costLocale() === "ru" ? "," : ".")}${costText("seconds")}` : null].filter(Boolean).join(" · ");
    const withAudio = reference && /^duration_seconds_with_audio_/.test(reference.sku || "");
    const silent = (result.reason_codes || [result.reason]).includes("AUDIO_EFFECTIVE_SEMANTICS_UNRESOLVED") ||
        Boolean(precompletion && withAudio && widget(node,"generate_audio")?.value === false);
    const sub = reference ? withAudio ? costText("withAudioOutput") : costText(reference.scope === "COMPONENT" ? "knownComponent" : "referenceScope") :
        ["formula", "range", "rate", "model", "scenarios"].includes(kind) ? costText(kind === "model" ? "conditional" : kind === "scenarios" ? "alternative" : "output") : "";
    const notes = { formula:"formulaNote", range:"rangeNote", model:"modelNote", scenarios:"scenariosNote", component:"componentNote", reference:silent?"silentNote":"referenceNote",
        details:"detailsNote", rate:"rateNote", partial:"partialNote", unknown:"unknownNote", invalid:"invalidNote", stale:"staleNote", calculating:"calculatingNote" };
    const sections = [];
    const validation = costValidationSection(node,result);
    if (validation) sections.push(validation);
    if (precompletion) {
        const missing = precompletion.missing_inputs.filter(item => !validation ||
            !(result.validation_details || []).slice(0,3).some(detail => detail?.field === "reference_count" &&
                detail.kind === item.kind && detail.operator === "min" &&
                Number.isFinite(detail.observed) && Number.isFinite(detail.bound) && detail.bound - detail.observed === item.count));
        if (missing.length) sections.push({ title:costText("missingInputs"), rows:
            missing.map(item => [item.role==="reference" ? costText(`${item.kind}References`) : costText(`validation_${item.role}`), String(item.count)]) });
        if(precompletion.alternatives?.length>1)sections.push({title:costText("completionOptions"),rows:precompletion.alternatives.slice(0,3).map((option,index)=>[
            `${index+1}`,option.map(item=>`${item.count} ${item.role==="reference"?item.kind.toUpperCase():costText(`validation_${item.role}`)}`).join(" + ")])});
    }
    if(precompletion?.rates?.length>1)sections.push({title:costText("details"),rows:precompletion.rates.map((row,index)=>[`${costText("rate")} ${index+1}`,costRateLabel(row)])});
    if (reference && silent) {
        const audio = widget(node,"generate_audio")?.value;
        sections.push({ title:costText("selected"), rows:[
            [costText("audio"), costText(audio === true ? "on" : audio === false ? "off" : "notEstablished")], [costText("inputCharges"), costText("notEstablished")] ] });
    }
    if (separateQuantity) sections.push({title:costText("referenceScope"),rows:[[costText("billableQuantity"),
        `${String(referenceSeconds).replace(".",costLocale()==="ru"?",":".")}${costText("seconds")}`]]});
    if (rows.length && !reference) sections.push({ title:costText("details"), rows:rows.map((row,index)=>[`${costText(row.scope === "COMPONENT" ? "componentRow" : "referenceRow")} ${index+1}`, costUsd(row.amount_usd)]) });
    const components = (result.breakdown || []).filter(row => costMoney(row.amount_usd) !== null);
    if (result.state === "PARTIAL" && components.length > 1) sections.push({ title:costText("partial"), rows:components.map((row,index)=>[`${costText("componentRow")} ${index+1}`,costUsd(row.amount_usd)]) });
    const actual = node.__orvActualState, receipt = actual?.receipt;
    if (actual?.status === "KNOWN" && receipt && costUsd(receipt.amount)) {
        const actualRows = [[costText("actual"), costUsd(receipt.amount), true]];
        if (actualText(receipt.job)) actualRows.push([costText("job"), `…${receipt.job.slice(-4)}`]);
        if (actualText(receipt.model) && receipt.model !== id) actualRows.push([costText("modelLabel"), widget(node, "model")?.__orvIdToLabel?.get(receipt.model) || costText("modelUnavailable")]);
        sections.push({ title:costText("lastJob"), rows:actualRows });
    } else if (["MISSING", "CONFLICT", "INVALID_ACTUAL"].includes(actual?.status) || node.__orvActualBindingUnavailable) sections.push({ title:costText("lastJob"), rows:[[costText("actual"), costText("actualUnavailable")]] });
    let note = costText(notes[kind]);
    if(reference?.source==="APPLICABLE_BREAKDOWN")note=`${note} ${costText("modelNote")}`;
    if (precompletion) {
        // Localize existing scenario limitations for presentation only. These
        // markers never select a tariff, change its amount or grant readiness.
        const assumptions=[reference?.assumption,...(precompletion.scenarios || []).map(row=>row.assumption)].filter(Boolean).join(" ");
        if (/OpenRouter equivalence|route equivalence/i.test(assumptions)) note = costText("routeComparisonNote");
        else if (/tariff precedence/i.test(assumptions)) note = costText("inputComponentNote");
        else if (/unestablished input charges/i.test(assumptions)) note = costText("componentNote");
        note = `${costText("completionNote")} ${note} ${precompletion.version==="ACI-PRECOMPLETION-2"?costText("unknownInputQuantities"):""}`.trim();
    }
    return { kind, title:costText(kind), identity:`${modelDisplayLabel(model).replace(/^[^:]+:\s*/, "")}${method ? ` · ${method}` : ""}`, context, sub, amount, note, sections, accent };
}

function costPriceView(result = {}) {
    const state = result.state || (result.availability === "AVAILABLE" ? "FORMULA" : "UNKNOWN");
    const precompletion=costPrecompletionAdvisory(result);
    const plan = result.planning, planning = ["UNKNOWN", "PARTIAL", "RATE_ONLY"].includes(state) && plan?.version === "ACI-PLANNING-1";
    const reference = costAdvisoryComparison(result), rows = costReferenceRows(result);
    let kind = ({ FORMULA:"formula", RANGE:"range", RATE_ONLY:"rate", PARTIAL:"partial", INVALID:"invalid", STALE:"stale", CALCULATING:"calculating" })[state] || "unknown";
    let amount = null, badge = null;
    if(precompletion?.display==="SCENARIOS"){
        kind="reference";amount=costRangeUsd(precompletion.lower_usd,precompletion.upper_usd);badge=`≈ ${amount} REF.`;
    } else if(precompletion?.display==="RATE_ONLY"){
        kind="rate";const labels=[...new Set(precompletion.rates.map(costRateLabel))];amount=labels.length===1?labels[0]:null;badge=amount?`${amount} RATE`:costText("detailsBadge");
    } else if(precompletion?.display==="UNKNOWN" || (state==="INVALID" && result.reason==="required_inputs_missing" && !precompletion)){
        kind="unknown";
    } else if (state === "FORMULA") { amount = costUsd(result.amount_usd ?? result.estimated_cost_usd); if (amount) badge = `≈ ${amount} EST.`; }
    else if (state === "RANGE") { amount = costRangeUsd(result.lower_usd, result.upper_usd); if (amount) badge = `${amount} EST.`; }
    else if (planning && plan.display === "MODELLED" && costUsd(plan.modelled_usd)) { kind = "model"; amount = costUsd(plan.modelled_usd); badge = `≈ ${amount} MODEL`; }
    else if (planning && plan.display === "SCENARIO_RANGE" && costRangeUsd(plan.scenario_min_usd, plan.scenario_max_usd)) { kind = "scenarios"; amount = costRangeUsd(plan.scenario_min_usd, plan.scenario_max_usd); badge = `≈ ${amount} MODEL`; }
    else if (state === "RATE_ONLY" && costRateLabel(result)) { amount = costRateLabel(result); badge = `${amount} RATE`; }
    else if (reference) { kind = reference.scope === "COMPONENT" ? "component" : "reference"; amount = costUsd(reference.amount_usd); badge = `${reference.scope === "COMPARISON" ? "≈ " : ""}${amount} REF.`; }
    else if (rows.length > 1) { kind = "details"; badge = costText("detailsBadge"); }
    if (!badge) {
        if (["formula", "range", "rate"].includes(kind)) kind = "unknown";
        badge = costText(`${kind}Badge`) || costText("unknownBadge");
    }
    const accent = ["formula", "range"].includes(kind) ? ACI_INDICATOR_COLORS.green : ["model", "scenarios"].includes(kind) ? ACI_INDICATOR_COLORS.yellow : ["reference", "component", "details"].includes(kind) ? ACI_INDICATOR_COLORS.violet : precompletion && kind==="rate" ? ACI_INDICATOR_COLORS.violet : "#C4C4C4";
    return { kind, amount, badge, accent };
}

function actualText(value) {
    return typeof value === "string" && value.length > 0 && value.length <= 512 && !/[\x00-\x1f\x7f]/.test(value);
}

function actualMoney(value) {
    if (value === null) return true;
    if (typeof value !== "string" || !/^\d{1,32}(\.\d{1,30})?$/.test(value)) return false;
    const [whole, fraction = ""] = value.split(".");
    return whole.replace(/^0+/, "").length <= 31 && (whole + fraction).replace(/^0+/, "").length <= 60;
}

function sameActualAmount(left, right) {
    if (left === right) return true;
    if (left === null || right === null || !actualMoney(left) || !actualMoney(right)) return false;
    const canonical = value => {
        const [whole, fraction = ""] = value.split(".");
        return `${whole.replace(/^0+/, "") || "0"}.${fraction.replace(/0+$/, "")}`;
    };
    return canonical(left) === canonical(right);
}

function emptyActualState() { return Object.freeze({ watermark: -1, status: "NO_JOB", receipt: null }); }

function reduceActualCompletion(state, event, dispatch) {
    if (!dispatch || event.epoch !== dispatch.epoch || event.node !== dispatch.node ||
        event.prompt !== dispatch.prompt || event.seq !== dispatch.seq || event.kind !== dispatch.kind ||
        !actualText(event.prompt) || !Number.isSafeInteger(event.seq) || event.seq < 0 ||
        !["GENERATE", "RESUME"].includes(event.kind) || !actualText(event.job) || !actualText(event.model)) return state;
    if (event.kind === "RESUME" && (!actualText(dispatch.expected_job) || event.job !== dispatch.expected_job)) return state;
    if (event.seq < state.watermark) return state;
    if (event.seq === state.watermark) {
        if (state.status === "CONFLICT") return state;
        const prior = state.receipt;
        if (prior && ["epoch", "node", "prompt", "seq", "kind", "job", "model"].every(key => prior[key] === event[key]) &&
            sameActualAmount(prior.amount, event.amount)) return state;
        return Object.freeze({ watermark: event.seq, status: "CONFLICT", receipt: null });
    }
    if (!actualMoney(event.amount)) return Object.freeze({ watermark: event.seq, status: "INVALID_ACTUAL", receipt: null });
    return Object.freeze({ watermark: event.seq, status: event.amount === null ? "MISSING" : "KNOWN", receipt: Object.freeze({ ...event }) });
}

function currentActualEpoch(graph) {
    if (!graph || typeof graph !== "object") return null;
    if (!actualGraphEpochs.has(graph)) actualGraphEpochs.set(graph, ++actualGraphEpoch);
    return actualGraphEpochs.get(graph);
}

function resetActualBinding(node) {
    actualPreparedNodes.delete(node);
    for (const [prompt, owners] of actualDispatches) {
        const retained = owners.filter(owner => owner.instance !== node);
        if (retained.length) actualDispatches.set(prompt, retained); else actualDispatches.delete(prompt);
    }
    for (const [id, ticket] of actualQueueTickets) {
        if (ticket.owners.some(owner => owner.instance === node)) actualQueueTickets.delete(id);
    }
    node.__orvActualState = emptyActualState();
    node.__orvActualBindingUnavailable = false;
    node.__orvActualInstanceEpoch = (node.__orvActualInstanceEpoch || 0) + 1;
}

function resetActualGraph(graph) {
    if (!graph) return;
    actualGraphEpochs.delete(graph);
    for (const node of costPresentationNodes) if (node.graph === graph) {
        resetActualBinding(node);
        clearCostMetadataWatches(node);
        refreshCostDetails(node);
    }
    // An unassociated early event cannot be attributed safely after graph reset.
    actualEarlyEvents.clear();
    pruneActualBindings();
}

function pruneActualBindings(now = costClock()) {
    for (const observing of actualQueueObservers) if (observing.expires <= now) actualQueueObservers.delete(observing);
    for (const [id, ticket] of actualQueueTickets) if (ticket.expires <= now) actualQueueTickets.delete(id);
    for (const [prompt, owners] of actualDispatches) {
        const alive = owners.filter(owner => owner.expires > now && owner.instance.graph === owner.graph &&
            owner.instance.__orvActualInstanceEpoch === owner.instance_epoch && owner.graph.getNodeById?.(owner.instance.id) === owner.instance);
        if (alive.length) actualDispatches.set(prompt, alive); else actualDispatches.delete(prompt);
    }
    for (const [prompt, pending] of actualEarlyEvents) if (pending.expires <= now) actualEarlyEvents.delete(prompt);
    clearTimeout(actualPruneTimer);
    const expiries = [...actualQueueTickets.values()].map(ticket => ticket.expires)
        .concat([...actualDispatches.values()].flatMap(owners => owners.map(owner => owner.expires)),
            [...actualEarlyEvents.values()].map(pending => pending.expires));
    expiries.push(...[...actualQueueObservers].map(observing => observing.expires));
    if (expiries.length) actualPruneTimer = setTimeout(() => pruneActualBindings(), Math.max(1, Math.min(...expiries) - now));
}

function captureActualQueueTicket(detail) {
    pruneActualBindings();
    const graph = app.rootGraph || app.graph;
    if (!graph || !actualText(graph.id) || !Number.isSafeInteger(detail?.requestId) ||
        !Number.isSafeInteger(detail.batchCount) || detail.batchCount < 1 || detail.batchCount > 100) return;
    const owners = [];
    for (const node of graph._nodes || Object.values(graph.nodes || {})) {
        const type = node.comfyClass || node.type;
        if (![GENERATE_NODE, "OpenRouterVideoResume"].includes(type) || node.graph !== graph || graph.getNodeById?.(node.id) !== node) continue;
        const model = type === GENERATE_NODE ? canonicalModel(node) : null;
        if (!actualText(String(node.id)) || (type === GENERATE_NODE && !actualText(model))) continue;
        const expected = widget(node, "job_id")?.value;
        owners.push(Object.freeze({ instance: node, graph, epoch: currentActualEpoch(graph),
            instance_epoch: node.__orvActualInstanceEpoch || 0, node: String(node.id), type,
            model,
            kind: type === GENERATE_NODE ? "GENERATE" : "RESUME",
            expected_job: actualText(expected) ? expected : null,
            linked_resume: inputByName(node, "job_id")?.link != null }));
    }
    if (!owners.length || owners.length > 128 || actualQueueTickets.size >= 128) return;
    actualQueueTickets.set(detail.requestId, { graph, graph_id: graph.id, owners: Object.freeze(owners),
        remaining: detail.batchCount, expires: costClock() + ACTUAL_EARLY_TTL_MS });
    pruneActualBindings();
}

function actualOwnersForQueuedPrompt(prompt) {
    pruneActualBindings();
    // Inspect only bounded ownership fields; never copy or retain native payloads.
    const graphId = prompt?.workflow?.id, output = prompt?.output;
    if (!actualText(graphId) || !output || typeof output !== "object") return [];
    const candidates = [...actualQueueTickets.values()].filter(ticket => ticket.graph_id === graphId &&
        ticket.graph === (app.rootGraph || app.graph) && ticket.remaining > 0 &&
        ticket.owners.some(owner => output[owner.node]?.class_type === owner.type));
    if (candidates.length !== 1) return [];
    const ticket = candidates[0];
    ticket.remaining -= 1;
    const seq = ++actualDispatchSequence, expires = costClock() + ACTUAL_BINDING_TTL_MS;
    return ticket.owners.filter(owner => {
        const queued = output[owner.node];
        const prepared = actualPreparedNodes.get(owner.instance);
        actualPreparedNodes.delete(owner.instance);
        if (queued?.class_type !== owner.type || owner.instance.graph !== owner.graph ||
            owner.graph.getNodeById?.(owner.instance.id) !== owner.instance ||
            owner.instance.__orvActualInstanceEpoch !== owner.instance_epoch ||
            prepared?.graph !== owner.graph || prepared.instance_epoch !== owner.instance_epoch) return false;
        if (owner.kind === "GENERATE" && queued.inputs?.model !== owner.model) return false;
        if (owner.kind === "RESUME" && !owner.linked_resume && queued.inputs?.job_id !== owner.expected_job) return false;
        return true;
    }).map(owner => Object.freeze({ ...owner, seq, expires }));
}

function installActualQueueObserver() {
    if (installActualQueueObserver.installed || typeof api.queuePrompt !== "function") return;
    installActualQueueObserver.installed = true;
    const original = api.queuePrompt;
    api.queuePrompt = function (...args) {
        let owners = [];
        try { owners = actualOwnersForQueuedPrompt(args[1]); } catch { /* Observer must not affect queue semantics. */ }
        const observing = { expires: costClock() + ACTUAL_EARLY_TTL_MS, nodes: new Set(owners.map(owner => owner.node)) };
        const canObserve = owners.length > 0 && actualQueueObservers.size < 128;
        if (canObserve) actualQueueObservers.add(observing);
        let result;
        try { result = original.apply(this, args); }
        catch (error) { actualQueueObservers.delete(observing); throw error; }
        if (!canObserve) return result;
        pruneActualBindings();
        try { if (result && typeof result.then === "function") {
            // Return the ORIGINAL promise, including its original rejection behavior.
            void result.then(value => {
                const active = actualQueueObservers.has(observing);
                actualQueueObservers.delete(observing);
                try {
                    const prompt = value?.prompt_id;
                    if (!active || !actualText(prompt) || !owners.length || actualDispatches.has(prompt)) return;
                    const bound = owners.map(owner => Object.freeze({ ...owner, prompt }));
                    if (actualDispatches.size >= 256) actualDispatches.delete(actualDispatches.keys().next().value);
                    actualDispatches.set(prompt, Object.freeze(bound));
                    const pending = actualEarlyEvents.get(prompt);
                    actualEarlyEvents.delete(prompt);
                    if (pending?.expires > costClock()) for (const detail of pending.events) handleActualExecuted(detail);
                    pruneActualBindings();
                } catch { /* Cost observation is isolated from successful native submission. */ }
            }, () => { actualQueueObservers.delete(observing); pruneActualBindings(); }).catch(() => {});
        } else actualQueueObservers.delete(observing);
        } catch { actualQueueObservers.delete(observing); }
        return result;
    };
}

function actualCostText(node, detail = false) {
    const state = node.__orvActualState || emptyActualState(), receipt = state.receipt;
    if (state.status === "KNOWN" && receipt) {
        const amount = costMoney(receipt.amount);
        if (amount !== null) return detail ? `Last completed job · $${amount} USD ACTUAL\n${receipt.model} · ${receipt.job}` : `$${amount} ACTUAL`;
    }
    if (state.status === "NO_JOB" && !node.__orvActualBindingUnavailable) return detail ? "No completed job." : "";
    const reason = ({ CONFLICT: "conflicting completion", INVALID_ACTUAL: "invalid reported cost", MISSING: "cost not reported" })[state.status] || "execution ownership unavailable";
    return detail ? `Last completed job ACTUAL unavailable (${reason}).${receipt ? `\n${receipt.model} · ${receipt.job}` : ""}` : "";
}

function costBadgeLabel(node, width = 0) {
    expireCostPresentation(node);
    const primary = String(node.__orvEstimate?.value || costText("unknownBadge"));
    // The prior job belongs in its own section, never in the next-price badge.
    const suffix = primary.match(/ (EST\.|MODEL|RATE|REF\.)$/)?.[1], budget = Math.floor(width / 7);
    if (width > 0 && suffix && primary.length > budget) {
        if (budget <= suffix.length + 3) return suffix;
        return `${primary.slice(0, budget - suffix.length - 2)}… ${suffix}`;
    }
    return primary;
}

function setCostBadgeLabel(node, badge, text) {
    if (badge.textContent === text) return;
    const actual = actualCostText(node), marker = text.lastIndexOf(" · ");
    badge.textContent = text;
    if (actual && marker >= 0 && text.slice(marker + 3) === actual && typeof document !== "undefined") {
        badge.textContent = text.slice(0, marker + 3);
        const span = document.createElement("span");
        span.textContent = actual;
        span.style.color = ACI_INDICATOR_COLORS.green;
        badge.append(span);
    }
}

function drawCostBadgeLabel(node, ctx, text, x, y, width) {
    const actual = actualCostText(node), marker = text.lastIndexOf(" · ");
    if (!actual || marker < 0 || text.slice(marker + 3) !== actual) { ctx.fillText(text, x, y, width); return; }
    const actualWidth = ctx.measureText?.(actual).width || actual.length * 7, color = ctx.fillStyle;
    ctx.fillStyle = ACI_INDICATOR_COLORS.green;
    ctx.fillText(actual, x, y, actualWidth);
    ctx.fillStyle = color;
    ctx.fillText(text.slice(0, marker + 3), x - actualWidth, y, Math.max(0, width - actualWidth));
}

function renderCostDetails(node, detail) {
    const view = costTooltipView(node);
    detail.textContent = "";
    detail.dir = document.documentElement?.dir || "ltr";
    Object.assign(detail.style, { boxSizing:"border-box", width:"340px", maxWidth:"calc(100vw - 16px)",
        padding:"12px", borderRadius:"8px", border:`1px solid ${view.accent}`, background:"#1A1A1A",
        color:"#C4C4C4", font:`400 12px/18px ${nodeTypography(node).family}`, fontVariantNumeric:"tabular-nums",
        whiteSpace:"normal", overflowWrap:"anywhere", pointerEvents:"none", boxShadow:"0 4px 16px rgba(0,0,0,0.33)" });
    const element = (tag, cls, text, style = {}) => {
        const item = document.createElement(tag); item.className = `orv-cost-${cls}`;
        if (text != null) item.textContent = text;
        Object.assign(item.style, style); return item;
    };
    const heading = element("h3","heading",view.title,{margin:"0",fontSize:"13px",fontWeight:"600",lineHeight:"18px",color:"#F9F9F9"});
    const identity = element("div","identity",view.identity,{margin:"5px 0 10px",fontSize:"12px",fontWeight:"400",lineHeight:"18px",unicodeBidi:"isolate",direction:"ltr"});
    const price = element("div","price",null,{display:"flex",flexWrap:"wrap",justifyContent:"space-between",alignItems:"center",gap:"12px",padding:"10px 0",
        borderTop:"1px solid rgba(196,196,196,0.15)",borderBottom:"1px solid rgba(196,196,196,0.15)"});
    const context = element("div","context",view.context,{minWidth:"0",fontSize:"12px",fontWeight:"400",lineHeight:"18px"});
    if (view.sub) context.append(element("small","scope",view.sub,{display:"block",marginTop:"2px",fontSize:"11px",fontWeight:"400",lineHeight:"16px"}));
    price.append(context);
    if (view.amount) price.append(element("span","amount",view.amount,{flex:"none",marginInlineStart:"auto",fontSize:["range","scenarios"].includes(view.kind)?"17px":"20px",
        fontWeight:"600",lineHeight:"24px",letterSpacing:["range","scenarios"].includes(view.kind)?"-0.3px":"-0.35px",color:view.accent,whiteSpace:"nowrap",direction:"ltr",unicodeBidi:"isolate"}));
    detail.append(heading, identity, price, element("p","note",view.note,{fontSize:"11px",fontWeight:"400",lineHeight:"16px",margin:"9px 0 0"}));
    for (const section of view.sections) {
        const group = element("section","section",null,{borderTop:"1px solid rgba(196,196,196,0.15)",marginTop:"10px",paddingTop:"8px"});
        group.append(element("h3","section-heading",section.title,{fontSize:"11px",fontWeight:"600",lineHeight:"18px",color:"#F9F9F9",margin:"0 0 5px"}));
        for (const [label,value,actual,severity] of section.rows) {
            const row = element("div","line",null,{display:"flex",justifyContent:"space-between",gap:"12px",padding:"3px 0",alignItems:"baseline"});
            row.append(element("span","label",label,{minWidth:"0"}),element("span",actual?"actual":"value",value,{textAlign:"end",color:severity === "violation"?"#FC5083":actual?ACI_INDICATOR_COLORS.green:"#F9F9F9",fontWeight:actual?"600":"400",unicodeBidi:"isolate"}));
            group.append(row);
        }
        detail.append(group);
    }
}

function refreshCostDetails(node) {
    if (node.__orvCostPopover) renderCostDetails(node, node.__orvCostPopover);
    scheduleBetaPresentation();
    node.setDirtyCanvas?.(true, true);
}

function suppressActualCompletion(node, owner) {
    const previous = node.__orvActualState || emptyActualState();
    if (owner.seq < previous.watermark || (owner.seq === previous.watermark && previous.status === "CONFLICT")) return;
    node.__orvActualState = Object.freeze({ watermark: owner.seq,
        status: owner.seq === previous.watermark ? "CONFLICT" : "INVALID_ACTUAL", receipt: null });
    refreshCostDetails(node);
}

function handleActualExecuted(detail) {
    pruneActualBindings();
    if (!actualText(detail?.prompt_id)) return;
    const owners = actualDispatches.get(detail.prompt_id);
    if (!owners) {
        // Websocket completion can beat HTTP acknowledgement. Buffer only the
        // allowlisted, bounded cost row, never arbitrary native UI output.
        const rows = detail.output?.orv_actual_v1, row = rows?.[0];
        const nodeId = String(detail.node ?? "");
        const potentiallyOwned = actualText(nodeId) && [...actualQueueObservers].some(observer => observer.nodes.has(nodeId));
        if (potentiallyOwned && actualEarlyEvents.size < 128) {
            const safeRow = Array.isArray(rows) && rows.length === 1 && row &&
            row.schema_version === 1 && row.state === "DONE" && actualText(row.job_id) && actualText(row.model) &&
            ["GENERATE", "RESUME"].includes(row.operation_kind) &&
            (row.amount_usd === null || row.amount_usd === undefined || (typeof row.amount_usd === "string" && row.amount_usd.length <= 100)) &&
            (row.expected_job_id === undefined || actualText(row.expected_job_id)) &&
            JSON.stringify(row).length <= 2048 && Object.keys(row).every(key =>
                ["schema_version", "job_id", "model", "amount_usd", "state", "operation_kind", "expected_job_id"].includes(key));
            const pending = actualEarlyEvents.get(detail.prompt_id) || { expires: costClock() + ACTUAL_EARLY_TTL_MS, events: [] };
            const safeEvent = { prompt_id: detail.prompt_id, node: nodeId,
                output: safeRow ? { orv_actual_v1: [{ ...row }] } : {} };
            if (pending.events.length < 4) pending.events.push(safeEvent);
            else pending.events = [{ prompt_id: detail.prompt_id, node: nodeId, output: {} }];
            actualEarlyEvents.set(detail.prompt_id, pending);
            pruneActualBindings();
        }
        return;
    }
    const nodeId = String(detail.node ?? ""), rows = detail.output?.orv_actual_v1;
    for (const owner of owners) {
        const node = owner.instance;
        if (owner.node !== nodeId || node.graph !== owner.graph || currentActualEpoch(owner.graph) !== owner.epoch ||
            owner.graph.getNodeById?.(node.id) !== node || node.__orvActualInstanceEpoch !== owner.instance_epoch ||
            !costPresentationNodes.has(node)) continue;
        if (!Array.isArray(rows) || rows.length !== 1) { suppressActualCompletion(node, owner); continue; }
        const row = rows[0];
        if (!row || typeof row !== "object" || Array.isArray(row) || row.schema_version !== 1 || row.state !== "DONE" ||
            !actualText(row.job_id) || !actualText(row.model) || !["GENERATE", "RESUME"].includes(row.operation_kind) ||
            Object.keys(row).some(key => !["schema_version", "job_id", "model", "amount_usd", "state", "operation_kind", "expected_job_id"].includes(key))) {
            suppressActualCompletion(node, owner); continue;
        }
        const event = { epoch: owner.epoch, node: owner.node, prompt: owner.prompt, seq: owner.seq,
            kind: row.operation_kind, job: row.job_id, model: row.model, amount: row.amount_usd };
        if (event.kind !== owner.kind || (owner.kind === "GENERATE" && event.model !== owner.model)) {
            suppressActualCompletion(node, owner); continue;
        }
        // Linked Resume input is verified execution-locally by the backend row;
        // the owned prompt/node association remains mandatory independently.
        if (owner.kind === "RESUME" && owner.linked_resume && !actualText(row.expected_job_id)) {
            suppressActualCompletion(node, owner); continue;
        }
        const dispatch = owner.kind === "RESUME" && owner.linked_resume && actualText(row.expected_job_id) ?
            Object.freeze({ ...owner, expected_job: row.expected_job_id }) : owner;
        if (owner.kind === "RESUME" && (!actualText(dispatch.expected_job) || event.job !== dispatch.expected_job)) {
            suppressActualCompletion(node, owner); continue;
        }
        node.__orvActualState = reduceActualCompletion(node.__orvActualState || emptyActualState(), event, dispatch);
        refreshCostDetails(node);
    }
}

function installResumeActualPresentation(node) {
    if (node.__orvResumeActualInstalled) return;
    node.__orvResumeActualInstalled = true;
    node.__orvEstimate = { value: "RESUME", result: { state: "UNKNOWN" } };
    installCostLifecycle(node);
    // Reuse the existing native cost surface, without Generate's sizing/chrome.
    installBetaPresentation(node);
    const draw = node.onDrawForeground;
    node.onDrawForeground = function (ctx, ...args) {
        draw?.call(this, ctx, ...args);
        drawCollapsedCostBadge(this, ctx);
    };
    const configure = node.onConfigure;
    node.onConfigure = function (...args) {
        resetActualBinding(this);
        return configure?.apply(this, args);
    };
}

function expireCostPresentation(node) {
    if (!node.__orvCostExpiresAt || costClock() < node.__orvCostExpiresAt) return false;
    node.__orvCostExpiresAt = null;
    discardCurrentCost(node, "pricing_evidence_stale");
    setCostPresentation(node, { state: "STALE", reason_codes: ["pricing_evidence_stale"] });
    return true;
}

function costClock() {
    return typeof performance !== "undefined" && typeof performance.now === "function" ? performance.now() : Date.now();
}

function installCostLifecycle(node) {
    if (!costPresentationNodes.has(node)) {
        costPresentationNodes.add(node);
        resetActualBinding(node);
        const queueWidget = widget(node, node.type === "OpenRouterVideoResume" || node.comfyClass === "OpenRouterVideoResume" ? "job_id" : "model");
        if (queueWidget && !queueWidget.__orvActualQueuePrepared) {
            queueWidget.__orvActualQueuePrepared = true;
            const beforeQueued = queueWidget.beforeQueued;
            queueWidget.beforeQueued = function (...args) {
                const result = beforeQueued?.apply(this, args);
                actualPreparedNodes.set(node, Object.freeze({ graph: node.graph, instance_epoch: node.__orvActualInstanceEpoch }));
                return result;
            };
        }
        const removed = node.onRemoved;
        node.onRemoved = function (...args) {
            costPresentationNodes.delete(this);
            resetActualBinding(this);
            clearTimeout(this.__orvCostExpiryTimer);
            cancelTopologyRefresh(this);
            clearTimeout(this.__orvCostRefreshTimer);
            this.__orvEstimateRevision = (this.__orvEstimateRevision || 0) + 1;
            clearCostMetadataWatches(this);
            this.__orvClassicCostBadge?.remove();
            this.__orvCostPopover?.remove();
            return removed?.apply(this, args);
        };
    }
    if (costLifecycleInstalled) return;
    costLifecycleInstalled = true;
    const resume = () => {
        pruneActualBindings();
        for (const current of costPresentationNodes) {
            if (expireCostPresentation(current)) refreshCostDetails(current);
        }
    };
    app.ui?.settings?.addEventListener?.("Comfy.Locale.change", () => {
        for (const current of costPresentationNodes) {
            if (current.__orvEstimate?.result) current.__orvEstimate.value = costBadgeText(current.__orvEstimate.result);
            refreshCostDetails(current);
        }
    });
    if (typeof document !== "undefined") document.addEventListener?.("visibilitychange", resume);
    if (typeof window !== "undefined") window.addEventListener?.("focus", resume);
}

// ARENAS®lab approved auxiliary palette. Presentation only; not a pricing state resolver.
const ACI_INDICATOR_COLORS = Object.freeze({ green: "#0ACF83", violet: "#9E6BFF", yellow: "#FFBB00", black: "#1A1A1A" });

function costBadgeColors(node, text) {
    const primary = text.split(" · ")[0];
    const accent = primary.endsWith(" MODEL") ? ACI_INDICATOR_COLORS.yellow : primary.endsWith(" REF.") ? ACI_INDICATOR_COLORS.violet :
        primary.endsWith(" ACTUAL") && node.__orvActualState?.status === "KNOWN" ? ACI_INDICATOR_COLORS.green :
        costPriceView(node.__orvEstimate?.result).accent;
    return { accent, background: ACI_INDICATOR_COLORS.black };
}

function costDetailAccent(node) {
    return costPriceView(node.__orvEstimate?.result).accent;
}

function syncCostDetailAccent(node) {
    if (node.__orvCostPopover) node.__orvCostPopover.style.borderColor = costDetailAccent(node);
}

function drawCollapsedCostBadge(node, ctx) {
    checkNativeCostMetadata(node);
    const width = node._collapsed_width || node.size?.[0] || 400;
    const badgeWidth = Math.min(width * 0.5, 160);
    const text = costBadgeLabel(node, badgeWidth - 12);
    ctx.save();
    ctx.font = `600 11px ${nodeTypography(node).family}`;
    const colors = costBadgeColors(node, text);
    ctx.fillStyle = colors.background || "#27302f";
    ctx.fillRect(width - badgeWidth, -24, badgeWidth - 4, 18);
    ctx.fillStyle = colors.accent || "#c8cecc";
    ctx.textAlign = "right";
    drawCostBadgeLabel(node, ctx, text, width - 8, -11, badgeWidth - 12);
    ctx.restore();
    syncClassicCostBadge(node, ctx, { x: width - badgeWidth, y: -24, width: badgeWidth - 4, height: 18 });
}

function costBadgeText(result) {
    return costPriceView(result).badge;
}

function costDetailsText(node) {
    const view = costTooltipView(node);
    return [view.title, view.identity, view.context, view.sub, view.amount, view.note,
        ...view.sections.flatMap(section => [section.title, ...section.rows.map(row => `${row[0]}: ${row[1]}`)])].filter(Boolean).join("\n");
}

function costTechnicalDetailsText(node) {
    expireCostPresentation(node);
    const result = node.__orvEstimate?.result;
    const lines = [String(node.__orvEstimate?.value || "PRICE UNKNOWN")];
    if (result) {
        lines.push(`${canonicalModel(node) || ""} · ${widget(node, "inference_method")?.value || ""}`);
        if (result.observed_at) lines.push(`Catalogue observed ${result.observed_at}`);
        for (const row of result.breakdown || []) {
            const amount = row.amount_usd == null ? "quantity unknown" : `$${costCompactDecimal(row.amount_usd)}`;
            lines.push(`${row.sku}: ${costCompactDecimal(row.quantity)} × $${costCompactDecimal(row.rate_usd)} = ${amount}${row.relation === "minimum" ? " (request floor)" : ""}`);
        }
        if (result.state === "PARTIAL") lines.push("Known components are not a total or a lower bound.");
        if (result.state === "RANGE") lines.push("Documented alternatives; this range is not a spending cap.");
        if (result.planning?.version === "ACI-PLANNING-1") {
            lines.push("Limited billing transparency. OpenRouter does not fully disclose the billing mechanism for this configuration.", "Modelled scenarios are not a quote, a bound, or spending authorization.");
            for (const scenario of result.planning.scenarios || []) {
                lines.push(`${scenario.scope}: ${scenario.label} · $${costCompactDecimal(scenario.amount_usd)}`, scenario.assumption);
                for (const charge of scenario.charges || []) lines.push(`${charge.sku}: ${costCompactDecimal(charge.quantity)} ${charge.quantity_unit || ""} × $${costCompactDecimal(charge.rate_usd)}/${charge.quantity_unit || "unit"} = $${costCompactDecimal(charge.amount_usd)}`);
            }
            if (result.planning.missing?.length) lines.push(`Missing: ${result.planning.missing.join(", ")}`);
        }
        lines.push(...(result.assumptions || []));
        lines.push(...(result.reason_codes || (result.reason ? [result.reason] : [])).map(costReasonText));
    }
    lines.push("Advisory model cost; final provider usage may differ.", actualCostText(node, true));
    return lines.filter(Boolean).join("\n");
}

function costReasonText(code) {
    const messages = {
        billing_quantity_unavailable: "Connect media with known duration or choose a fixed output length.",
        automatic_duration_unknown: "Output length is automatic; no complete bound is documented.",
        INPUT_VIDEO_TOKEN_QUANTITY_UNRESOLVED: "Video-input token quantity is not documented for this route.",
        VIDEO_INPUT_TOKEN_QUANTITY_UNRESOLVED: "Video-input token quantity is not documented for this route.",
        delivered_output_geometry_or_fps_unproven: "Delivered output geometry, cap rounding or frame rate is not established.",
        unclassified_pricing_sku: "A new catalogue charge needs a verified pricing rule.",
        canonical_revision_unverified: "This model revision needs verified pricing rules.",
        pricing_evidence_stale: "Catalogue pricing is stale; use the existing refresh flow.",
        AUDIO_EFFECTIVE_SEMANTICS_UNRESOLVED: "Pricing for explicit silent output is not documented.",
        LONG_TARIFF_WHOLE_VS_MARGINAL_AND_LONG_REFERENCE_PRECEDENCE_UNRESOLVED: "The long-duration tariff schedule is not documented.",
    };
    return messages[code] || String(code).replaceAll("_", " ").toLowerCase();
}

function setCostPresentation(node, result) {
    clearTimeout(node.__orvCostExpiryTimer);
    node.__orvEstimate.result = result;
    node.__orvEstimate.value = costBadgeText(result);
    node.__orvCostExpiresAt = null;
    if (Number.isFinite(result.valid_for_ms) && result.valid_for_ms > 0 && result.state !== "STALE") {
        node.__orvCostExpiresAt = costClock() + result.valid_for_ms;
        node.__orvCostExpiryTimer = setTimeout(() => {
            if (node.__orvEstimate?.result !== result) return;
            expireCostPresentation(node);
        }, result.valid_for_ms);
    }
    if (!node.__orvCostExpiryCleanup) {
        node.__orvCostExpiryCleanup = true;
        const removed = node.onRemoved;
        node.onRemoved = function (...args) {
            clearTimeout(this.__orvCostExpiryTimer);
            this.__orvEstimateRevision = (this.__orvEstimateRevision || 0) + 1;
            return removed?.apply(this, args);
        };
    }
    if (node.__orvCostPopover) {
        const text = costDetailsText(node);
        if (node.__orvCostPopover.textContent !== text) renderCostDetails(node, node.__orvCostPopover);
        syncCostDetailAccent(node);
    }
    node.setDirtyCanvas?.(true, true);
}

function invalidateCostPresentation(node) {
    node.__orvEstimateRevision = (node.__orvEstimateRevision || 0) + 1;
    if (node.__orvEstimate) setCostPresentation(node, { state: "CALCULATING" });
}

function discardCurrentCost(node, reason) {
    node.__orvEstimateRevision = (node.__orvEstimateRevision || 0) + 1;
    delete node.__orvCostAcceptedSignature;
    delete node.__orvCostAcceptedResult;
    if (node.__orvEstimate) setCostPresentation(node, { state: "UNKNOWN", reason_codes: [reason] });
}

function bindCostBadge(node, badge) {
    badge.removeAttribute?.("title");
    if (badge.__orvCostBound) return;
    badge.__orvCostBound = true;
    badge.tabIndex = 0;
    badge.setAttribute("role", "button");
    badge.removeAttribute?.("aria-haspopup");
    badge.removeAttribute?.("aria-expanded");
    const close = () => {
        node.__orvCostPopover?.remove(); node.__orvCostPopover = null;
        node.__orvCostPopoverOwner?.removeAttribute?.("aria-describedby");
        node.__orvCostPopoverOwner = null;
        if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(node.__orvCostAnchorFrame);
        node.__orvCostAnchorFrame = null;
    };
    node.__orvCloseCostTooltip = close;
    const open = () => {
        expireCostPresentation(node);
        for (const other of costPresentationNodes) if (other !== node && other.__orvCostPopover) {
            other.__orvCloseCostTooltip?.();
            if (other.__orvCostPopover) { other.__orvCostPopover.remove(); other.__orvCostPopover = null; }
        }
        if (node.__orvCostPopoverOwner && node.__orvCostPopoverOwner !== badge) close();
        node.__orvCostPopoverOwner = badge;
        if (!node.__orvCostPopover) {
            const detail = document.createElement("div"); detail.className = "orv-cost-detail";
            bindCostBadge.sequence = (bindCostBadge.sequence || 0) + 1;
            detail.id = `orv-cost-tooltip-${bindCostBadge.sequence}`;
            detail.setAttribute("role", "tooltip");
            Object.assign(detail.style,{position:"fixed",zIndex:"10000"});
            renderCostDetails(node, detail); document.body.append(detail); node.__orvCostPopover = detail;
        }
        badge.setAttribute("aria-describedby", node.__orvCostPopover.id);
        positionCostTooltip(node, badge);
        const watch = () => {
            node.__orvCostAnchorFrame = null;
            if (!node.__orvCostPopover) return;
            positionCostTooltip(node, badge);
            if (node.__orvCostPopover) node.__orvCostAnchorFrame = requestAnimationFrame(watch);
        };
        if (typeof requestAnimationFrame === "function" && !node.__orvCostAnchorFrame) node.__orvCostAnchorFrame = requestAnimationFrame(watch);
    };
    badge.addEventListener("mouseenter", open);
    badge.addEventListener("mouseleave", close);
    badge.addEventListener("focus", open);
    badge.addEventListener("blur", close);
    badge.addEventListener("keydown", event => { if (event.key === "Escape") close(); });
}

function positionCostTooltip(node, badge) {
    const detail = node.__orvCostPopover;
    if (!detail) return;
    const rect = badge.getBoundingClientRect();
    const inactive = node.graph && (app.canvas?.graph || app.graph)?.getNodeById?.(node.id) !== node;
    if (badge.isConnected === false || badge.hidden || rect.width === 0 || inactive ||
        rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) {
        node.__orvCloseCostTooltip?.(); return;
    }
    const bounds = detail.getBoundingClientRect?.() || {};
    const width = bounds.width || 430, height = bounds.height || 250;
    const below = rect.bottom + 4;
    const top = below + height <= window.innerHeight - 8 ? below : Math.max(8, rect.top - height - 4);
    Object.assign(detail.style,{left:`${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`,
        top:`${Math.max(8, Math.min(top, window.innerHeight - height - 8))}px`});
}

function syncClassicCostBadge(node, ctx, rect) {
    if (typeof document === "undefined") return;
    const vue = [...(document.querySelectorAll?.(".lg-node[data-node-id]") || [])]
        .some(element => element.dataset.nodeId === String(node.id));
    const inactive = node.graph && (app.canvas?.graph || app.graph)?.getNodeById?.(node.id) !== node;
    if (vue || inactive) {
        const badge = node.__orvClassicCostBadge;
        if (badge) badge.hidden = true;
        if (badge && node.__orvCostPopoverOwner === badge) {
            node.__orvCostPopover?.remove();
            node.__orvCostPopover = null;
            node.__orvCostPopoverOwner = null;
            badge.removeAttribute?.("aria-describedby");
        }
        return;
    }
    if (!ctx?.canvas || !rect) {
        if (node.__orvClassicCostBadge) node.__orvClassicCostBadge.hidden = true;
        return;
    }
    let badge = node.__orvClassicCostBadge;
    if (!badge) {
        badge = document.createElement("button");
        badge.type = "button";
        badge.className = "orv-classic-cost-badge";
        Object.assign(badge.style, { position: "fixed", zIndex: "4", opacity: "0", margin: "0",
            padding: "0", border: "0", borderRadius:"6px", font:`600 11px/16px ${nodeTypography(node).family}`, cursor: "pointer", background: "transparent" });
        badge.addEventListener("focus", () => { badge.style.opacity = "1"; setCostBadgeLabel(node, badge, costBadgeLabel(node, node.__orvClassicCostWidth || 0)); });
        badge.addEventListener("blur", () => { badge.style.opacity = "0"; badge.textContent = ""; });
        bindCostBadge(node, badge);
        document.body.append(badge);
        node.__orvClassicCostBadge = badge;
        const removed = node.onRemoved;
        node.onRemoved = function (...args) { badge.remove(); this.__orvCostPopover?.remove(); return removed?.apply(this, args); };
    }
    const transform = ctx.getTransform(), canvas = ctx.canvas.getBoundingClientRect();
    const sx = canvas.width / ctx.canvas.width, sy = canvas.height / ctx.canvas.height;
    Object.assign(badge.style, { left: `${canvas.left + (transform.a * rect.x + transform.c * rect.y + transform.e) * sx}px`,
        top: `${canvas.top + (transform.b * rect.x + transform.d * rect.y + transform.f) * sy}px`,
        width: `${Math.abs(transform.a * rect.width * sx)}px`, height: `${Math.abs(transform.d * rect.height * sy)}px` });
    badge.hidden = false;
    node.__orvClassicCostWidth = rect.width;
    const colors = costBadgeColors(node, String(node.__orvEstimate?.value || "PRICE UNKNOWN"));
    badge.style.color = colors.accent;
    badge.style.backgroundColor = colors.background || "transparent";
    badge.setAttribute("aria-label", costDetailsText(node));
    badge.removeAttribute?.("title");
}

function costMediaOccurrences(node, topology) {
    const graph = mediaGraph(node);
    const legacy = inputByName(node, "input_references");
    let references = directReferenceInputs(node).filter(input => input.link != null)
        .sort((a, b) => referenceInputSuffix(a) - referenceInputSuffix(b));
    if (legacy?.link != null) {
        const link = mediaLink(graph, legacy.link);
        const collection = link ? graph?.getNodeById?.(link.origin_id) : null;
        if ((collection?.type || collection?.comfyClass) !== "OpenRouterVideoReferenceCollection") return null;
        references = (collection.inputs || []).filter(input => input.link != null && /(^|\.)reference_\d+$/.test(input.name))
            .sort((a, b) => referenceInputSuffix(a) - referenceInputSuffix(b));
    }
    const result = references.map(input => ({ input, kind: connectedReferenceKind(input), role: "reference" }));
    for (const role of topology.fixed || []) {
        const input = inputByName(node, role);
        if (input?.link != null) result.push({ input, kind: role === "source_video" ? "video" : "image", role });
    }
    return result;
}

const COST_METADATA_EVENTS = ["loadedmetadata", "durationchange", "emptied", "load", "loadstart"];

function clearCostMetadataWatches(node) {
    for (const [element, record] of node.__orvCostMetadataWatches || []) {
        for (const event of COST_METADATA_EVENTS) element.removeEventListener?.(event, record.changed);
        record.unobserveSelection?.();
    }
    node.__orvCostMetadataWatches?.clear();
    delete node.__orvCostMetadataSignature;
}

function nativeCostSelection(origin, element) {
    // Selection identity is scalar native UI revision only. Never read preview
    // URLs, filenames, selection values, prompt, or media content for pricing.
    return JSON.stringify([origin.imageIndex ?? null, costPreviewSelections.get(origin)?.revision || 0]);
}

function observeNativeCostSelection(origin, changed) {
    let selection = costPreviewSelections.get(origin);
    if (!selection) {
        selection = { revision: 0, listeners: new Set(), hooks: [] };
        costPreviewSelections.set(origin, selection);
        for (const item of origin.widgets || []) {
            if (!/^(image|video|audio|file|filename|upload)$/.test(item.name || "")) continue;
            const previous = item.callback;
            const wrapper = function (...args) {
                const result = previous?.apply(this, args);
                selection.revision += 1;
                for (const listener of selection.listeners) { try { listener(); } catch { /* Cost hint observation cannot change native selection. */ } }
                return result;
            };
            item.callback = wrapper;
            selection.hooks.push({ item, previous, wrapper });
        }
    }
    selection.listeners.add(changed);
    return () => {
        selection.listeners.delete(changed);
        if (selection.listeners.size) return;
        for (const { item, previous, wrapper } of selection.hooks) if (item.callback === wrapper) item.callback = previous;
        costPreviewSelections.delete(origin);
    };
}

function currentCostMetadataOccurrence(node, watch) {
    if (node.graph && node.graph !== watch.graph) return false;
    const link = mediaLink(watch.graph, watch.input.link);
    if (watch.input.link !== watch.link_id || link !== watch.link || watch.graph?.getNodeById?.(link?.origin_id) !== watch.origin) return false;
    const selected = Number.isSafeInteger(watch.origin.imageIndex) ? watch.origin.imgs?.[watch.origin.imageIndex] : null;
    if (!(selected ? selected === watch.element : watch.origin.imgs?.includes(watch.element)) &&
        !(watch.origin.widgets || []).some(item => item.element === watch.element || item.element?.contains?.(watch.element))) return false;
    const current = costMediaOccurrences(node, node.__orvCapability?.__methodProfile?.topology || {});
    return Boolean(current?.some(item => item.input === watch.input && item.kind === watch.kind && item.role === watch.role));
}

function scheduleTopologyRefresh(node, task) {
    clearTimeout(node.__orvEstimateTimer);
    node.__orvTopologyPending = true;
    node.__orvEstimateTimer = setTimeout(() => {
        node.__orvTopologyPending = false;
        task();
    }, 120);
}

function cancelTopologyRefresh(node) {
    clearTimeout(node.__orvEstimateTimer);
    node.__orvTopologyPending = false;
}

function scheduleCostRefresh(node) {
    clearTimeout(node.__orvCostRefreshTimer);
    node.__orvCostRefreshTimer = setTimeout(() => {
        // The topology owner refreshes cost after publishing its new projection.
        if (!node.__orvTopologyPending && !node.__orvPendingMediaSelection &&
            !node.__orvConfiguringMedia && !node.__orvReconcilingMedia) refreshEstimate(node);
    }, 120);
}

function checkNativeCostMetadata(node) {
    if (!node.__orvEstimate || node.__orvResumeActualInstalled || node.__orvConfiguringMedia) return;
    const occurrences = costMediaOccurrences(node, node.__orvCapability?.__methodProfile?.topology || {});
    if (!occurrences) return;
    pruneCostMetadataWatches(node);
    const metadata = occurrences.map(occurrence => readNativeCostMetadata(node, occurrence));
    const signature = JSON.stringify([node.__orvCostMetadataGeneration || 0, occurrences.map(item => item.input.link), metadata]);
    const changed = node.__orvCostMetadataSignature !== undefined && node.__orvCostMetadataSignature !== signature;
    node.__orvCostMetadataSignature = signature;
    if (changed) {
        invalidateCostPresentation(node);
        scheduleCostRefresh(node);
    }
}

function pruneCostMetadataWatches(node) {
    for (const [element, record] of node.__orvCostMetadataWatches || []) {
        for (const watch of record.watches) if (!currentCostMetadataOccurrence(node, watch)) record.watches.delete(watch);
        if (!record.watches.size) {
            for (const event of COST_METADATA_EVENTS) element.removeEventListener?.(event, record.changed);
            record.unobserveSelection?.();
            node.__orvCostMetadataWatches.delete(element);
        }
    }
}

function readNativeCostMetadata(node, occurrence) {
    const { input, kind, role } = occurrence;
    const unknown = { kind, role, status: "UNKNOWN" };
    const graph = mediaGraph(node), link = mediaLink(graph, input.link);
    const origin = link ? graph?.getNodeById?.(link.origin_id) : null;
    if (!origin || !kind || (origin.outputs || []).filter(output => String(output.type).toLowerCase() === kind).length !== 1) return unknown;
    const elements = new Set();
    const isMedia = element => (typeof HTMLMediaElement !== "undefined" && element instanceof HTMLMediaElement) ||
        (typeof HTMLImageElement !== "undefined" && element instanceof HTMLImageElement);
    const selectedImage = Number.isSafeInteger(origin.imageIndex) ? origin.imgs?.[origin.imageIndex] : null;
    for (const element of selectedImage ? [selectedImage] : origin.imgs || []) if (isMedia(element)) elements.add(element);
    for (const item of origin.widgets || []) {
        const element = item.element;
        if (isMedia(element)) elements.add(element);
        for (const child of element?.querySelectorAll?.("video, audio, img") || []) if (isMedia(child)) elements.add(child);
    }
    const matching = [...elements].filter(element => {
        const tag = element.tagName?.toLowerCase();
        return tag === (kind === "image" ? "img" : kind);
    });
    if (matching.length !== 1) return unknown;
    const element = matching[0];
    node.__orvCostMetadataWatches ||= new Map();
    let record = node.__orvCostMetadataWatches.get(element);
    if (!record) {
        node.__orvCostMetadataGeneration = (node.__orvCostMetadataGeneration || 0) + 1;
        const watches = new Set();
        const changed = event => {
            pruneCostMetadataWatches(node);
            if (!node.__orvCostMetadataWatches?.has(element) || ![...watches].some(watch => currentCostMetadataOccurrence(node, watch))) return;
            const selection = nativeCostSelection(origin, element);
            const sameSelection = record.selection === selection;
            record.selection = selection;
            record.ready = sameSelection && ["loadedmetadata", "durationchange", "load"].includes(event?.type);
            invalidateCostPresentation(node);
            scheduleCostRefresh(node);
        };
        record = { watches, changed, selection: nativeCostSelection(origin, element), ready: true };
        record.unobserveSelection = observeNativeCostSelection(origin, () => {
            record.selection = nativeCostSelection(origin, element);
            record.ready = false;
            node.__orvCostMetadataGeneration = (node.__orvCostMetadataGeneration || 0) + 1;
            invalidateCostPresentation(node);
            scheduleCostRefresh(node);
        });
        node.__orvCostMetadataWatches.set(element, record);
        for (const event of COST_METADATA_EVENTS) element.addEventListener(event, changed);
    }
    if (![...record.watches].some(watch => watch.input === input && watch.link === link)) record.watches.add({
        input, kind, role, graph, origin, element, link, link_id: input.link });
    const selection = nativeCostSelection(origin, element);
    if (record.selection !== selection) {
        record.selection = selection; record.ready = false;
        node.__orvCostMetadataGeneration = (node.__orvCostMetadataGeneration || 0) + 1;
    }
    if (!record.ready) return unknown;
    if (kind === "image") {
        const width = element.naturalWidth, height = element.naturalHeight;
        return Number.isSafeInteger(width) && width > 0 && Number.isSafeInteger(height) && height > 0
            ? { kind, role, status: "HINT", width, height } : unknown;
    }
    const duration = element.duration;
    if (!Number.isFinite(duration) || duration <= 0 || element.readyState < 1) return unknown;
    const result = { kind, role, status: "HINT", duration_seconds: String(duration) };
    if (kind === "video" && Number.isSafeInteger(element.videoWidth) && element.videoWidth > 0 &&
        Number.isSafeInteger(element.videoHeight) && element.videoHeight > 0) {
        result.width = element.videoWidth; result.height = element.videoHeight;
    }
    return result;
}

function projectProviderCostControls(node, options) {
    if (node.__orvLinkedCreativeIssue) return {state:"INVALID",controls:[]};
    if (!Array.isArray(options) || options.length > 8) return { state: "UNKNOWN" };
    const providers = node.__orvCapability?.__methodProfile?.controls?.provider_options?.providers || {};
    const seen = new Set(), controls = [];
    for (const option of options) {
        if (!option || typeof option !== "object" || Array.isArray(option) ||
            Object.keys(option).some(key => !["provider", "key", "value", "container", "path"].includes(key)) ||
            option.container != null || (option.path != null && (!Array.isArray(option.path) || option.path.length)))
            return { state: "UNKNOWN" };
        const spec = providers[option.provider]?.[option.key];
        const identity = `${option.provider}/${option.key}`;
        if (!spec || seen.has(identity) || ["format", "fields", "items", "values", "omits_controls", "container"].some(key => key in spec))
            return { state: "UNKNOWN" };
        seen.add(identity);
        const descriptor = { provider: option.provider, key: option.key };
        if (spec.type === "number") {
            const value = option.value;
            if (typeof value !== "number" || !Number.isFinite(value) ||
                (spec.min != null && value < spec.min) || (spec.max != null && value > spec.max) ||
                (spec.exclusive_min != null && value <= spec.exclusive_min)) return { state: "INVALID" };
            descriptor.number_value = String(value);
        } else if (spec.type === "string") {
            if (typeof option.value !== "string") return { state: "INVALID" };
            const length = [...option.value].length;
            if (length > 65536) return { state: "UNKNOWN" };
            if ((spec.min_length != null && length < spec.min_length) ||
                (spec.max_length != null && length > spec.max_length)) return { state: "INVALID" };
            descriptor.text_length = length;
        } else return { state: "UNKNOWN" };
        controls.push(descriptor);
    }
    return { state: "READY", controls };
}

async function refreshEstimate(node) {
    if (node.__orvTopologyPending || node.__orvPendingMediaSelection || node.__orvConfiguringMedia ||
        node.__orvReconcilingMedia || !projectionMatchesSelection(node)) return;
    const revision = node.__orvEstimateRevision = (node.__orvEstimateRevision || 0) + 1;
    setCostPresentation(node, { state: "CALCULATING" });
    const unavailable = (reason, state = "UNKNOWN") => setCostPresentation(node, { state, reason_codes: [reason],
        validation_details:localCostValidationDetails(node,reason) });
    let providerControls;
    try { providerControls = JSON.parse(widget(node, "provider_options")?.value || "[]"); }
    catch { providerControls = null; }
    const costControls = projectProviderCostControls(node, providerControls);
    if (costControls.state !== "READY") {
        unavailable(costControls.state === "INVALID" ? "provider_control_invalid" :
            "provider_configuration_pricing_unverified", costControls.state); return;
    }
    if (node.__orvReferenceInvalid || geometryAuthority(node) === "AMBIGUOUS") {
        unavailable("configuration_not_authorized", "INVALID"); return;
    }
    const model = canonicalModel(node);
    if (!model) { unavailable("select_model", "INVALID"); return; }
    const referenceKinds = selectedReferenceKinds(node);
    if (referenceKinds === null) { unavailable("active_reference_shape_not_known"); return; }
    const profile = node.__orvCapability?.__methodProfile;
    const topology = applyTransportInputConstraints(profile?.topology, inputByName(node, "source_video")?.link != null);
    if (profile?.state !== "SUPPORTED" || !topology ||
        (!referenceShapeValid(topology, referenceKinds) && !referencePartialAllowed(topology, referenceKinds))) {
        unavailable("configuration_not_authorized", "INVALID"); return;
    }
    const sourcePresent = inputByName(node, "source_video")?.link != null;
    const occurrences = costMediaOccurrences(node, topology);
    pruneCostMetadataWatches(node);
    const media = occurrences ? occurrences.map(occurrence => readNativeCostMetadata(node, occurrence)) :
        referenceKinds.map(kind => ({ kind, role: "reference", status: "UNKNOWN" }));
    media.forEach((item, occurrence_index) => { item.occurrence_index = occurrence_index; item.context_revision = revision; });
    const factor = projectedWidgetValue(node, "upscale_factor");
    const payload = {
        schema_version: 2, context_revision: revision,
        model_id: model, duration: projectedWidgetValue(node, "duration"),
        resolution: geometryAuthority(node) === "EXACT" ? null : projectedWidgetValue(node, "resolution"),
        aspect_ratio: geometryAuthority(node) === "EXACT" ? null : projectedWidgetValue(node, "aspect_ratio"),
        size: geometryAuthority(node) === "NORMALIZED" ? null : projectedWidgetValue(node, "size"),
        generate_audio: projectedWidgetValue(node, "generate_audio"),
        inference_method: widget(node, "inference_method")?.value,
        reference_kinds: referenceKinds, reference_count: referenceKinds.length,
        source_video_present: sourcePresent, media,
        upscale_factor: factor == null ? null : String(factor),
        creativity: projectedWidgetValue(node, "creativity"),
        provider_policy_version: "ACI-1.0", provider_controls: costControls.controls,
    };
    const signature = JSON.stringify({ ...payload, context_revision: 0, catalogue: catalogueSignature });
    // No indefinitely reusable estimate. Existing catalogue service owns freshness.
    const started = costClock();
    try {
        const response = await api.fetchApi("/openrouter-video/v1/cost-estimate", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error("estimate unavailable");
        const result = await response.json();
        if (revision !== node.__orvEstimateRevision || result.context_revision !== revision) return;
        if (!Number.isFinite(result.valid_for_ms) || result.valid_for_ms <= 0) {
            setCostPresentation(node, { state: "STALE", reason_codes: ["pricing_evidence_stale"] }); return;
        }
        result.valid_for_ms = Math.max(0, Math.min(900000, result.valid_for_ms) - (costClock() - started));
        if (!result.valid_for_ms) { setCostPresentation(node, { state: "STALE", reason_codes: ["pricing_evidence_stale"] }); return; }
        node.__orvCostAcceptedSignature = signature;
        node.__orvCostAcceptedResult = result;
        setCostPresentation(node, result);
    } catch {
        if (revision !== node.__orvEstimateRevision) return;
        unavailable("pricing_request_unavailable");
    }
}

function bindEstimateRefresh(node) {
    for (const item of node.widgets || []) {
        if (item.name === "COST" || item.name === "Advanced") continue;
        const previous = item.callback;
        item.callback = function (...args) {
            previous?.apply(this, args);
            if (["model", "inference_method", "resolution", "aspect_ratio", "size", "duration", "generate_audio", "upscale_factor", "creativity", "provider_options"].includes(item.name)) {
                invalidateCostPresentation(node);
            }
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
            if (item.name === "duration" && Number(widget(node, "duration")?.value) !== 0) {
                configureDuration(node, node.__orvDurationValues);
                scheduleBetaPresentation([node]);
            }
            if (["resolution", "aspect_ratio", "size"].includes(item.name)) scheduleCostRefresh(node);
            else scheduleTopologyRefresh(node, () => projectSelectedModel(node));
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
    invalidateCostPresentation(node);
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
            setCostPresentation(node, { state: "STALE", reason_codes: ["pricing_evidence_stale"] });
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
        installActualQueueObserver();
        api.addEventListener("promptQueueing", event => captureActualQueueTicket(event.detail));
        api.addEventListener("promptQueued", event => actualQueueTickets.delete(event.detail?.requestId));
        api.addEventListener("executed", event => handleActualExecuted(event.detail));
        api.addEventListener("graphCleared", () => resetActualGraph(app.rootGraph || app.graph));
        for (const name of ["execution_error", "execution_interrupted"]) api.addEventListener(name, event => {
            if (actualText(event.detail?.prompt_id)) {
                actualDispatches.delete(event.detail.prompt_id);
                actualEarlyEvents.delete(event.detail.prompt_id);
            }
        });
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
    beforeConfigureGraph() {
        resetActualGraph(app.rootGraph || app.graph);
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name === "OpenRouterVideoResume") {
            const created = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function (...args) {
                const result = created?.apply(this, args);
                suppressPackageBadge(this);
                installResumeActualPresentation(this);
                return result;
            };
            return;
        }
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
            claimDirectReferenceTopology(this);
            // LGraphNode.configure emits input callbacks before onConfigure.
            // Mark reconstruction at entry, including standalone undo/configure.
            this.__orvConfiguringMedia = true;
            this.__orvProjectionVersion = (this.__orvProjectionVersion || 0) + 1;
            try { return previousNodeConfigure.apply(this, args); }
            catch (error) { this.__orvConfiguringMedia = false; throw error; }
        };
        const previousConnectInput = nodeType.prototype.onConnectInput;
        nodeType.prototype.onConnectInput = function (slot, type, output, origin, originSlot, ...rest) {
            if (!claimDirectReferenceTopology(this)) return false;
            if (previousConnectInput?.call(this, slot, type, output, origin, originSlot, ...rest) === false) return false;
            if (app.configuringGraph || this.__orvConfiguringMedia || this.__orvReconcilingMedia) return true;
            normalizeImportedReferenceInputs(this);
            if (this.__orvReferenceAliasConflict) return false;
            const input = this.inputs?.[slot];
            if (!input || !isMediaInput(input) || !this.__orvCapability) return;
            if (!projectionMatchesSelection(this) || this.__orvPendingMediaSelection) return false;
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
            if (!claimDirectReferenceTopology(this)) return;
            const result = previousConnectionsChange?.apply(this, args);
            if (app.configuringGraph || this.__orvReconcilingMedia || this.__orvConfiguringMedia) return result;
            // Establish occurrence order at the connection event, before a second
            // connection can arrive during the debounced catalogue projection.
            captureMediaIntent(this);
            this.__orvEstimateRevision = (this.__orvEstimateRevision || 0) + 1;
            if (this.__orvEstimate) setCostPresentation(this, { state: "CALCULATING" });
            const hasMedia = this.inputs?.some(isMediaInput);
            if (hasMedia) {
                scheduleTopologyRefresh(this, () => {
                    if (this.__orvCapability && projectionMatchesSelection(this) && !this.__orvPendingMediaSelection) {
                        configureReferenceTopology(
                            this,
                            this.__orvCapability,
                            widget(this, "inference_method")?.value,
                        );
                    }
                    projectSelectedModel(this);
                });
            }
            return result;
        };
        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = previousCreated?.apply(this, args);
            for (const item of this.widgets || []) if (item.name?.startsWith("provider_option:")) setVisible(item,false);
            claimDirectReferenceTopology(this);
            createGeometryCombos(this);
            this.__orvIsNewNode = true;
            // Hidden nonserialized compatibility slot preserves legacy positional order.
            this.__orvAdvanced = this.addWidget("button", "Advanced", "", null);
            this.__orvAdvanced.serialize = false;
            setVisible(this.__orvAdvanced, false);
            this.__orvSummary = addReadOnlyWidget(this, "REFERENCES", "");
            this.__orvSummary.label = " ";
            this.__orvSummary.__orvComputeSize = () => [0, capacityMeterHeight(this)];
            this.__orvSummary.draw = (ctx, node, width, y) => drawCapacityMeter(ctx,node,width,y);
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
            installCostLifecycle(this);
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
            delete this.__orvMasterPromptHeight;
            const promptGeometry=args[0]?.properties?.orv_prompt_geometry;
            if(!promptGeometry && this.properties)delete this.properties.orv_prompt_geometry;
            if(promptGeometry?.version===2 && Number.isFinite(promptGeometry.height) && promptGeometry.height>=0) this.__orvMasterPromptHeight=promptGeometry.height;
            if (Array.isArray(args[0]?.size) && args[0].size.length === 2 && args[0].size.every(Number.isFinite)) this.__orvRestoreGeometry = [...args[0].size];
            claimDirectReferenceTopology(this);
            cancelTopologyRefresh(this);
            clearTimeout(this.__orvCostRefreshTimer);
            resetActualBinding(this);
            clearCostMetadataWatches(this);
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
            normalizeImportedReferenceInputs(this);
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
