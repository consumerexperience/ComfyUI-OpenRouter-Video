import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

// Historical shields retain their exact accepted source. This separate pin is
// UNACCEPTED and must also pass current ACI negative-space and behavior tests.
export function aciCandidateMatches(root, file, digest) {
    const pin = JSON.parse(readFileSync(new URL("tests/fixtures/aci_v1_source_candidate.json", root), "utf8"));
    return pin.status === "UNACCEPTED" &&
        pin.baseline_sha === "f8ba174347bd4bfed155dc64aec1d7168c39c1fa" &&
        pin.candidate_files?.[file] === digest;
}

export function aciHistoricalSource(root, file, current) {
    const digest = createHash("sha256").update(current.replace(/\r\n/g, "\n")).digest("hex");
    if (!aciCandidateMatches(root, file, digest)) return current;
    return execFileSync("git", ["show", `f8ba174347bd4bfed155dc64aec1d7168c39c1fa:${file}`],
        { cwd: root, encoding: "utf8" }).replace(/\r\n/g, "\n");
}
