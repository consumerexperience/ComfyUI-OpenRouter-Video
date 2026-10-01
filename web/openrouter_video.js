import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const EXTENSION = "openrouter-video.capability-driven-ui";
const GENERATE_NODE = "OpenRouterVideoGenerate";
const SELECT_MODEL = "SELECT MODEL";
const AUTO = "AUTO / MODEL DEFAULT";
const UI_CONTRACT_VERSION = 4;
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

function widget(node, name) {
    return node.widgets?.find((item) => item.name === name);
}

function setVisible(item, visible) {
    if (!item) return;
    item.hidden = !visible;
    item.computeSize = visible ? item.__orvComputeSize : () => [0, -4];
}

function addReadOnlyWidget(node, name, initial) {
    const item = node.addWidget("text", name, initial, null, { multiline: false });
    item.serialize = false;
    item.options = item.options || {};
    item.options.readOnly = true;
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
    for (const name of [
        "model", "inference_method", "resolution", "aspect_ratio",
        "duration", "seed", "generate_audio",
    ]) setMinimumWidgetHeight(widget(node, name), 38);
    setMinimumWidgetHeight(widget(node, "prompt"), 92);
    setMinimumWidgetHeight(node.__orvAdvanced, 40);
}

function stylePrompt(node) {
    const element = widget(node, "prompt")?.element;
    if (!element?.style) return;
    element.placeholder = "Prompt";
    element.style.background = "#20272a";
    element.style.border = "1px solid #354540";
    element.style.borderRadius = "9px";
    element.style.color = "#e4ece9";
    element.style.fontSize = "14px";
    element.style.padding = "9px 11px";
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
        seed: "Seed", generate_audio: "Generate Audio",
    };
    for (const item of node.widgets || []) {
        if (labels[item.name]) item.label = labels[item.name];
    }
    sizePrimaryControls(node);
    stylePrompt(node);
    syncAdvancedControls(node);
    setVisible(node.__orvEstimate, false);
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
    let changed = false;
    const show = Boolean(node.__orvAdvancedOpen && canonicalModel(node));
    for (const item of node.widgets || []) {
        const identity = `${item.name || ""} ${item.label || ""}`;
        if (/control[ _]?after[ _]?generate/i.test(identity) && Boolean(item.hidden) === show) {
            setVisible(item, show);
            changed = true;
        }
    }
    const size = widget(node, "size");
    const sizeVerified = Array.isArray(node.__orvCapability?.supported_sizes) &&
        node.__orvCapability.supported_sizes.length > 0;
    const showSize = show && (sizeVerified || normalizedValue(size) !== null);
    if (size && Boolean(size.hidden) === showSize) {
        setVisible(size, showSize);
        changed = true;
    }
    return changed;
}

