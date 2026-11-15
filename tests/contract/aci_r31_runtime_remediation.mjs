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
            while (names.has(\`direct_references.reference_\${index}\`) ||
                targets.has(\`direct_references.reference_\${index}\`)) index++;
            alias.name = \`direct_references.reference_\${index}\`;
        }
        targets.add(alias.name);
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
    const pin = JSON.parse(readFileSync(new URL('tests/fixtures/aci_r31_runtime_remediation_candidate.json', root), 'utf8'));
    if (pin.presentation_functions) {
        for (const [before, after] of [
            ['border-radius:9px; padding:2px 6px; color:var(--input-text, #ddd); font-size:12px;',
             'border-radius:6px; padding:1px 7px; color:var(--input-text, #ddd); font:600 11px/16px Arial, Helvetica, sans-serif;'],
            ['        ctx.font = "12px sans-serif";\n        const badgeWidth =',
             '        ctx.font = "600 11px Arial, Helvetica, sans-serif";\n        const badgeWidth ='],
            ['        if (ctx.roundRect) ctx.roundRect(width - badgeWidth - 10, -27, badgeWidth, 21, 9);',
             '        if (ctx.roundRect) ctx.roundRect(width - badgeWidth - 10, -27, badgeWidth, 21, 6);'],
        ]) {
            assert.equal(expected.split(before).length - 1, 1);
            expected = expected.replace(before, after);
        }
        const allowed = ['syncBetaPresentation', 'actualCostText', 'renderCostDetails', 'costDetailAccent',
            'costBadgeText', 'costDetailsText', 'bindCostBadge', 'syncClassicCostBadge',
            'costBadgeLabel', 'costBadgeColors', 'createEstimateState', 'installCostLifecycle', 'drawCollapsedCostBadge'];
        const added = { costCompactDecimal: 'actualText', costAdvisoryComparison: 'actualText',
            costLocale:'actualText', costText:'actualText', costUsd:'actualText', costRangeUsd:'actualText',
            costReferenceRows:'actualText', costRateLabel:'actualText', costTooltipView:'actualText', costPriceView:'actualText',
            costTechnicalDetailsText: 'costReasonText', positionCostTooltip:'syncClassicCostBadge' };
        const find = (text, name) => {
            const matches = [...text.matchAll(new RegExp(`^function ${name}\\([^\\n]*\\) \\{[\\s\\S]*?^\\}\\n`, 'gm'))];
            assert.equal(matches.length, 1, `Unique presentation function ${name}`);
            return matches[0][0];
        };
        for (const name of Object.keys(pin.presentation_functions)) assert([...allowed, ...Object.keys(added)].includes(name));
        for (const name of [...allowed, ...Object.keys(added)]) {
            const body = find(normalized(current), name);
            assert.equal(createHash('sha256').update(body).digest('hex'), pin.presentation_functions[name], `${name} exact reviewed bytes`);
            if (name !== 'syncBetaPresentation') assert(!/api\.|fetch\(|queuePrompt\(|handleActualExecuted\(/.test(body), 'Presentation cannot submit or change execution ownership');
            if (added[name]) expected = expected.replace(`function ${added[name]}(`, () => body + `\nfunction ${added[name]}(`);
            else expected = expected.replace(find(expected, name), () => body);
        }
    }
    if (normalized(current) !== expected) {
        const index = [...normalized(current)].findIndex((char, i) => char !== expected[i]);
        assert.fail(`Undeclared source delta near ${index}: current=${JSON.stringify(normalized(current).slice(index - 30, index + 90))} expected=${JSON.stringify(expected.slice(index - 30, index + 90))}`);
    }
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
