import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { r31HistoricalSource } from './aci_r31_reviewed_patch.mjs';

// Read actual current source, never the historical-shield substitution helper.
const root = new URL('../../', import.meta.url);
const before = execFileSync('git', ['show', 'f8ba174347bd4bfed155dc64aec1d7168c39c1fa:web/openrouter_video.js'],
    { cwd:root, encoding:'utf8' }).replace(/\r\n/g, '\n');
const after = r31HistoricalSource(root, 'web/openrouter_video.js',
    readFileSync(new URL('web/openrouter_video.js', root), 'utf8').replace(/\r\n/g, '\n'));
const functions = text => Object.fromEntries(text.split(/(?=^function |^async function )/m).slice(1)
    .map(part => [part.match(/function (\w+)/)[1], part.slice(0, part.indexOf('\n}') + 2)]));
const changedCost = new Set(['applyPresentation', 'createEstimateState', 'installBetaPresentation',
    'syncBetaPresentation', 'refreshCatalogue', 'refreshEstimate', 'bindEstimateRefresh', 'projectSelectedModel']);
const addedCost = new Set(['costMoney', 'drawCollapsedCostBadge', 'costBadgeText', 'costDetailsText',
    'costReasonText', 'setCostPresentation', 'invalidateCostPresentation', 'discardCurrentCost',
    'bindCostBadge', 'syncClassicCostBadge', 'costMediaOccurrences', 'readNativeCostMetadata',
    'projectProviderCostControls']);

test('ACI leaves every existing non-cost function exact, including OP07 projection and media intent', () => {
    const a=functions(before),b=functions(after);
    for(const [name,text] of Object.entries(a)) if(!changedCost.has(name)) assert.equal(b[name],text,name);
    for(const name of Object.keys(b)) if(!(name in a)) assert(addedCost.has(name),`Undeclared new function: ${name}`);
    assert.equal(after.split(/(?=^function |^async function )/m)[0],
        before.split(/(?=^function |^async function )/m)[0], 'global method labels, identity and constants');
});

test('ACI registration changes only cost invalidation, not graph reconstruction or execution', () => {
    const registration=text=>text.slice(text.indexOf('app.registerExtension({'));
    const current=registration(after).replace(
        '            if (this.__orvEstimate) setCostPresentation(this, { state: "CALCULATING" });\n','');
    assert.equal(current,registration(before));
    assert(!/localStorage|sessionStorage|indexedDB|api\.queuePrompt|\/api\/v1\/videos/.test(after));
});
