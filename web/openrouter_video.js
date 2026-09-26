import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION = "openrouter-video.capability-driven-ui";
const GENERATE_NODE = "OpenRouterVideoGenerate";
const SELECT_MODEL = "SELECT MODEL";
const AUTO = "AUTO / MODEL DEFAULT";
const GEOMETRY_AUTO = "AUTO / MODEL DEFAULT";
const GEOMETRY_RESOLUTION = "RESOLUTION + ASPECT RATIO";
const GEOMETRY_SIZE = "EXACT SIZE";
const DURATION_AUTO = "AUTO / MODEL DEFAULT";
const DURATION_EXPLICIT = "EXPLICIT DURATION";

let capabilityPromise;

function widget(node, name) {
    return node.widgets?.find((item) => item.name === name);
}

function setVisible(item, visible) {
    if (!item) return;
    item.hidden = !visible;
    item.computeSize = visible ? undefined : () => [0, -4];
}

function addReadOnlyWidget(node, name, initial) {
    const item = node.addWidget("text", name, initial, null, { multiline: false });
    item.serialize = false;
    item.disabled = true;
    return item;
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
    if (!item || item.value === "" || item.value === AUTO || item.value === 0) return null;
    return item.value;
}

function disclose(node, message) {
    if (!message) return;
    const status = node.__orvCapabilityStatus;
    status.value = message;
    node.setDirtyCanvas?.(true, true);
}

