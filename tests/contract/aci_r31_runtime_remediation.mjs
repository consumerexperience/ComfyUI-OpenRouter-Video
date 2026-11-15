import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

export const remediationBaseline = 'a39204322349b5d13270c7df3f3e6cc24d12180a';
export const remediationFile = 'web/openrouter_video.js';
const normalized = text => text.replace(/\r\n/g, '\n');
const declaredEdits = [
    ['        "last_frame_url", "geometry_authority",\n',
     '        "last_frame_url", "geometry_authority", "previous_job_id",\n        "upscale_factor", "creativity", "provider_options",\n'],
    ['function capabilityIntent(node) {',
`function normalizeImportedReferenceInputs(node) {
    const inputs = node.inputs || [];
    const aliases = inputs.filter(input => /^reference_\\d+$/.test(input.name))
        .map(input => ({ input, name: \`direct_references.\${input.name}\` }));
    const names = new Set(inputs.map(input => input.name)), targets = new Set();
    node.__orvReferenceAliasConflict = false;
    for (const { name } of aliases) {
        if (names.has(name) || targets.has(name)) {
            node.__orvReferenceAliasConflict = true;
            node.__orvReferenceInvalid = true;
            return;
        }
        targets.add(name);
    }
    // Native inputs are hydrated at onConfigure. Rename only after validating
    // every alias, without replacing sockets or touching their slots/links.
    for (const { input, name } of aliases) input.name = name;
}

function capabilityIntent(node) {`],
    ['function captureMediaIntent(node) {\n',
`function captureMediaIntent(node) {
    if (node.__orvReferenceAliasConflict) {
        node.__orvMediaIntentInvalid = true;
        return [];
    }
`],
    ['function reconcileReferenceTopology(node, capability, method, transition) {\n',
`function reconcileReferenceTopology(node, capability, method, transition) {
    if (node.__orvReferenceAliasConflict) {
        node.__orvReferenceInvalid = true;
        disclose(node, "CONFLICTING REFERENCE INPUT NAMES; saved state preserved; Generate blocked");
        return;
    }
`],
    ['            const result = previousConfigure?.apply(this, args);\n',
     '            const result = previousConfigure?.apply(this, args);\n            normalizeImportedReferenceInputs(this);\n'],
];

// Raw current-source equality against the exact approved five edits. No historical
// routing is involved: any other byte change (including pricing/queue/transport)
// rejects the candidate, even if somebody also changes its digest pin.
export function assertRuntimeRemediationScope(root, current) {
    let expected = normalized(execFileSync('git', ['show', `${remediationBaseline}:${remediationFile}`],
        { cwd: root, encoding: 'utf8' }));
    for (const [before, after] of declaredEdits) {
        assert.equal(expected.split(before).length - 1, 1, 'Declared insertion must occur exactly once');
        expected = expected.replace(before, after);
    }
    assert.equal(normalized(current), expected, 'Only the declared import/restore remediation is authorized');
}

export function remediationHistoricalSource(root, file, current) {
    if (file !== remediationFile) return current;
    const path = new URL('tests/fixtures/aci_r31_runtime_remediation_candidate.json', root);
    if (!existsSync(path)) return current;
    const pin = JSON.parse(readFileSync(path, 'utf8'));
    const digest = createHash('sha256').update(normalized(current)).digest('hex');
    if (pin.status !== 'UNACCEPTED' || pin.baseline_sha !== remediationBaseline ||
        pin.candidate_files?.[file] !== digest) return current;
    assertRuntimeRemediationScope(root, current);
    return normalized(execFileSync('git', ['show', `${remediationBaseline}:${file}`],
        { cwd: root, encoding: 'utf8' }));
}

export function remediationCandidateMatches(root, file, digest) {
    if (file !== remediationFile) return false;
    const current = readFileSync(new URL(file, root), 'utf8');
    if (createHash('sha256').update(normalized(current)).digest('hex') !== digest) return false;
    return remediationHistoricalSource(root, file, current) !== current;
}
