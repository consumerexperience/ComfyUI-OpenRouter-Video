import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { execFileSync } from "node:child_process";

const source = readFileSync(new URL("../../web/openrouter_video.js", import.meta.url), "utf8");

test("public naming and first-run connection surface are present", () => {
    assert(source.includes('id: "OpenRouter Video.Connection"'));
    assert(source.includes("Connect OpenRouter"));
    assert(source.includes("Sign in with OpenRouter"));
    assert(source.includes("OpenRouter Video 0.1.0-rc.2 by ARENAS®lab"));
    assert(source.includes("/openrouter-video/v1/connection"));
    assert(source.includes("/openrouter-video/v1/auth/start"));
});

test("frontend connection flow has no browser secret persistence or paid submit", () => {
    assert(!/localStorage|sessionStorage|indexedDB/i.test(source));
    assert(!source.includes("/api/v1/videos"));
    assert(!source.includes("/prompt"));
    assert(!/Authorization\s*:/i.test(source));
    assert(source.includes('method: "DELETE"'));
});

test("RC identity matches package metadata and changes only two About literals", () => {
    const metadata = readFileSync(new URL("../../pyproject.toml", import.meta.url), "utf8");
    const version = metadata.match(/^version = "([^"]+)"/m)?.[1];
    assert.equal(version, "0.1.0-rc.2");
    assert(source.includes(`aria-label", "OpenRouter Video ${version} by ARENAS®lab"`));
    assert(source.includes(`version.textContent = "${version}"`));
    assert.equal(source.split(version).length - 1, 2);
    const baseline = execFileSync("git", ["show", "6ad02d8969484984cab4661513b6b8868cd70169:web/openrouter_video.js"], {cwd: new URL("../../", import.meta.url), encoding: "utf8"});
    assert.equal(source.replaceAll(version, "0.1.0-rc.1").replace(/\r\n/g, "\n"), baseline.replace(/\r\n/g, "\n"));
});
