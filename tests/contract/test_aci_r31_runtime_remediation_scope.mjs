import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import test from 'node:test';
import { assertRuntimeRemediationScope, remediationBaseline, remediationFile,
    remediationHistoricalSource } from './aci_r31_runtime_remediation.mjs';

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
        assert.equal(readFileSync(new URL(file, root), 'utf8').replace(/\r\n/g, '\n'), expected, file);
    }
    assert.equal(execFileSync('git', ['diff', '--name-only', remediationBaseline, '--', 'src'],
        { cwd: root, encoding: 'utf8' }).trim(), '', 'No tracked backend/data additions or changes');
    assert.equal(execFileSync('git', ['ls-files', '--others', '--exclude-standard', 'src'],
        { cwd: root, encoding: 'utf8' }).trim(), '', 'No added backend/data source');
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