function configureEnum(node, item, supported, label) {
    if (!item) return;
    const current = normalizedValue(item);
    item.type = "combo";
    item.options = item.options || {};
    if (supported === null) {
        item.options.values = current === null ? [AUTO] : [AUTO, current];
        if (current !== null) disclose(node, `${label}: saved value is not verified by catalogue`);
        return;
    }
    item.options.values = [AUTO, ...supported];
    if (current !== null && !supported.includes(current)) {
        item.value = AUTO;
        disclose(node, `${label}: unsupported saved value reset to AUTO`);
    } else if (current === null) {
        item.value = AUTO;
    }
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

function configureDuration(node, supported) {
    const item = widget(node, "duration");
    if (!item) return;
    node.__orvDurationValues = supported;
    const current = Number(item.value || 0);
    const mode = node.__orvDurationMode;
    if (current > 0) mode.value = DURATION_EXPLICIT;
    item.options = item.options || {};
    if (mode.value === DURATION_AUTO) {
        item.value = 0;
        setVisible(item, false);
        return;
    }
    setVisible(item, true);
    if (supported === null) {
        item.type = "combo";
        item.options.values = current > 0 ? [0, current] : [0];
        if (current > 0) disclose(node, "DURATION: saved value is not verified by catalogue");
        return;
    }
    const values = [...supported].sort((left, right) => left - right);
    if (current > 0 && !values.includes(current)) {
        item.value = 0;
        mode.value = DURATION_AUTO;
        setVisible(item, false);
        disclose(node, "DURATION: unsupported saved value reset to AUTO");
        return;
    }
    const step = arithmeticStep(values);
    if (current === 0 && values.length > 1) {
        item.type = "combo";
        item.options.values = [0, ...values];
        disclose(node, "DURATION: select an explicit supported value");
    } else if (values.length > 1 && step !== null) {
        item.type = "number";
        item.options.min = values[0];
        item.options.max = values.at(-1);
        item.options.step = step;
        item.options.precision = 0;
    } else {
        item.type = "combo";
        item.options.values = values;
        if (values.length === 1 && current === 0) item.value = values[0];
    }
}

function supportedReference(capability, mode) {
    return capability.normalized_reference_modes?.find((item) => item.mode === mode)?.status;
}

function configureGeometry(node, capability) {
    configureEnum(node, widget(node, "resolution"), capability.supported_resolutions, "RESOLUTION");
    configureEnum(
        node,
        widget(node, "aspect_ratio"),
        capability.supported_aspect_ratios,
        "ASPECT RATIO",
    );
    configureEnum(node, widget(node, "size"), capability.supported_sizes, "EXACT SIZE");

    const mode = node.__orvGeometryMode;
    const resolution = normalizedValue(widget(node, "resolution"));
    const aspect = normalizedValue(widget(node, "aspect_ratio"));
    const size = normalizedValue(widget(node, "size"));
    if (size !== null) mode.value = GEOMETRY_SIZE;
    else if (resolution !== null || aspect !== null) mode.value = GEOMETRY_RESOLUTION;
    else if (![GEOMETRY_AUTO, GEOMETRY_RESOLUTION, GEOMETRY_SIZE].includes(mode.value)) {
        mode.value = GEOMETRY_AUTO;
    }
    applyGeometryMode(node);
}

function applyGeometryMode(node) {
    const mode = node.__orvGeometryMode?.value || GEOMETRY_AUTO;
    const resolution = widget(node, "resolution");
    const aspect = widget(node, "aspect_ratio");
    const size = widget(node, "size");
    setVisible(resolution, mode === GEOMETRY_RESOLUTION);
    setVisible(aspect, mode === GEOMETRY_RESOLUTION);
    setVisible(size, mode === GEOMETRY_SIZE);
    if (mode === GEOMETRY_AUTO) {
        if (resolution) resolution.value = AUTO;
        if (aspect) aspect.value = AUTO;
        if (size) size.value = AUTO;
    } else if (mode === GEOMETRY_RESOLUTION && size) {
        size.value = AUTO;
    } else if (mode === GEOMETRY_SIZE) {
        if (resolution) resolution.value = AUTO;
        if (aspect) aspect.value = AUTO;
    }
}

function selectedReferenceMode(node) {
    const first = normalizedValue(widget(node, "first_frame_url"));
    const last = normalizedValue(widget(node, "last_frame_url"));
    const referenceInput = node.inputs?.find((item) => item.name === "input_references");
    if (referenceInput?.link != null) return null;
    if (first !== null && last !== null) return "first_plus_last";
    if (first !== null) return "first_frame";
    return "none";
}

async function refreshEstimate(node) {
    const model = widget(node, "model")?.value;
    if (!model || model === SELECT_MODEL) {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — SELECT MODEL";
        return;
    }
    const referenceMode = selectedReferenceMode(node);
    if (referenceMode === null) {
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — REFERENCE SHAPE RESOLVES AT EXECUTION";
        return;
    }
    const payload = {
        model_id: model,
        duration: normalizedValue(widget(node, "duration")),
        resolution: normalizedValue(widget(node, "resolution")),
        aspect_ratio: normalizedValue(widget(node, "aspect_ratio")),
        size: normalizedValue(widget(node, "size")),
        generate_audio: Boolean(widget(node, "generate_audio")?.value),
        reference_mode: referenceMode,
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
        if (["CAPABILITY STATUS", "ESTIMATED COST"].includes(item.name)) continue;
        const previous = item.callback;
        item.callback = function (...args) {
            previous?.apply(this, args);
            if (item.name === "model") {
                projectSelectedModel(node);
                return;
            }
            if (item.name === "duration" && Number(item.value) > 0) {
                configureDuration(node, node.__orvDurationValues);
            }
            clearTimeout(node.__orvEstimateTimer);
            node.__orvEstimateTimer = setTimeout(() => refreshEstimate(node), 120);
        };
    }
}

async function projectSelectedModel(node, force = false) {
    node.__orvCapabilityStatus.value = "LOADING CAPABILITIES";
    try {
        const projection = await loadCapabilities(force);
        const model = widget(node, "model")?.value;
        if (!model || model === SELECT_MODEL) {
            node.__orvCapabilityStatus.value = "SELECT MODEL";
            node.__orvEstimate.value = "ESTIMATE UNAVAILABLE — SELECT MODEL";
            return;
        }
        const capability = projection.models.find((item) => item.model_id === model);
        if (!capability) {
            widget(node, "model").value = SELECT_MODEL;
            disclose(node, "SAVED MODEL IS NOT PRESENT IN CURRENT CATALOGUE");
            return;
        }
        node.__orvCapabilityStatus.value = `CATALOGUE ${capability.observed_at}`;
        configureDuration(node, capability.supported_durations);
        configureGeometry(node, capability);
        const seed = widget(node, "seed");
        setVisible(seed, capability.supports_seed === true);
        if (capability.supports_seed === true) {
            seed.options.min = 0;
            if (Number(seed.value) < 0) seed.value = 0;
        } else {
            seed.value = -1;
        }
        setVisible(widget(node, "generate_audio"), capability.generate_audio === true);
        if (capability.generate_audio !== true) widget(node, "generate_audio").value = false;
        const frames = capability.supported_frame_types;
        const firstFrame = widget(node, "first_frame_url");
        const lastFrame = widget(node, "last_frame_url");
        const firstSupported = frames?.includes("first_frame") === true;
        const lastSupported = frames?.includes("last_frame") === true;
        if (!firstSupported && normalizedValue(firstFrame) !== null) {
            firstFrame.value = "";
            disclose(node, "FIRST FRAME: unsupported saved value reset to omission");
        }
        if (!lastSupported && normalizedValue(lastFrame) !== null) {
            lastFrame.value = "";
            disclose(node, "LAST FRAME: unsupported saved value reset to omission");
        }
        setVisible(firstFrame, firstSupported);
        setVisible(lastFrame, lastSupported);
        const referenceStates = [
            "multi_image_reference",
            "video_reference",
            "image_plus_video_reference",
        ].map((mode) => supportedReference(capability, mode));
        if (referenceStates.every((status) => status !== "ENFORCED")) {
            disclose(node, "INPUT REFERENCES: not positively authorized for selected model");
        }
        await refreshEstimate(node);
    } catch {
        node.__orvCapabilityStatus.value = "CAPABILITY PROJECTION UNAVAILABLE — SUBMIT BLOCKED BY CORE";
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
    }
    node.setSize?.(node.computeSize?.());
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: EXTENSION,
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== GENERATE_NODE) return;
        const previousCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = previousCreated?.apply(this, args);
            this.__orvCapabilityStatus = addReadOnlyWidget(this, "CAPABILITY STATUS", "SELECT MODEL");
            this.__orvEstimate = addReadOnlyWidget(
                this,
                "ESTIMATED COST",
                "ESTIMATE UNAVAILABLE — SELECT MODEL",
            );
            this.__orvGeometryMode = this.addWidget(
                "combo",
                "OUTPUT GEOMETRY",
                GEOMETRY_AUTO,
                () => {
                    applyGeometryMode(this);
                    refreshEstimate(this);
                },
                { values: [GEOMETRY_AUTO, GEOMETRY_RESOLUTION, GEOMETRY_SIZE] },
            );
            this.__orvDurationMode = this.addWidget(
                "combo",
                "DURATION MODE",
                DURATION_AUTO,
                () => {
                    if (this.__orvDurationMode.value === DURATION_AUTO) {
                        widget(this, "duration").value = 0;
                    }
                    configureDuration(this, this.__orvDurationValues ?? null);
                    refreshEstimate(this);
                },
                { values: [DURATION_AUTO, DURATION_EXPLICIT] },
            );
            migratePhase8Values(this);
            bindEstimateRefresh(this);
            setTimeout(() => projectSelectedModel(this), 0);
            return result;
        };

        const previousConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = previousConfigure?.apply(this, args);
            migratePhase8Values(this);
            setTimeout(() => projectSelectedModel(this), 0);
            return result;
        };
    },
});
