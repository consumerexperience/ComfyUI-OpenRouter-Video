import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
export function reviewedRcText(root, file, text) {
    const pin = JSON.parse(readFileSync(new URL("tests/fixtures/rc_live_reviewed_patch.json", root), "utf8"));
    if (!pin.reviewed_files[file]) return text;
    const current = readFileSync(new URL(file, root), "utf8").replace(/\r\n/g, "\n");
    assert.equal(createHash("sha256").update(current).digest("hex"), pin.reviewed_files[file], `Undeclared RC change: ${file}`);
    return execFileSync("git", ["show", `${pin.baseline_sha}:${file}`], { cwd: root, encoding: "utf8" }).replace(/\r\n/g, "\n");
}