function fitPresentationWidth(node) {
    const measured = node.computeSize?.();
    if (measured) node.setSize?.([Math.max(560, measured[0]), measured[1]]);
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
        !METHODS.includes(namedValues.inference_method)) return false;
    for (const name of [
        "model", "inference_method", "prompt", "resolution", "aspect_ratio",
        "duration", "size", "seed", "generate_audio", "first_frame_url",
        "last_frame_url",
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
    if (!item || item.value === "" || item.value === AUTO || item.value === 0) return null;
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
        item.options.values.push(current);
        disclose(node, `${label}: incompatible saved value preserved; Generate blocked`);
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
    item.options = item.options || {};
    setVisible(item, true);
    if (supported === null) {
        item.type = "combo";
        item.options.values = current > 0 ? [0, current] : [0];
        if (current > 0) disclose(node, "DURATION: saved value is not verified by catalogue");
        return;
    }
    const values = [...supported].sort((left, right) => left - right);
    if (current > 0 && !values.includes(current)) {
        item.type = "combo";
        item.options.values = [0, ...values, current];
        disclose(node, "DURATION: incompatible saved value preserved; Generate blocked");
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

function isDirectReferenceInput(item) {
    return ["OPENROUTER_VIDEO_INPUT_REFERENCE", "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE"].includes(item?.type) &&
        String(item?.name || "").startsWith("direct_references.reference_");
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
            ? "OPENROUTER_VIDEO_INPUT_REFERENCE"
            : "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE",
    );
    const input = inputByName(node, name);
    if (input) {
        if (name !== "source_video") input.type = "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE";
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

function addTrailingReferenceInput(node, current) {
    if (!node.addInput) return;
    if (current.length === 0) {
        node.addInput(
            "direct_references.reference_0",
            "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE",
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
    const keepFixed = new Set(fixedRolesForMethod(method));
    for (const name of keepFixed) ensureFixedInput(node, name);
    removeUnusedFixedInputs(node, keepFixed);
    for (const name of [...keepFixed].reverse()) moveInputToFrontPreservingLinks(node, name);
    const legacy = inputByName(node, "input_references");
    if (legacy && legacy.link == null) {
        const legacyIndex = node.inputs.indexOf(legacy);
        if (legacyIndex >= 0) node.removeInput?.(legacyIndex);
    }

    const inputs = directReferenceInputs(node);
    for (const input of inputs) input.type = "IMAGE,OPENROUTER_VIDEO_INPUT_REFERENCE";
    const linked = inputs.filter((item) => item.link != null);
    const unlinked = inputs.filter((item) => item.link == null);
    const limit = capability.max_reference_count;
    const effectiveLimit = Number.isInteger(limit) && limit >= 0 ? limit : null;
    const sourceCount = inputByName(node, "source_video")?.link != null ? 1 : 0;
    const reservedSourceCount = keepFixed.has("source_video") ? 1 : 0;
    const usesReferences = methodUsesReferences(method);
    const exactOne = method === "IR2V";
    const keepTrailing = usesReferences &&
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
        addTrailingReferenceInput(node, afterTrim);
    }
    const finalInputs = directReferenceInputs(node).sort(
        (left, right) => referenceInputSuffix(left) - referenceInputSuffix(right),
    );
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

    const currentCount = finalInputs.filter((item) => item.link != null).length;
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
    const supported = capability?.supported_inference_methods || [];
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
    item.disabled = false;
    item.label = "Inference Method";
    let selected = current;
    const hasConnections = connectedRoles(node).some((role) =>
        ["first_frame", "last_frame", "source_video", "references"].includes(role),
    );
    if (
        !selected ||
        (
            node.__orvIsNewNode &&
            !node.__orvMethodInitialized &&
            !node.__orvMethodExplicit &&
            !hasConnections
        )
    ) {
        selected = capability.preferred_inference_method || supported[0] || null;
    }
    item.options.values = selected && !supported.includes(selected)
        ? [...supported, selected]
        : [...supported];
    if (selected) item.value = selected;
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
        if (METHODS.includes(next) && switchWouldOrphan(node, next)) {
            item.value = prior;
            disclose(node, "Disconnect incompatible media before changing Inference Method");
            node.setDirtyCanvas?.(true, true);
            return;
        }
        previous?.apply(this, args);
        node.__orvMethodExplicit = true;
        node.__orvLastMethod = next;
        if (node.__orvCapability) configureReferenceTopology(node, node.__orvCapability, next);
        fitPresentationWidth(node);
    };
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

    const resolution = widget(node, "resolution");
    const aspect = widget(node, "aspect_ratio");
    const size = widget(node, "size");
    setVisible(resolution, true);
    setVisible(aspect, true);
    setVisible(size, normalizedValue(size) !== null);
}

function selectedReferenceKinds(node) {
    const legacy = inputByName(node, "input_references");
    if (legacy?.link != null) return null;
    const connected = directReferenceInputs(node).filter((item) => item.link != null);
    const kinds = connected.map(connectedReferenceKind);
    return kinds.some((kind) => kind === null) ? null : kinds;
}

async function refreshEstimate(node) {
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
    const payload = {
        model_id: model,
        duration: normalizedValue(widget(node, "duration")),
        resolution: normalizedValue(widget(node, "resolution")),
        aspect_ratio: normalizedValue(widget(node, "aspect_ratio")),
        size: normalizedValue(widget(node, "size")),
        generate_audio: Boolean(widget(node, "generate_audio")?.value),
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
            if (item.name === "model") {
                projectSelectedModel(node);
                return;
            }
            if (item.name === "duration" && Number(item.value) > 0) {
                configureDuration(node, node.__orvDurationValues);
            }
            clearTimeout(node.__orvEstimateTimer);
            node.__orvEstimateTimer = setTimeout(() => projectSelectedModel(node), 120);
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
        configureDuration(node, capability.supported_durations);
        configureGeometry(node, capability);
        const seed = widget(node, "seed");
        setVisible(seed, capability.supports_seed === true);
        if (capability.supports_seed === true) {
            seed.options.min = 0;
        } else if (Number(seed.value) >= 0) {
            disclose(node, "SEED: saved value is incompatible; intent preserved and Generate blocked");
        }
        setVisible(widget(node, "generate_audio"), capability.generate_audio === true);
        if (capability.generate_audio !== true && widget(node, "generate_audio")?.value === true) {
            disclose(node, "GENERATE AUDIO: incompatible saved value preserved; Generate blocked");
        }
        setVisible(widget(node, "first_frame_url"), false);
        setVisible(widget(node, "last_frame_url"), false);
        node.__orvCapability = capability;
        const method = configureInferenceMethod(node, capability);
        if (method) configureReferenceTopology(node, capability, method);
        await refreshEstimate(node);
    } catch {
        node.__orvCapabilityStatus.value = "ERROR — CAPABILITIES UNAVAILABLE";
        setVisible(node.__orvCapabilityStatus, true);
        node.__orvEstimate.value = "ESTIMATE UNAVAILABLE";
    }
    setVisible(node.__orvAdvanced, Boolean(canonicalModel(node)));
    syncAdvancedControls(node);
    fitPresentationWidth(node);
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: EXTENSION,
    setup() {
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
            this.__orvIsNewNode = true;
            this.__orvAdvancedOpen = false;
            this.__orvAdvanced = this.addWidget("button", "Advanced", "›", () => {
                this.__orvAdvancedOpen = !this.__orvAdvancedOpen;
                this.__orvAdvanced.value = this.__orvAdvancedOpen ? "⌄" : "›";
                syncAdvancedControls(this);
                fitPresentationWidth(this);
                this.setDirtyCanvas?.(true, true);
            });
            this.__orvAdvanced.serialize = false;
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
            this.__orvEstimate = addReadOnlyWidget(
                this,
                "COST",
                "ESTIMATE UNAVAILABLE — SELECT MODEL",
            );
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
