import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { remediationHistoricalSource } from './aci_r31_runtime_remediation.mjs';

const root = new URL('../../', import.meta.url);
const before = execFileSync('git', ['show', '15cc5aea7570fe43d2154b4e3b6f1efba8f4ac2d:web/openrouter_video.js'],
    { cwd: root, encoding: 'utf8' }).replace(/\r\n/g, '\n');
// R3.1 assertions retain their exact historical source only after the separate
// raw-current remediation guard passes; the older R3.1 pin remains unchanged.
const after = remediationHistoricalSource(root, 'web/openrouter_video.js',
    readFileSync(new URL('web/openrouter_video.js', root), 'utf8').replace(/\r\n/g, '\n'));
const functions = source => Object.fromEntries(source.split(/(?=^function |^async function )/m).slice(1).map(part => {
    const end = part.indexOf('\n}');
    return [part.match(/function (\w+)/)[1], end < 0 ? part.split('\n')[0] : part.slice(0, end + 2)];
}));
const changed = new Set(['applyPresentation', 'bindCostBadge', 'costBadgeText', 'costDetailsText',
    'costMoney', 'drawCollapsedCostBadge', 'readNativeCostMetadata', 'refreshEstimate',
    'setCostPresentation', 'syncBetaPresentation', 'syncClassicCostBadge']);
const added = new Set(['actualCostText', 'actualMoney', 'actualOwnersForQueuedPrompt', 'actualText',
    'captureActualQueueTicket', 'clearCostMetadataWatches', 'costBadgeColors', 'costBadgeLabel',
    'costClock', 'costDecimalShift', 'costDetailAccent', 'currentActualEpoch',
    'currentCostMetadataOccurrence', 'emptyActualState', 'expireCostPresentation',
    'handleActualExecuted', 'installActualQueueObserver', 'installCostLifecycle',
    'installResumeActualPresentation', 'nativeCostSelection', 'pruneActualBindings',
    'pruneCostMetadataWatches', 'reduceActualCompletion', 'refreshCostDetails',
    'resetActualBinding', 'sameActualAmount', 'syncCostDetailAccent',
    'checkNativeCostMetadata', 'drawCostBadgeLabel', 'setCostBadgeLabel',
    'renderCostDetails', 'resetActualGraph', 'observeNativeCostSelection',
    'suppressActualCompletion']);

test('R3.1 preserves every existing non-cost function, topology, capability and geometry algorithm', () => {
    const a = functions(before), b = functions(after);
    for (const [name, body] of Object.entries(a)) if (!changed.has(name)) assert.equal(b[name], body, name);
    for (const name of Object.keys(b)) if (!(name in a)) assert(added.has(name), `Unapproved helper: ${name}`);
});

test('R3.1 preserves all existing global identity, method labels and node chrome', () => {
    const prefix = source => source.split(/(?=^function |^async function )/m)[0];
    const old = prefix(before).trimEnd(), current = prefix(after);
    assert(current.startsWith(old + '\n'));
    const allowed = `// Cost presentation only. Object identity never leaves this process or a workflow.
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
let costLifecycleInstalled = false;`;
    assert.equal(current.slice(old.length).trim(), allowed);
});

test('R3.1 registration adds only passive cost and ACTUAL lifecycle hooks', () => {
    const registration = source => source.slice(source.indexOf('app.registerExtension({'));
    let current = registration(after);
    const inserts = [
`        installActualQueueObserver();
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
`,
`        if (nodeData?.name === "OpenRouterVideoResume") {
            const created = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function (...args) {
                const result = created?.apply(this, args);
                installResumeActualPresentation(this);
                return result;
            };
            return;
        }
`,
`            installCostLifecycle(this);
`,
`            resetActualBinding(this);
            clearCostMetadataWatches(this);
`,
`    beforeConfigureGraph() {
        resetActualGraph(app.rootGraph || app.graph);
    },
`];
    for (const insertion of inserts) {
        assert.equal(current.split(insertion).length - 1, 1, 'Expected one declared lifecycle insertion');
        current = current.replace(insertion, '');
    }
    assert.equal(current, registration(before));
});

test('R3.1 queue observer never initiates a queue, retries, or introduces upstream transport', () => {
    const observer = functions(after).installActualQueueObserver;
    assert.equal((observer.match(/original\.apply\(this, args\)/g) || []).length, 1);
    assert(observer.includes('return result;'));
    assert(!/\b(?:api|app)\.queuePrompt\s*\(/.test(after));
    assert(!/localStorage|sessionStorage|indexedDB|Authorization\s*:|\/api\/v1\/videos/.test(after));
    assert(!/JSON\.stringify\(prompt\)|structuredClone\(prompt\)/.test(observer));
});
