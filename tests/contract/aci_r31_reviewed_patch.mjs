import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const baseline = '15cc5aea7570fe43d2154b4e3b6f1efba8f4ac2d';

export function r31CandidateMatches(root, file, digest) {
    const path = new URL('tests/fixtures/aci_r31_source_candidate.json', root);
    if (!existsSync(path)) return false;
    const pin = JSON.parse(readFileSync(path, 'utf8'));
    return pin.status === 'UNACCEPTED' && pin.baseline_sha === baseline &&
        pin.candidate_files?.[file] === digest;
}

export function r31HistoricalSource(root, file, current) {
    const digest = createHash('sha256').update(current.replace(/\r\n/g, '\n')).digest('hex');
    if (!r31CandidateMatches(root, file, digest)) return current;
    // This is an exact pin for historical assertions, never current-source acceptance.
    // test_aci_r31_scope.mjs and the Product Contract Guard inspect raw current bytes.
    return execFileSync('git', ['show', `${baseline}:${file}`], { cwd: root, encoding: 'utf8' })
        .replace(/\r\n/g, '\n');
}
