import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { package02AmendmentBaselineSource } from './package02_amendment_delta.mjs';
import { assertRuntimeRemediationScope, remediationBaseline, remediationFile,
    remediationHistoricalSource, integratedHistoricalSource, integratedAuthorizedBackendDelta,
    assertIntegratedCandidate } from './aci_r31_runtime_remediation.mjs';

const root = new URL('../../', import.meta.url);
const current = readFileSync(new URL(remediationFile, root), 'utf8').replace(/\r\n/g, '\n');

test('raw current source differs from a392043 only by declared import/restore edits', () => {
    assertRuntimeRemediationScope(root, current);
});

test('all tracked backend/data source remains exact against a392043', () => {
    const files = execFileSync('git', ['ls-tree', '-r', '--name-only', remediationBaseline, 'src'],
        { cwd: root, encoding: 'utf8' }).trim().split('\n');
    for (const file of files) {
        const expected = execFileSync('git', ['show', `${remediationBaseline}:${file}`],
            { cwd: root, encoding: 'utf8' }).replace(/\r\n/g, '\n');
        assert.equal(integratedHistoricalSource(root,file,readFileSync(new URL(file, root), 'utf8'),remediationBaseline), expected, file);
    }
    assert.equal(integratedAuthorizedBackendDelta(root,remediationBaseline,execFileSync('git', ['diff', '--name-only', remediationBaseline, '--', 'src'],
        { cwd: root, encoding: 'utf8' }).trim()), '', 'No undeclared tracked backend/data additions or changes');
    assert.equal(execFileSync('git', ['ls-files', '--others', '--exclude-standard', 'src'],
        { cwd: root, encoding: 'utf8' }).trim(), '', 'No added backend/data source');
});

test('R2 locale hook leaves ACTUAL lifecycle and ownership bookkeeping exact against 111805b',()=>{
    const prior=execFileSync('git',['show','111805bb151daccb48e95d8a748a728d5a7d93d4:web/openrouter_video.js'],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n');
    const body=text=>text.match(/^function installCostLifecycle\([^\n]*\) \{[\s\S]*?^\}\n/m)[0];
    const hook='    app.ui?.settings?.addEventListener?.("Comfy.Locale.change", () => {\n        for (const current of costPresentationNodes) {\n            if (current.__orvEstimate?.result) current.__orvEstimate.value = costBadgeText(current.__orvEstimate.result);\n            refreshCostDetails(current);\n        }\n    });\n';
    assert.equal(body(integratedHistoricalSource(root,remediationFile,current,'4026c34')).replace(hook,''),body(prior));
});

test('final cumulative declaration permits only reviewed source plus two exact diagnostic replacements',()=>{
    assertIntegratedCandidate(root,current);
    for(const changed of [current+'\n// undeclared\n',current.replace('return []','return [1]'),current.replace('pricing_request_unavailable','invented_transport_reason')]) {
        assert.throws(()=>assertIntegratedCandidate(root,changed));
        assert.equal(integratedHistoricalSource(root,remediationFile,changed,remediationBaseline),changed);
    }
    const golden=execFileSync('git',['show','4f49c9b:web/openrouter_video.js'],{cwd:root,encoding:'utf8'}).replace(/\r\n/g,'\n');
    const observer=t=>t.match(/^function installActualQueueObserver\([^\n]*\) \{[\s\S]*?^\}\n/m)[0];
    assert.equal(observer(package02AmendmentBaselineSource(root,remediationFile,current)),observer(golden));
    assert.equal((current.match(/api\.queuePrompt/g)||[]).length,(golden.match(/api\.queuePrompt/g)||[]).length);
});

test('exact UNACCEPTED pin routes historical assertions only after raw current guard passes', () => {
    const historical = execFileSync('git', ['show', `${remediationBaseline}:${remediationFile}`],
        { cwd: root, encoding: 'utf8' }).replace(/\r\n/g, '\n');
    assert.equal(remediationHistoricalSource(root, remediationFile, current), historical);
    const changed = current.replace('return []', 'return [1]');
    assert.equal(remediationHistoricalSource(root, remediationFile, changed), changed);
    assert.throws(() => assertRuntimeRemediationScope(root, changed));
    assert.throws(() => assertRuntimeRemediationScope(root, current + '\n// undeclared\n'));
});
