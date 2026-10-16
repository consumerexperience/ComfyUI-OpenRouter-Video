import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../../web/openrouter_video.js", import.meta.url), "utf8");

test("public naming and first-run connection surface are present", () => {
    assert(source.includes('id: "OpenRouter Video.Connection"'));
    assert(source.includes("Connect OpenRouter"));
    assert(source.includes("Sign in with OpenRouter"));
    assert(source.includes("OpenRouter Video 0.1.0-rc.1 by ARENAS®lab"));
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
