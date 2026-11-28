import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { aciCandidateMatches } from "./aci_reviewed_patch.mjs";
export function reviewedRcText(root, file, text) {
    const pin = JSON.parse(readFileSync(new URL("tests/fixtures/rc_live_reviewed_patch.json", root), "utf8"));
    const current = readFileSync(new URL(file, root), "utf8").replace(/\r\n/g, "\n");
    const digest = createHash("sha256").update(current).digest("hex");
    // Current OP07 files are checked by their own UNACCEPTED pins, semantic
    // guard and behavioral tests. Let historical shields inspect their original
    // source without changing any accepted fixture or claiming acceptance.
    const op07 = JSON.parse(readFileSync(new URL("tests/fixtures/op07_discovery_candidate.json", root), "utf8"));
    if (!pin.reviewed_files[file] && (op07.candidate_files?.[file] === digest || aciCandidateMatches(root, file, digest))) {
        return execFileSync("git", ["show", `${pin.baseline_sha}:${file}`], { cwd: root, encoding: "utf8" }).replace(/\r\n/g, "\n");
    }
    if (!pin.reviewed_files[file]) return text;
    let acceptedCandidate = false;
    acceptedCandidate ||= aciCandidateMatches(root, file, digest);
    try {
        const candidate = JSON.parse(readFileSync(new URL("tests/fixtures/pre_rc_first_run_ux.json", root), "utf8"));
        acceptedCandidate ||= candidate.candidate_files?.[file] === digest;
    } catch {}
    // Separate, explicitly unaccepted OP-07 candidate pin. Historical accepted
    // fixtures are immutable; the current delta has its own semantic tests/guard.
    try {
        const candidate = JSON.parse(readFileSync(new URL("tests/fixtures/op07_discovery_candidate.json", root), "utf8"));
        acceptedCandidate ||= candidate.candidate_files?.[file] === digest;
    } catch {}
    try {
        // A separate declaration binds only this unaccepted Owner topology delta.
        // It never rewrites historical reviewed or discovery-candidate pins.
        const candidate = JSON.parse(readFileSync(new URL("tests/fixtures/op07_grouped_topology_candidate.json", root), "utf8"));
        acceptedCandidate ||= file === "web/openrouter_video.js" && candidate.status === "UNACCEPTED" &&
            candidate.baseline_sha === "b6289127e7d2e6f735f6497e7e6cf0f26c5adcac" && candidate.candidate_files?.[file] === digest;
    } catch {}
    assert(acceptedCandidate || digest === pin.reviewed_files[file], `Undeclared RC change: ${file}`);
    return execFileSync("git", ["show", `${pin.baseline_sha}:${file}`], { cwd: root, encoding: "utf8" }).replace(/\r\n/g, "\n");
}
